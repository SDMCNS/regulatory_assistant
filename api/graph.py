"""
api/graph.py - FastAPI Router for Regulatory Knowledge Graph Explorer & GraphRAG.

Exposes endpoints for:
- Full EASA & Multi-Source Knowledge Federation stats & catalog
- Dual Entry Discovery: exact code match and HyDE dense vector search
- D3 Force-Directed Subgraph Generators (Compliance Chain, Blast Radius, Concept Ontology)
- Deep 360° Node Inspection & Dossier generation
- Compliance Path Traversals
"""

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.core.config import settings

logger = logging.getLogger("api.graph")
NARRATIVES_CACHE_FILE = settings.DATA_DIR / "concept_narratives.json"
_narratives_lock = threading.Lock()


def _load_cached_narratives() -> Dict[str, Any]:
    if not NARRATIVES_CACHE_FILE.exists():
        return {}
    try:
        with _narratives_lock:
            with open(NARRATIVES_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read concept narratives cache: {e}")
        return {}


def _save_cached_narrative(cache_key: str, data: Dict[str, Any]) -> None:
    try:
        NARRATIVES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _narratives_lock:
            cache = {}
            if NARRATIVES_CACHE_FILE.exists():
                try:
                    with open(NARRATIVES_CACHE_FILE, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                except Exception:
                    cache = {}
            cache[cache_key] = data
            with open(NARRATIVES_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save concept narrative to cache: {e}")


_graph_import_error = None
try:
    from ingestion.graph.traversal import get_engine, EasaGraphEngine
    from ingestion.graph.sources import get_source_manager, MultiSourceManager
    from ingestion.graph.hyde import get_hyde_engine, HydeEngine
    from ingestion.graph.custom_concepts import get_custom_concept_manager, CustomConceptManager
    from api.utils import call_unified_chat
except Exception as e:
    _graph_import_error = str(e)
    get_engine = None
    get_source_manager = None
    get_hyde_engine = None
    get_custom_concept_manager = None
    call_unified_chat = None

router = APIRouter()


class GenerateConceptRequest(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None


class ConceptNarrativeRequest(BaseModel):
    concept_name: str
    provider: Optional[str] = "gemini"  # "gemini" or "local"
    model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    force_refresh: Optional[bool] = False



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
    """Converts concept subgraph to D3 nodes and links with rich cross-annex hierarchy."""
    nodes = []
    links = []
    seen = set()

    c = sub["concept"]
    cid = c.get("id") or f"CONCEPT_{c['name']}"
    is_custom = c.get("is_custom", sub.get("is_custom", False))
    total_provs = sub.get("total_governing_provisions", 0)

    nodes.append({
        "id": cid,
        "label": c["name"],
        "type": "CONCEPT",
        "category": c.get("category", "General"),
        "is_anchor": True,
        "is_custom": is_custom,
        "description": c.get("description", ""),
        "total_provisions": total_provs,
        "title": f"Aviation Concept: {c['name']} ({c.get('category', 'General')})"
    })
    seen.add(cid)

    provisions_by_annex = sub.get("provisions_by_annex", {})
    # Sort annexes by provision count descending
    sorted_annexes = sorted(provisions_by_annex.items(), key=lambda x: len(x[1]), reverse=True)

    for annex_name, provs in sorted_annexes[:8]:
        annex_id = f"ANNEX_{annex_name}"
        if annex_id not in seen:
            seen.add(annex_id)
            full_annex_name = provs[0].get("annex_name") if provs else annex_name
            nodes.append({
                "id": annex_id,
                "label": annex_name,
                "type": "ANNEX",
                "title": full_annex_name or f"Annex {annex_name}"
            })
            links.append({"source": annex_id, "target": cid, "type": "COVERS_CONCEPT", "label": "COVERS"})

        # Prioritize IRs (hard law) first, then AMCs, then GMs
        def _prov_sort_key(p: Dict[str, Any]) -> int:
            ct = p.get("content_type", "")
            if ct == "IR":
                return 0
            if ct == "AMC":
                return 1
            if ct == "GM":
                return 2
            return 3

        sorted_provs = sorted(provs, key=_prov_sort_key)
        for p in sorted_provs[:5]:
            pid = p.get("id") or f"PROV_{p['code']}"
            if pid not in seen:
                seen.add(pid)
                lbl = p["code"]
                if p.get("title") and any(tag in p["title"] for tag in ("AMC", "GM")):
                    parts = p["title"].split()
                    if len(parts) >= 2 and any(tag in parts[0] for tag in ("AMC", "GM")):
                        lbl = f"{parts[0]} {parts[1]}"
                nodes.append({
                    "id": pid,
                    "label": lbl,
                    "type": p["content_type"],
                    "title": p["title"],
                    "legal_force": p["legal_force"]
                })
                links.append({"source": pid, "target": annex_id, "type": "BELONGS_TO", "label": "IN"})
                links.append({"source": pid, "target": cid, "type": "GOVERNS_CONCEPT", "label": "GOVERNS"})

    return {
        "concept": c,
        "total_provisions": total_provs,
        "is_custom": is_custom,
        "nodes": nodes,
        "links": links
    }


def build_regulation_concept_graph(res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts regulation concepts subgraph to D3 nodes and links.
    - Anchor Node: The selected RegulationDocument (type: REGULATION, is_anchor: True)
    - Orbit Nodes: Applicable Concepts (type: CONCEPT)
    - Edge Nodes: Strongly connected Other Regulations (type: CROSS_REGULATION)
    """
    nodes = []
    links = []
    seen = set()

    doc = res["regulation"]
    anchor_id = doc["id"]
    seen.add(anchor_id)
    nodes.append({
        "id": anchor_id,
        "label": doc.get("code") or doc["id"].replace("DOC_", "").split("__")[0],
        "type": "REGULATION",
        "title": doc["title"],
        "total_topics": doc.get("total_topics", 0),
        "source": doc.get("source", "EASA"),
        "annex_count": doc.get("annex_count", 0),
        "is_anchor": True
    })

    for c in res.get("applicable_concepts", []):
        cid = c.get("id") or f"CONCEPT_{c['name']}"
        if cid not in seen:
            seen.add(cid)
            nodes.append({
                "id": cid,
                "label": c["name"],
                "type": "CONCEPT",
                "category": c.get("category", "General"),
                "rule_count": c.get("rule_count", 0),
                "is_custom": c.get("is_custom", False)
            })

        # Link REGULATION -> CONCEPT
        links.append({
            "source": anchor_id,
            "target": cid,
            "type": "COVERS_CONCEPT",
            "label": f"Governs ({c.get('rule_count', 0)} rules)",
            "rule_count": c.get("rule_count", 0)
        })

        # Connected other regulations
        for cr in c.get("connected_regulations", []):
            crid = f"CROSS_REG_{cr['id']}"
            if crid not in seen:
                seen.add(crid)
                nodes.append({
                    "id": crid,
                    "target_doc_id": cr["id"],
                    "label": cr.get("code") or cr["id"].replace("DOC_", "").split("__")[0],
                    "type": "CROSS_REGULATION",
                    "title": cr["title"],
                    "shared_rules": cr.get("shared_rules", 0)
                })

            links.append({
                "source": cid,
                "target": crid,
                "type": "BRIDGES_TO",
                "label": f"Bridges ({cr.get('shared_rules', 0)} rules)",
                "shared_rules": cr.get("shared_rules", 0)
            })

    return {
        "regulation": doc,
        "nodes": nodes,
        "links": links,
        "total_concepts": res.get("total_concepts", len(res.get("applicable_concepts", []))),
        "all_regulations": res.get("all_regulations", [])
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


@router.get("/concepts")
def get_concepts_catalog():
    """Returns the full catalog of aviation ontology concepts with category and rule counts."""
    check_graph_engine()
    try:
        eng = get_engine()
        return eng.get_all_concepts()
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


@router.get("/regulations")
def get_regulations_catalog():
    """Returns the catalog of all primary regulation documents and frameworks in the graph."""
    check_graph_engine()
    try:
        eng = get_engine()
        return eng.get_all_regulations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regulation/concepts")
def get_regulation_concepts_graph(
    name: str = Query("Air Operations", description="Regulation title, code, or alias (e.g. Air Operations, Continuing Airworthiness, Part-CAT, CS-25)")
):
    """
    Retrieves the applicable concepts in a selected regulation mapped out with
    edge nodes for other regulations that strongly connect to those concepts.
    """
    check_graph_engine()
    try:
        eng = get_engine()
        sub = eng.get_regulation_concepts_subgraph(name)
        if "error" in sub:
            raise HTTPException(status_code=404, detail=sub["error"])
        return build_regulation_concept_graph(sub)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/concept/generate")
def generate_custom_concept_api(request: GenerateConceptRequest):
    """
    Suggest and generate a new aviation concept ontology mesh.
    Discovers governing provisions across EASA regulations,
    persists the concept for future sessions, and formats as D3 force-directed graph.
    """
    check_graph_engine()
    clean_name = request.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Concept name cannot be empty")

    try:
        eng = get_engine()
        hyde = None
        try:
            hyde = get_hyde_engine()
        except Exception:
            pass

        if get_custom_concept_manager is None:
            raise HTTPException(status_code=500, detail="Custom concept manager is not available")

        mgr = get_custom_concept_manager()
        generated = mgr.generate_concept(
            name=clean_name,
            category=request.category,
            description=request.description,
            eng=eng,
            hyde=hyde
        )

        return build_concept_graph(generated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/concept/custom")
def delete_custom_concept_api(id: str = Query(..., description="Custom Concept ID or Name")):
    """Deletes a user-generated custom concept by ID or name."""
    if get_custom_concept_manager is None:
        raise HTTPException(status_code=500, detail="Custom concept manager is not available")
    try:
        mgr = get_custom_concept_manager()
        deleted = mgr.delete_concept(id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Custom concept '{id}' not found")
        return {"status": "deleted", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concept/narrative")
def generate_concept_narrative_api(request: ConceptNarrativeRequest):
    """
    Synthesizes an LLM-based regulatory narrative and executive report
    for a concept ontology mesh using Google Gemini Cloud or Local LM Studio.
    """
    check_graph_engine()
    concept_name = request.concept_name.strip()
    if not concept_name:
        raise HTTPException(status_code=400, detail="Concept name cannot be empty")

    provider_used = request.provider or "gemini"
    cache_key = f"{concept_name.lower()}_{provider_used.lower()}"

    # Return persistent stored report if available and force_refresh is not requested
    if not request.force_refresh:
        cached_narratives = _load_cached_narratives()
        if cache_key in cached_narratives:
            cached_data = dict(cached_narratives[cache_key])
            cached_data["cached"] = True
            logger.info(f"Returning cached concept narrative for '{concept_name}' ({provider_used})")
            return cached_data

    try:
        eng = get_engine()
        sub = eng.get_concept_subgraph(concept_name)
        if "error" in sub:
            raise HTTPException(status_code=404, detail=sub["error"])

        c_info = sub["concept"]
        provs_by_annex = sub.get("provisions_by_annex", {})
        total_provisions = sub.get("total_governing_provisions", 0)

        # Build comprehensive structural topology prompt
        lines = [
            f"# Concept: {c_info.get('name', concept_name)}",
            f"Domain / Category: {c_info.get('category', 'Flight Operations & Airworthiness')}",
            f"Total Codified Governing Provisions: {total_provisions}",
            f"Description / Scope: {c_info.get('description', 'Aviation regulatory concept mesh across European air law')}\n",
            "## Governing Regulatory Annexes & Codified Hierarchy:"
        ]

        # Sort annexes by provision count descending
        sorted_annexes = sorted(provs_by_annex.items(), key=lambda x: len(x[1]), reverse=True)
        annexes_covered = []

        for annex, provs in sorted_annexes[:8]:
            annexes_covered.append(annex)
            lines.append(f"\n### Annex: {annex} ({len(provs)} provisions)")
            irs = [p for p in provs if p.get('content_type') == 'IR'][:5]
            amcs = [p for p in provs if p.get('content_type') == 'AMC'][:5]
            gms = [p for p in provs if p.get('content_type') == 'GM'][:4]
            cs_rules = [p for p in provs if p.get('content_type') == 'CS'][:4]

            if irs:
                lines.append("- Implementing Rules (IR - Hard Law / Mandatory Baseline):")
                for p in irs:
                    lines.append(f"  * {p['code']}: {p['title']}")
            if cs_rules:
                lines.append("- Certification Specifications (CS - Technical Airworthiness Standard):")
                for p in cs_rules:
                    lines.append(f"  * {p['code']}: {p['title']}")
            if amcs:
                lines.append("- Acceptable Means of Compliance (AMC - Soft Law / Standard Compliance Path):")
                for p in amcs:
                    lines.append(f"  * {p['code']}: {p['title']}")
            if gms:
                lines.append("- Guidance Material (GM - Soft Law / Operational Interpretation):")
                for p in gms:
                    lines.append(f"  * {p['code']}: {p['title']}")

        topology_text = "\n".join(lines)

        system_prompt = (
            "You are a senior European Aviation Safety Agency (EASA) regulatory architect and aviation compliance legal expert. "
            "You are given an interactive Concept Ontology Mesh codifying how European aviation regulations govern a specific domain across Annexes, "
            "Implementing Rules (IR), Certification Specifications (CS), Acceptable Means of Compliance (AMC), and Guidance Material (GM).\n\n"
            "TASK:\n"
            "Write an authoritative, clear, and comprehensive regulatory synthesis report outlining 'how it all fits together'.\n\n"
            "FORMAT & STYLE REQUIREMENTS:\n"
            "- Use clean GitHub-flavored markdown with structured headings (H2, H3), bold terminology, bullet lists, and comparative markdown tables.\n"
            "- Clearly articulate the interaction between Hard Law (IR / CS) and Soft Law (AMC / GM).\n"
            "- Detail how different Annexes (e.g., Part-ORO organizational requirements vs Part-CAT operational procedures vs Part-M/CAMO airworthiness) interface.\n"
            "- Provide practical guidance for airline operators, safety managers, CAMO, and audit inspectors.\n\n"
            "REQUIRED SECTIONS:\n"
            "1. ## Executive Summary & Operational Mandate\n"
            "   - Purpose, safety intent, and regulatory objective in European aviation.\n"
            "2. ## Regulatory Pillars & Multi-Annex Architecture\n"
            "   - Detailed breakdown of how each Annex contributes to governing this concept.\n"
            "   - Include a Markdown Table: | Annex | Scope & Domain | Core Provisions | Role in Concept |\n"
            "3. ## Compliance Chain: Hard Law vs Soft Law Interplay\n"
            "   - The binding legal baseline established by Implementing Rules (IR).\n"
            "   - The role of AMCs as standard approved compliance paths vs Alternative Means of Compliance (AltMoC).\n"
            "   - How Guidance Material (GM) provides operational rationale and interpretation.\n"
            "4. ## Cross-Annex Interplay & Stakeholder Responsibilities\n"
            "   - Obligations of Aircraft Operators (Part-CAT / Part-NCC / Part-SPO).\n"
            "   - Role of Organization Requirements (Part-ORO / SMS / Management Systems).\n"
            "   - Interfaces with Continuing Airworthiness (Part-CAMO / Part-M) and Technical Specs (CS-25).\n"
            "   - Competent Authority oversight.\n"
            "5. ## Key Compliance Audit Checkpoints & Operational Risk Focus\n"
            "   - 5 actionable inspection checkpoints for operators, flight operations inspectors, and safety auditors."
        )

        user_prompt = (
            f"Generate the comprehensive EASA regulatory synthesis report for the following Concept Ontology Mesh:\n\n"
            f"{topology_text}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        from datetime import datetime
        provider_used = request.provider or "gemini"

        if call_unified_chat is None:
            raise HTTPException(status_code=500, detail="LLM chat service is not initialized")

        narrative_text = call_unified_chat(
            messages=messages,
            provider=provider_used,
            gemini_api_key=request.gemini_api_key,
            gemini_model=request.model or "gemini-3.5-flash",
            max_tokens=3500,
            temperature=0.3
        )

        response_data = {
            "concept": c_info.get("name", concept_name),
            "category": c_info.get("category", "General"),
            "total_provisions": total_provisions,
            "annexes_covered": annexes_covered,
            "provider_used": provider_used,
            "narrative": narrative_text,
            "generated_at": datetime.utcnow().isoformat(),
            "cached": False
        }
        _save_cached_narrative(cache_key, response_data)
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate concept narrative: {str(e)}")


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
