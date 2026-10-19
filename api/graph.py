"""
api/graph.py - FastAPI Router for Regulatory Knowledge Graph Explorer & GraphRAG.

Exposes endpoints for:
- Full EASA & Multi-Source Knowledge Federation stats & catalog
- Dual Entry Discovery: exact code match and HyDE dense vector search
- D3 Force-Directed Subgraph Generators (Compliance Chain, Blast Radius, Concept Ontology)
- Deep 360° Node Inspection & Dossier generation
- Compliance Path Traversals
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from fastapi import APIRouter, HTTPException, Query

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

_graph_import_error = None
try:
    from ingestion.graph.traversal import get_engine, EasaGraphEngine
    from ingestion.graph.sources import get_source_manager, MultiSourceManager
    from ingestion.graph.hyde import get_hyde_engine, HydeEngine
except Exception as e:
    _graph_import_error = str(e)
    get_engine = None
    get_source_manager = None
    get_hyde_engine = None

router = APIRouter()


def build_chain_graph(chain: Dict[str, Any]) -> Dict[str, Any]:
    """Converts compliance chain result to D3 nodes and links."""
    nodes = []
    links = []
    seen_nodes = set()

    def add_node(node_id: str, label: str, node_type: str, props: Dict[str, Any] = None):
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append({
                "id": node_id,
                "label": label,
                "type": node_type,
                **(props or {})
            })

    # 1. Anchor IR
    rule = chain["anchor_rule"]
    add_node(rule["id"], rule["code"], rule["content_type"], {
        "title": rule["title"],
        "legal_force": rule["legal_force"],
        "subject": rule["subject"],
        "text": rule["text_snippet"],
        "is_anchor": True
    })

    # 2. Annex
    annex = chain["annex"]
    annex_id = f"ANNEX_{annex['code']}"
    add_node(annex_id, annex["code"], "ANNEX", {
        "title": annex["name"],
        "subject": annex["code"]
    })
    links.append({"source": rule["id"], "target": annex_id, "type": "BELONGS_TO_ANNEX", "label": "BELONGS_TO"})

    # 3. AMCs (Soft Law)
    for amc in chain["acceptable_means_of_compliance"]:
        add_node(amc["id"], amc["code"], "AMC", {
            "title": amc["title"],
            "legal_force": amc["legal_force"],
            "text": amc.get("text_snippet", "")
        })
        links.append({"source": amc["id"], "target": rule["id"], "type": "SATISFIES", "label": "SATISFIES"})

    # 4. GMs (Soft Law)
    for gm in chain["guidance_material"]:
        add_node(gm["id"], gm["code"], "GM", {
            "title": gm["title"],
            "legal_force": gm["legal_force"],
            "text": gm.get("text_snippet", "")
        })
        links.append({"source": gm["id"], "target": rule["id"], "type": "EXPLAINS", "label": "EXPLAINS"})

    # 5. Concepts
    for c in chain.get("concepts", []):
        cid = f"CONCEPT_{c['name']}"
        add_node(cid, c["name"], "CONCEPT", {
            "category": c["category"],
            "title": c["name"]
        })
        links.append({"source": rule["id"], "target": cid, "type": "GOVERNS_CONCEPT", "label": "GOVERNS"})

    # 6. Stakeholders
    for s in chain.get("stakeholders", []):
        sid = f"STAKEHOLDER_{s['name']}"
        add_node(sid, s["name"], "STAKEHOLDER", {
            "role_type": s["role_type"],
            "title": s["name"]
        })
        links.append({"source": rule["id"], "target": sid, "type": "APPLIES_TO", "label": "APPLIES_TO"})

    # 7. Outgoing citations
    for cite in chain.get("outgoing_citations", []):
        cite_id = f"CITE_{cite['code']}"
        add_node(cite_id, cite["code"], cite.get("content_type", "IR"), {
            "title": cite.get("title", ""),
            "subject": cite.get("subject", "")
        })
        links.append({"source": rule["id"], "target": cite_id, "type": "CROSS_REFERENCES", "label": "CITES"})

    # 8. Semantic Parallels (SIMILAR_TO)
    for sim in chain.get("similar_provisions", []):
        sim_id = sim["id"]
        score_pct = int(round(sim.get("score", 0.0) * 100))
        add_node(sim_id, sim["code"], sim.get("content_type", "IR"), {
            "title": sim.get("title", ""),
            "legal_force": sim.get("legal_force", ""),
            "annex": sim.get("annex", ""),
            "similarity_score": sim.get("score", 0.0),
            "similarity_reason": sim.get("reason", "")
        })
        links.append({
            "source": rule["id"],
            "target": sim_id,
            "type": "SIMILAR_TO",
            "label": f"SIMILAR ({score_pct}%)",
            "score": sim.get("score", 0.0),
            "reason": sim.get("reason", "")
        })

    return {
        "query": chain["query"],
        "anchor": rule,
        "nodes": nodes,
        "links": links
    }


def build_blast_graph(blast: Dict[str, Any]) -> Dict[str, Any]:
    """Converts blast radius result to D3 nodes and links."""
    nodes = []
    links = []
    seen_nodes = set()

    def add_node(node_id: str, label: str, node_type: str, props: Dict[str, Any] = None):
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append({"id": node_id, "label": label, "type": node_type, **(props or {})})

    target = blast["target"]
    add_node(target["id"], target["code"], target["content_type"], {
        "title": target["title"],
        "is_anchor": True
    })

    for d in blast.get("direct_dependent_rules", []):
        did = f"DEP_{d['code']}"
        add_node(did, d["code"], d["content_type"], {
            "title": d["title"],
            "subject": d["subject"]
        })
        links.append({"source": did, "target": target["id"], "type": "CROSS_REFERENCES", "label": "CITES"})

    for s in blast.get("attached_soft_law", []):
        sid = f"SOFT_{s['code']}_{s['rel_type']}"
        node_type = "AMC" if "SATISFIES" in s["rel_type"] else "GM"
        add_node(sid, s["code"], node_type, {"title": s["title"]})
        links.append({"source": sid, "target": target["id"], "type": s["rel_type"], "label": s["rel_type"]})

    return {
        "target": target,
        "nodes": nodes,
        "links": links
    }


def build_concept_graph(sub: Dict[str, Any]) -> Dict[str, Any]:
    """Converts concept subgraph to D3 nodes and links."""
    nodes = []
    links = []
    seen = set()

    c = sub["concept"]
    cid = f"CONCEPT_{c['name']}"
    nodes.append({"id": cid, "label": c["name"], "type": "CONCEPT", "category": c["category"], "is_anchor": True})
    seen.add(cid)

    for annex_name, provs in sub.get("provisions_by_annex", {}).items():
        annex_id = f"ANNEX_{annex_name}"
        if annex_id not in seen:
            seen.add(annex_id)
            nodes.append({"id": annex_id, "label": annex_name, "type": "ANNEX"})
            links.append({"source": annex_id, "target": cid, "type": "COVERS_CONCEPT", "label": "COVERS"})

        for p in provs[:6]:
            pid = f"PROV_{p['code']}"
            if pid not in seen:
                seen.add(pid)
                nodes.append({
                    "id": pid,
                    "label": p["code"],
                    "type": p["content_type"],
                    "title": p["title"],
                    "legal_force": p["legal_force"]
                })
                links.append({"source": pid, "target": annex_id, "type": "BELONGS_TO", "label": "IN"})
                links.append({"source": pid, "target": cid, "type": "GOVERNS_CONCEPT", "label": "GOVERNS"})

    return {
        "concept": c,
        "nodes": nodes,
        "links": links
    }


def check_graph_engine():
    if _graph_import_error:
        raise HTTPException(
            status_code=503,
            detail=f"Graph engine dependency error: {_graph_import_error}. Please ensure Python 3.11 with kuzu is active."
        )


@router.get("/stats")
def get_graph_stats():
    """Returns knowledge graph node and relationship counts."""
    check_graph_engine()
    try:
        eng = get_engine()
        return eng.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
def get_sources_catalog():
    """Returns the catalog of integrated regulatory knowledge sources and Skybrary sub-topics."""
    try:
        sm = get_source_manager()
        return sm.get_sources_catalog()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
def search_graph(
    q: str = Query("", description="Search term, provision code, or keyword"),
    sources: str = Query("EASA,EU,FAA,SKYBRARY,EUROCAE", description="Comma-separated active sources"),
    skybrary_topics: str = Query("", description="Comma-separated Skybrary sub-topics")
):
    """Searches across EASA graph and federated knowledge sources."""
    query = q.strip()
    if not query:
        return {"query": "", "active_sources": [], "results": []}

    raw_sources = sources.strip() if isinstance(sources, str) else "EASA,EU,FAA,SKYBRARY,EUROCAE"
    active_sources = set(s.strip() for s in raw_sources.split(",") if s.strip()) if raw_sources else {"EASA", "EU", "FAA", "SKYBRARY", "EUROCAE"}

    raw_topics = skybrary_topics.strip() if isinstance(skybrary_topics, str) else ""
    selected_topics = set(t.strip() for t in raw_topics.split(",") if t.strip()) if raw_topics else None

    results = []

    # 1. EASA Search from Kùzu
    if "EASA" in active_sources:
        try:
            eng = get_engine()
            res = eng.conn.execute(f"""
                MATCH (p:Provision)
                WHERE p.code =~ '(?i).*{query}.*' OR p.title =~ '(?i).*{query}.*'
                RETURN p.id, p.code, p.title, p.content_type, p.subject
                LIMIT 20;
            """)
            while res.has_next():
                row = res.get_next()
                results.append({
                    "id": row[0],
                    "code": row[1],
                    "title": row[2],
                    "type": row[3],
                    "source": "EASA",
                    "subject": row[4]
                })
        except Exception as e:
            print(f"[WARN] Error in EASA graph search: {e}")

    # 2. Secondary Sources Search
    try:
        sm = get_source_manager()
        sec_results = sm.search_sources(
            query,
            active_sources=active_sources,
            skybrary_topics=selected_topics,
            limit_per_source=8
        )
        results.extend(sec_results)
    except Exception as e:
        print(f"[WARN] Error in secondary source search: {e}")

    return {"query": query, "active_sources": list(active_sources), "results": results}


@router.get("/hyde")
def hyde_search(
    q: str = Query(..., description="Natural language operational scenario or regulatory intent"),
    sources: str = Query("EASA,EU,FAA,SKYBRARY,EUROCAE", description="Comma-separated active sources"),
    skybrary_topics: str = Query("", description="Comma-separated Skybrary sub-topics"),
    top_k: int = Query(12, ge=1, le=50, description="Max candidate provisions to return")
):
    """
    Hypothetical Document Embeddings (HyDE) discovery:
    Generates a dense legal anchor and finds matching provisions.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    raw_sources = sources.strip() if isinstance(sources, str) else "EASA,EU,FAA,SKYBRARY,EUROCAE"
    active_sources = set(s.strip() for s in raw_sources.split(",") if s.strip()) if raw_sources else {"EASA", "EU", "FAA", "SKYBRARY", "EUROCAE"}

    raw_topics = skybrary_topics.strip() if isinstance(skybrary_topics, str) else ""
    selected_topics = set(t.strip() for t in raw_topics.split(",") if t.strip()) if raw_topics else None

    try:
        top_k = int(top_k) if top_k else 12
        engine_hyde = get_hyde_engine()
        results = engine_hyde.search_candidates(
            query,
            top_k=top_k,
            active_sources=active_sources,
            skybrary_topics=selected_topics
        )
        if isinstance(results, dict):
            cands = results.get("candidates") or results.get("candidate_nodes") or []
            results["candidates"] = cands
            results["candidate_nodes"] = cands
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chain")
def get_compliance_chain_graph(
    code: str = Query("CAT.OP.MPA.180", description="EASA Provision Code (e.g. CAT.OP.MPA.180, ORO.GEN.200)")
):
    """Retrieves full compliance chain and formats as D3 force-directed graph."""
    try:
        eng = get_engine()
        chain = eng.get_compliance_chain(code)
        if "error" in chain:
            raise HTTPException(status_code=404, detail=chain["error"])
        return build_chain_graph(chain)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blast")
def get_blast_radius_graph(
    code: str = Query("ORO.GEN.200", description="EASA Provision Code to analyze dependency radius for")
):
    """Retrieves all dependent and citing rules formatted as D3 force-directed graph."""
    try:
        eng = get_engine()
        blast = eng.get_blast_radius(code)
        if "error" in blast:
            raise HTTPException(status_code=404, detail=blast["error"])
        return build_blast_graph(blast)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concept")
def get_concept_subgraph_graph(
    name: str = Query("Fuel", description="Aviation Concept name or substring (e.g. Fuel, SMS, FTL)")
):
    """Retrieves concept subgraph across Annexes formatted as D3 graph."""
    try:
        eng = get_engine()
        sub = eng.get_concept_subgraph(name)
        if "error" in sub:
            raise HTTPException(status_code=404, detail=sub["error"])
        return build_concept_graph(sub)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/node")
def get_node_details_api(
    id: str = Query("", description="Node ID or code"),
    code: str = Query("", description="Alternative code parameter")
):
    """Deep inspection of any provision, annex, concept, stakeholder, or multi-source dossier."""
    node_id = (id or code).strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="Missing node 'id' or 'code' parameter")

    clean_id = node_id
    for pfx in ("CITE_", "DEP_", "PROV_", "TARGET_"):
        if clean_id.startswith(pfx):
            clean_id = clean_id[len(pfx):]
            break
    if clean_id.startswith("SOFT_"):
        clean_id = clean_id[5:]
        if "_SATISFIES_" in clean_id:
            clean_id = clean_id.split("_SATISFIES_")[0]
        elif "_EXPLAINS_" in clean_id:
            clean_id = clean_id.split("_EXPLAINS_")[0]

    # Check secondary source dossier first
    if node_id.startswith(("FAA_", "SKYBRARY_", "EU_", "EUROCAE_")) or clean_id.startswith(("FAA_", "SKYBRARY_", "EU_", "EUROCAE_")):
        try:
            sm = get_source_manager()
            dossier = sm.get_source_dossier(clean_id) or sm.get_source_dossier(node_id)
            if dossier:
                text_val = dossier.get("text") or dossier.get("full_text") or dossier.get("text_snippet") or ""
                dossier.setdefault("full_text", text_val)
                dossier.setdefault("text_snippet", text_val[:300] if len(text_val) > 300 else text_val)
                dossier.setdefault("graphrag_context", dossier.get("graph_rag_markdown", text_val))
                return dossier
        except Exception as e:
            print(f"[WARN] Error fetching source dossier: {e}")

    try:
        eng = get_engine()
        details = eng.get_node_details(clean_id)
        if "error" in details and clean_id != node_id:
            details = eng.get_node_details(node_id)
        if "error" in details:
            raise HTTPException(status_code=404, detail=details["error"])

        # Ensure normalized property aliases
        text_val = details.get("text") or details.get("full_text") or details.get("text_snippet") or ""
        details.setdefault("text", text_val)
        details.setdefault("full_text", text_val)
        details.setdefault("text_snippet", text_val[:300] if len(text_val) > 300 else text_val)

        amcs = details.get("acceptable_means_of_compliance") or details.get("downstream_amcs") or []
        details["acceptable_means_of_compliance"] = amcs
        details["downstream_amcs"] = amcs

        gms = details.get("guidance_material") or details.get("downstream_gms") or []
        details["guidance_material"] = gms
        details["downstream_gms"] = gms

        up = details.get("upstream_rules") or details.get("upstream") or []
        details["upstream_rules"] = up
        details["upstream"] = up

        rag = details.get("graphrag_context") or details.get("graph_rag_markdown") or ""
        details["graphrag_context"] = rag
        details["graph_rag_markdown"] = rag

        return details
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path")
def find_compliance_path_api(
    start: str = Query(..., description="Start provision code"),
    end: str = Query(..., description="End provision code")
):
    """Discovers citation path connecting two provisions."""
    try:
        eng = get_engine()
        return eng.find_compliance_path(start, end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
