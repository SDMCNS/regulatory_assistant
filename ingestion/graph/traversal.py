"""
traversal.py - Regulatory Graph Traversal & GraphRAG Query Engine for EASA.

Provides multi-hop Cypher traversals over Kùzu:
1. get_compliance_chain: Discovers IR + AMCs + GMs + Annex + Stakeholders.
2. get_blast_radius: Discovers all rules referencing or dependent on a target provision.
3. get_concept_subgraph: Aggregates all rules governing an aviation concept across Annexes.
4. find_compliance_path: Finds shortest legal path connecting two provisions.
5. build_graph_rag_context: Enriches semantic search seeds with structural legal context.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import re
import kuzu
from ingestion.core.config import settings


_global_engine = None


def get_engine(db_path: Optional[Path] = None) -> "EasaGraphEngine":
    """Returns singleton EasaGraphEngine instance."""
    global _global_engine
    if _global_engine is None:
        target_path = Path(db_path or settings.KUZU_DB_PATH)
        _global_engine = EasaGraphEngine(target_path)
    return _global_engine


class EasaGraphEngine:
    """Client for querying the EASA Kùzu knowledge graph."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or settings.KUZU_DB_PATH)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Kùzu database not found at {self.db_path}. Build graph first.")
        self.db = kuzu.Database(str(self.db_path), read_only=True)
        self.conn = kuzu.Connection(self.db)

    def get_stats(self) -> Dict[str, Any]:
        """Returns node and relationship counts across the knowledge graph."""
        res_nodes = self.conn.execute("""
            MATCH (p:Provision)
            RETURN p.content_type, count(*)
        """)
        provisions_by_type = {}
        while res_nodes.has_next():
            row = res_nodes.get_next()
            provisions_by_type[row[0]] = row[1]

        res_rels = {}
        rel_tables = [
            "CONTAINS_ANNEX", "BELONGS_TO_ANNEX", "SATISFIES",
            "EXPLAINS", "CROSS_REFERENCES", "GOVERNS_CONCEPT", "APPLIES_TO", "SIMILAR_TO"
        ]
        for rel in rel_tables:
            try:
                r = self.conn.execute(f"MATCH ()-[e:{rel}]->() RETURN count(*);")
                res_rels[rel.lower()] = r.get_next()[0] if r.has_next() else 0
            except Exception:
                res_rels[rel.lower()] = 0

        total_provisions = sum(provisions_by_type.values())
        return {
            "total_provisions": total_provisions,
            "provisions_by_type": provisions_by_type,
            "relationships": res_rels
        }

    def get_compliance_chain(self, query_code: str) -> Dict[str, Any]:
        """
        Retrieves the full Hard Law <-> Soft Law compliance chain for a rule code:
        - The Implementing Rule (IR)
        - Acceptable Means of Compliance (AMC)
        - Guidance Material (GM)
        - Parent Annex
        - Governed Concepts & Obligated Stakeholders
        """
        query_clean = query_code.strip()
        clean_base = re.sub(r'^(?:AMC\d*|GM\d*)\s+', '', query_clean, flags=re.IGNORECASE).strip()
        clean_base = re.sub(r'\(.*?\)', '', clean_base).strip()

        # Find primary provision
        res_prov = self.conn.execute(f"""
            MATCH (p:Provision)
            WHERE p.code = '{query_clean}' OR p.base_code = '{query_clean}' OR p.code = '{clean_base}' OR p.base_code = '{clean_base}'
            RETURN p.id, p.code, p.base_code, p.title, p.content_type, p.legal_force, p.subject, p.text
            LIMIT 10;
        """)

        found_provisions = []
        while res_prov.has_next():
            row = res_prov.get_next()
            found_provisions.append({
                "id": row[0],
                "code": row[1],
                "base_code": row[2],
                "title": row[3],
                "content_type": row[4],
                "legal_force": row[5],
                "subject": row[6],
                "text_snippet": row[7][:300] + "..." if len(row[7]) > 300 else row[7]
            })

        if not found_provisions:
            return {"error": f"No provision found matching code '{query_code}'"}

        # Identify anchor IR
        anchor_ir = next((p for p in found_provisions if p["content_type"] == "IR"), found_provisions[0])

        # If the queried node is an AMC or GM, check if we can resolve its parent IR
        if anchor_ir["content_type"] in ("AMC", "GM") and anchor_ir.get("base_code"):
            res_parent = self.conn.execute(f"""
                MATCH (ir:Provision)
                WHERE (ir.code = '{anchor_ir["base_code"]}' OR ir.id = '{anchor_ir["base_code"]}') AND ir.content_type = 'IR'
                RETURN ir.id, ir.code, ir.base_code, ir.title, ir.content_type, ir.legal_force, ir.subject, ir.text
                LIMIT 1;
            """)
            if res_parent.has_next():
                row = res_parent.get_next()
                anchor_ir = {
                    "id": row[0],
                    "code": row[1],
                    "base_code": row[2],
                    "title": row[3],
                    "content_type": row[4],
                    "legal_force": row[5],
                    "subject": row[6],
                    "text_snippet": row[7][:300] + "..." if len(row[7]) > 300 else row[7]
                }

        anchor_id = anchor_ir["id"]
        base_code = anchor_ir["base_code"]

        # 1. Fetch all AMCs (SATISFIES)
        res_amc = self.conn.execute(f"""
            MATCH (amc:Provision)-[:SATISFIES]->(ir:Provision {{id: '{anchor_id}'}})
            RETURN amc.id, amc.code, amc.title, amc.legal_force, amc.text
        """)
        amcs = []
        while res_amc.has_next():
            row = res_amc.get_next()
            amcs.append({
                "id": row[0],
                "code": row[1],
                "title": row[2],
                "legal_force": row[3],
                "text_snippet": row[4][:250] + "..." if len(row[4]) > 250 else row[4]
            })

        # 2. Fetch all GMs (EXPLAINS)
        res_gm = self.conn.execute(f"""
            MATCH (gm:Provision)-[:EXPLAINS]->(ir:Provision {{id: '{anchor_id}'}})
            RETURN gm.id, gm.code, gm.title, gm.legal_force, gm.text
        """)
        gms = []
        while res_gm.has_next():
            row = res_gm.get_next()
            gms.append({
                "id": row[0],
                "code": row[1],
                "title": row[2],
                "legal_force": row[3],
                "text_snippet": row[4][:250] + "..." if len(row[4]) > 250 else row[4]
            })

        # 3. Fetch Annex info
        res_annex = self.conn.execute(f"""
            MATCH (p:Provision {{id: '{anchor_id}'}})-[:BELONGS_TO_ANNEX]->(a:Annex)
            RETURN a.code, a.name
        """)
        annex_info = res_annex.get_next() if res_annex.has_next() else ("General", "General Provisions")

        # 4. Fetch Governed Concepts
        res_concepts = self.conn.execute(f"""
            MATCH (p:Provision {{id: '{anchor_id}'}})-[g:GOVERNS_CONCEPT]->(c:Concept)
            RETURN c.name, c.category, g.relevance
        """)
        concepts = []
        while res_concepts.has_next():
            row = res_concepts.get_next()
            concepts.append({"name": row[0], "category": row[1], "relevance": row[2]})

        # 5. Fetch Obligated Stakeholders
        res_stakeholders = self.conn.execute(f"""
            MATCH (p:Provision {{id: '{anchor_id}'}})-[a:APPLIES_TO]->(s:Stakeholder)
            RETURN s.name, s.role_type, a.obligation
        """)
        stakeholders = []
        while res_stakeholders.has_next():
            row = res_stakeholders.get_next()
            stakeholders.append({"name": row[0], "role_type": row[1], "obligation": row[2]})

        # 6. Fetch Outgoing Cross-References (What does this rule cite?)
        res_cites = self.conn.execute(f"""
            MATCH (p:Provision {{id: '{anchor_id}'}})-[:CROSS_REFERENCES]->(target:Provision)
            RETURN target.code, target.title, target.subject, target.content_type
            LIMIT 15
        """)
        cites = []
        while res_cites.has_next():
            row = res_cites.get_next()
            cites.append({"code": row[0], "title": row[1], "subject": row[2], "content_type": row[3]})

        # 7. Fetch Semantic Parallels (SIMILAR_TO)
        similar = []
        try:
            res_sim = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{anchor_id}'}})-[r:SIMILAR_TO]->(target:Provision)
                OPTIONAL MATCH (target)-[:BELONGS_TO_ANNEX]->(a:Annex)
                RETURN target.id, target.code, target.title, target.content_type, target.legal_force, r.score, r.method, r.reason, a.code
                ORDER BY r.score DESC
                LIMIT 8;
            """)
            while res_sim.has_next():
                row = res_sim.get_next()
                similar.append({
                    "id": row[0],
                    "code": row[1],
                    "title": row[2],
                    "content_type": row[3],
                    "legal_force": row[4],
                    "score": round(float(row[5]), 3),
                    "method": row[6],
                    "reason": row[7],
                    "annex": row[8] or "EASA"
                })
        except Exception:
            pass

        return {
            "query": query_code,
            "anchor_rule": anchor_ir,
            "annex": {"code": annex_info[0], "name": annex_info[1]},
            "amc_count": len(amcs),
            "acceptable_means_of_compliance": amcs,
            "gm_count": len(gms),
            "guidance_material": gms,
            "concepts": concepts,
            "stakeholders": stakeholders,
            "outgoing_citations": cites,
            "similar_provisions": similar
        }

    def get_blast_radius(self, query_code: str) -> Dict[str, Any]:
        """
        Calculates the regulatory blast-radius:
        All provisions that cite or depend on this provision.
        """
        query_clean = query_code.strip()
        res_target = self.conn.execute(f"""
            MATCH (p:Provision)
            WHERE p.code = '{query_clean}' OR p.base_code = '{query_clean}'
            RETURN p.id, p.code, p.title, p.content_type
            LIMIT 1;
        """)
        if not res_target.has_next():
            return {"error": f"Target provision '{query_code}' not found."}

        target = res_target.get_next()
        target_id = target[0]

        # 1. Rules citing this provision
        res_incoming = self.conn.execute(f"""
            MATCH (source:Provision)-[:CROSS_REFERENCES]->(target:Provision {{id: '{target_id}'}})
            RETURN source.code, source.title, source.subject, source.content_type
        """)
        citing_rules = []
        while res_incoming.has_next():
            row = res_incoming.get_next()
            citing_rules.append({
                "code": row[0],
                "title": row[1],
                "subject": row[2],
                "content_type": row[3]
            })

        # 2. Associated AMCs / GMs
        soft_law = []
        res_sat = self.conn.execute(f"""
            MATCH (soft:Provision)-[:SATISFIES]->(target:Provision {{id: '{target_id}'}})
            RETURN soft.code, soft.title
        """)
        while res_sat.has_next():
            row = res_sat.get_next()
            soft_law.append({"code": row[0], "title": row[1], "rel_type": "SATISFIES"})

        res_exp = self.conn.execute(f"""
            MATCH (soft:Provision)-[:EXPLAINS]->(target:Provision {{id: '{target_id}'}})
            RETURN soft.code, soft.title
        """)
        while res_exp.has_next():
            row = res_exp.get_next()
            soft_law.append({"code": row[0], "title": row[1], "rel_type": "EXPLAINS"})

        return {
            "target": {"id": target[0], "code": target[1], "title": target[2], "content_type": target[3]},
            "direct_dependent_rules_count": len(citing_rules),
            "direct_dependent_rules": citing_rules,
            "attached_soft_law_count": len(soft_law),
            "attached_soft_law": soft_law
        }

    def get_all_concepts(self) -> List[Dict[str, Any]]:
        """Returns all aviation ontology concepts (Kùzu taxonomy + user-defined custom concepts)."""
        res = self.conn.execute("""
            MATCH (c:Concept)
            OPTIONAL MATCH (p:Provision)-[:GOVERNS_CONCEPT]->(c)
            WHERE p.content_type IN ['IR', 'AMC', 'GM', 'CS']
            RETURN c.id, c.name, c.category, count(p)
            ORDER BY count(p) DESC;
        """)
        concepts = []
        seen_ids = set()
        while res.has_next():
            row = res.get_next()
            c_id = row[0]
            seen_ids.add(c_id.lower())
            concepts.append({
                "id": c_id,
                "name": row[1],
                "category": row[2],
                "total_provisions": row[3],
                "is_custom": False
            })

        # Integrate User-Suggested / Generated Custom Concepts
        try:
            from ingestion.graph.custom_concepts import get_custom_concept_manager
            mgr = get_custom_concept_manager()
            custom_list = mgr.load_all()
            for cc in custom_list:
                c_data = cc.get("concept", cc)
                c_id = c_data.get("id") or cc.get("id", "")
                if c_id.lower() not in seen_ids:
                    seen_ids.add(c_id.lower())
                    concepts.insert(0, {
                        "id": c_id,
                        "name": c_data.get("name", "Custom Concept"),
                        "category": c_data.get("category", "Custom Concept"),
                        "total_provisions": cc.get("total_governing_provisions", len(cc.get("provisions_by_annex", {}))),
                        "is_custom": True,
                        "description": c_data.get("description", "")
                    })
        except Exception as e:
            pass

        return concepts

    def resolve_concept(self, concept_query: str) -> Optional[Dict[str, Any]]:
        """
        Robustly resolves any concept query, preset name, acronym, or ID
        to its canonical concept record without fragile regex syntax errors.
        """
        q = concept_query.strip().lower()
        if not q:
            return None

        # 1. Check custom concepts first
        try:
            from ingestion.graph.custom_concepts import get_custom_concept_manager
            mgr = get_custom_concept_manager()
            cust = mgr.get_concept(concept_query)
            if cust:
                return {
                    "id": cust.get("concept", {}).get("id") or cust.get("id"),
                    "name": cust.get("concept", {}).get("name") or cust.get("name"),
                    "category": cust.get("concept", {}).get("category") or cust.get("category"),
                    "is_custom": True,
                    "raw_custom": cust
                }
        except Exception:
            pass

        # 2. Get all taxonomy concepts
        all_concepts = self.get_all_concepts()

        # Check exact ID (with or without 'concept_')
        for c in all_concepts:
            cid = c["id"].lower()
            if cid == q or cid.replace("concept_", "") == q:
                return c

        # Check exact Name
        for c in all_concepts:
            if c["name"].lower() == q:
                return c

        # Check Parentheses Acronyms (e.g. user passes 'SMS' or '(SMS)', matches 'Safety Management System (SMS)')
        for c in all_concepts:
            c_name_lower = c["name"].lower()
            if f"({q})" in c_name_lower or f"/{q})" in c_name_lower or f"({q}/" in c_name_lower or f"/{q}/" in c_name_lower:
                return c

        # Check Token Overlap for compound phrases (e.g. 'ATM/ANS Airspace' -> 'Air Traffic Management & Airspace (ATM/ANS/SERA)')
        q_clean = re.sub(r'[^a-zA-Z0-9]+', ' ', q).strip()
        q_words = set(w for w in q_clean.split() if len(w) > 2)
        best_c = None
        best_score = 0
        for c in all_concepts:
            c_clean = re.sub(r'[^a-zA-Z0-9]+', ' ', c["name"].lower()).strip()
            c_words = set(w for w in c_clean.split() if len(w) > 2)
            score = len(q_words & c_words)
            if score > best_score:
                best_score = score
                best_c = c
        if best_score >= 1:
            return best_c

        # Check Substring
        for c in all_concepts:
            if q in c["name"].lower() or c["name"].lower() in q:
                return c

        return None

    def get_concept_subgraph(self, concept_name: str) -> Dict[str, Any]:
        """
        Finds all regulatory provisions governing an aviation concept across Annexes.
        Handles both native Kùzu graph concepts and user-generated custom concepts.
        """
        resolved = self.resolve_concept(concept_name)
        if not resolved:
            return {"error": f"Concept '{concept_name}' not found in taxonomy."}

        # If it's a custom concept, return its pre-built mesh
        if resolved.get("is_custom"):
            raw = resolved.get("raw_custom")
            if not raw:
                try:
                    from ingestion.graph.custom_concepts import get_custom_concept_manager
                    mgr = get_custom_concept_manager()
                    raw = mgr.get_concept(resolved["id"]) or mgr.get_concept(resolved["name"])
                except Exception:
                    raw = None

            if raw:
                c_info = raw.get("concept", raw)
                provs_by_annex = raw.get("provisions_by_annex", {})
                total_provs = sum(len(v) for v in provs_by_annex.values())
                return {
                    "concept": {
                        "id": c_info.get("id", resolved["id"]),
                        "name": c_info.get("name", resolved["name"]),
                        "category": c_info.get("category", resolved.get("category", "Custom")),
                        "description": c_info.get("description", ""),
                        "is_custom": True
                    },
                    "total_governing_provisions": total_provs,
                    "provisions_by_annex": provs_by_annex,
                    "is_custom": True
                }

        # Otherwise query Kùzu for the canonical concept ID
        concept_id = resolved["id"]
        c_name = resolved["name"]
        c_cat = resolved.get("category", "General")

        res_provs = self.conn.execute(f"""
            MATCH (p:Provision)-[g:GOVERNS_CONCEPT]->(c:Concept {{id: '{concept_id}'}})
            WHERE p.content_type IN ['IR', 'AMC', 'GM', 'CS']
            OPTIONAL MATCH (p)-[:BELONGS_TO_ANNEX]->(a:Annex)
            RETURN p.id, p.code, p.title, p.subject, p.content_type, p.legal_force, g.relevance, a.code, a.name
        """)

        provisions_by_annex: Dict[str, List[Dict[str, Any]]] = {}
        while res_provs.has_next():
            row = res_provs.get_next()
            p_id, p_code, p_title, p_subj, p_ctype, p_force, g_rel, a_code, a_name = row
            annex = (a_code if a_code and a_code != "n/a" else None) or (p_subj if p_subj and p_subj != "n/a" else None) or "General"
            if annex not in provisions_by_annex:
                provisions_by_annex[annex] = []
            provisions_by_annex[annex].append({
                "id": p_id,
                "code": p_code,
                "title": p_title,
                "content_type": p_ctype,
                "legal_force": p_force,
                "relevance": g_rel,
                "annex_name": a_name or annex
            })

        total_provisions = sum(len(v) for v in provisions_by_annex.values())
        return {
            "concept": {"name": c_name, "category": c_cat, "id": concept_id, "is_custom": False},
            "total_governing_provisions": total_provisions,
            "provisions_by_annex": provisions_by_annex,
            "is_custom": False
        }

    def get_all_regulations(self) -> List[Dict[str, Any]]:
        """
        Returns all primary Regulation Documents and Annexes available in the graph.
        """
        res = self.conn.execute("""
            MATCH (d:RegulationDocument)
            OPTIONAL MATCH (d)-[:CONTAINS_ANNEX]->(a:Annex)
            RETURN d.id, d.title, d.source, d.total_topics, count(DISTINCT a) as annex_count
            ORDER BY d.total_topics DESC;
        """)
        regs = []
        while res.has_next():
            row = res.get_next()
            doc_id, title, src, topics, annexes = row

            clean_name = title.strip()
            clean_name = clean_name.replace("’", "'").replace("—", " - ").replace("–", " - ")
            if clean_name.lower().startswith("easy access rules for "):
                clean_name = clean_name[len("easy access rules for "):].strip()
            clean_name = clean_name.replace(" (Regulation (EU) No ", " (Reg ").replace(" (Regulation (EU) ", " (Reg ").replace(" (Regulations (EU) ", " (Regs ")
            clean_name = clean_name.replace("Regulation (EU) No ", "Reg ").replace("Regulation (EU) ", "Reg ")
            clean_name = clean_name.replace("_", ".")
            if clean_name.startswith("the "):
                clean_name = clean_name[4:].capitalize()
            elif clean_name.startswith("The "):
                clean_name = clean_name[4:]
            elif clean_name.startswith("small category"):
                clean_name = "Small Category VCA"
            elif "Sailplane Rule Book" in clean_name:
                clean_name = "Sailplanes (Rule Book)"

            short_code = doc_id.replace("DOC_", "").split("__")[0]
            if "AIR_OPERATIONS" in doc_id:
                short_code = "AIR-OPS (965/2012)"
                clean_name = "Air Operations (Reg 965/2012)"
            elif "CONTINUING_AIRWORTHINESS" in doc_id:
                short_code = "AIRWORTHINESS (1321/2014)"
                clean_name = "Continuing Airworthiness (Reg 1321/2014)"
            elif "AIRCREW" in doc_id:
                short_code = "AIRCREW (1178/2011)"
                clean_name = "Aircrew Licensing (Reg 1178/2011)"
            elif "AERODROMES" in doc_id:
                short_code = "AERODROMES (139/2014)"
                clean_name = "Aerodromes (Reg 139/2014)"
            elif "AIR_TRAFFIC_MANAGEMENT" in doc_id and "EQUIPMENT" in doc_id:
                short_code = "ATM/ANS Equipment"
                clean_name = "ATM/ANS Equipment Specifications"
            elif "AIR_TRAFFIC_MANAGEMENT" in doc_id:
                short_code = "ATM/ANS (2017/373)"
                clean_name = "Air Traffic Management (ATM/ANS 2017/373)"
            elif "LARGE_AEROPLANES" in doc_id:
                short_code = "CS-25 (Large Aeroplanes)"
                clean_name = "Large Aeroplanes (CS-25)"
            elif "INFORMATION_SECURITY" in doc_id:
                short_code = "PART-IS (Cybersecurity)"
                clean_name = "Information Security (Part-IS 2023/203)"
            elif "UNMANNED" in doc_id:
                short_code = "UAS (Drones 2019/947)"
                clean_name = "Unmanned Aircraft Systems (Drones 2019/947)"
            elif "STANDARDISED_EUROPEAN_RULES_OF_THE_AIR" in doc_id:
                short_code = "SERA (923/2012)"
                clean_name = "Rules of the Air (SERA 923/2012)"
            elif "GROUND_HANDLING" in doc_id:
                short_code = "GROUND HANDLING (2025/23)"
                clean_name = "Ground Handling (Part-GH 2025/23)"
            elif "INITIAL_AIRWORTHINESS" in doc_id:
                short_code = "PART-21 (Design/Production)"
                clean_name = "Initial Airworthiness (Part-21 748/2012)"
            elif "CS_MMEL" in doc_id:
                short_code = "CS-MMEL (Master MEL)"
                clean_name = "Master Minimum Equipment List (CS-MMEL)"
            elif "CS_AWO" in doc_id:
                short_code = "CS-AWO (All-Weather)"
                clean_name = "All-Weather Operations (CS-AWO)"
            elif "CS_ACNS" in doc_id:
                short_code = "CS-ACNS (Comms/Nav/Surv)"
                clean_name = "Airborne Comms, Nav & Surveillance (CS-ACNS)"
            elif "CS_ETSO" in doc_id:
                short_code = "CS-ETSO (Technical Orders)"
                clean_name = "European Technical Standard Orders (CS-ETSO)"
            elif "U_SPACE" in doc_id:
                short_code = "U-SPACE (2021/664)"
                clean_name = "U-Space Airspace (Reg 2021/664)"
            elif "BASIC_REGULATION" in doc_id:
                short_code = "BASIC REG (2018/1139)"
                clean_name = "The Basic Regulation (Reg 2018/1139)"
            elif "OCCURRENCE_REPORTING" in doc_id:
                short_code = "OCCURRENCE (376/2014)"
                clean_name = "Occurrence Reporting (Reg 376/2014)"
            elif "LARGE_ROTORCRAFT" in doc_id:
                short_code = "CS-29 (Rotorcraft)"
                clean_name = "Large Rotorcraft (CS-29)"
            elif "SMALL_ROTORCRAFT" in doc_id:
                short_code = "CS-27 (Rotorcraft)"
                clean_name = "Small Rotorcraft (CS-27)"
            elif "NORMAL_CATEGORY_AEROPLANES" in doc_id:
                short_code = "CS-23 (Normal Aeroplanes)"
                clean_name = "Normal-Category Aeroplanes (CS-23)"
            elif "VERY_LIGHT_AEROPLANES" in doc_id:
                short_code = "CS-VLA (Light Aeroplanes)"
                clean_name = "Very Light Aeroplanes (CS-VLA)"
            elif "LIGHT_SPORT_AEROPLANES" in doc_id:
                short_code = "CS-LSA (Light Sport)"
                clean_name = "Light Sport Aeroplanes (CS-LSA)"
            elif "ENGINES" in doc_id:
                short_code = "CS-E (Engines)"
                clean_name = "Engines (CS-E)"
            elif "SAILPLANES" in doc_id:
                short_code = "CS-22 (Sailplanes)"
                clean_name = "Sailplanes & Powered Sailplanes (CS-22)"
            elif "THIRD_COUNTRY_OPERATORS" in doc_id:
                short_code = "TCO (Third Country)"
                clean_name = "Third Country Operators (Part-TCO)"
            elif "HOT_AIR_BALLOONS" in doc_id:
                short_code = "CS-31HB (Hot Air)"
                clean_name = "Hot Air Balloons (CS-31HB)"
            elif "TETHERED_GAS_BALLOONS" in doc_id:
                short_code = "CS-31TGB (Tethered)"
                clean_name = "Tethered Gas Balloons (CS-31TGB)"
            elif "GAS_BALLOONS" in doc_id:
                short_code = "CS-31GB (Gas)"
                clean_name = "Gas Balloons (CS-31GB)"
            elif "BALLOONS" in doc_id:
                short_code = "BALLOONS"
                clean_name = "Balloons (Part-BFCL & Operations)"

            regs.append({
                "id": doc_id,
                "name": clean_name,
                "code": short_code,
                "title": title,
                "source": src or "EASA",
                "total_topics": topics or 0,
                "annex_count": annexes or 0
            })
        return regs

    def resolve_regulation(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolves any user-provided query, code, or alias to a canonical RegulationDocument.
        """
        q = (query or "").strip()
        if not q:
            return None
        q_lower = q.lower()
        all_regs = self.get_all_regulations()

        # 1. Exact ID, Code, or Name match
        for r in all_regs:
            if (
                r["id"].lower() == q_lower
                or r["code"].lower() == q_lower
                or r.get("name", "").lower() == q_lower
            ):
                return r

        # 2. Domain aliases
        alias_map = {
            "air operations": "DOC_02_AIR_OPERATIONS",
            "air ops": "DOC_02_AIR_OPERATIONS",
            "part-cat": "DOC_02_AIR_OPERATIONS",
            "part-oro": "DOC_02_AIR_OPERATIONS",
            "part-spa": "DOC_02_AIR_OPERATIONS",
            "part-ncc": "DOC_02_AIR_OPERATIONS",
            "part-nco": "DOC_02_AIR_OPERATIONS",
            "part-spo": "DOC_02_AIR_OPERATIONS",
            "part-aro": "DOC_02_AIR_OPERATIONS",
            "cat": "DOC_02_AIR_OPERATIONS",
            "oro": "DOC_02_AIR_OPERATIONS",
            "continuing airworthiness": "DOC_08_CONTINUING_AIRWORTHINESS",
            "airworthiness": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-m": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-145": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-camo": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-66": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-147": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-cao": "DOC_08_CONTINUING_AIRWORTHINESS",
            "part-ml": "DOC_08_CONTINUING_AIRWORTHINESS",
            "camo": "DOC_08_CONTINUING_AIRWORTHINESS",
            "aircrew": "DOC_03_AIRCREW__REGULATION__EU__NO_1178_2011",
            "part-fcl": "DOC_03_AIRCREW__REGULATION__EU__NO_1178_2011",
            "part-med": "DOC_03_AIRCREW__REGULATION__EU__NO_1178_2011",
            "part-cc": "DOC_03_AIRCREW__REGULATION__EU__NO_1178_2011",
            "fcl": "DOC_03_AIRCREW__REGULATION__EU__NO_1178_2011",
            "aerodromes": "DOC_06_AERODROMES",
            "aerodrome": "DOC_06_AERODROMES",
            "part-adr": "DOC_06_AERODROMES",
            "adr": "DOC_06_AERODROMES",
            "atm": "DOC_05_AIR_TRAFFIC_MANAGEMENT_AIR_NAVIGATION_SERVICES___PROVISION_OF_SERVICES",
            "ans": "DOC_05_AIR_TRAFFIC_MANAGEMENT_AIR_NAVIGATION_SERVICES___PROVISION_OF_SERVICES",
            "atm/ans": "DOC_05_AIR_TRAFFIC_MANAGEMENT_AIR_NAVIGATION_SERVICES___PROVISION_OF_SERVICES",
            "cs-25": "DOC_01_LARGE_AEROPLANES__CS_25",
            "cs25": "DOC_01_LARGE_AEROPLANES__CS_25",
            "large aeroplanes": "DOC_01_LARGE_AEROPLANES__CS_25",
            "cybersecurity": "DOC_09_INFORMATION_SECURITY__REGULATIONS__EU__2023_203_AND_2022_1645",
            "part-is": "DOC_09_INFORMATION_SECURITY__REGULATIONS__EU__2023_203_AND_2022_1645",
            "information security": "DOC_09_INFORMATION_SECURITY__REGULATIONS__EU__2023_203_AND_2022_1645",
            "uas": "DOC_10_UNMANNED_AIRCRAFT_SYSTEMS",
            "drone": "DOC_10_UNMANNED_AIRCRAFT_SYSTEMS",
            "drones": "DOC_10_UNMANNED_AIRCRAFT_SYSTEMS",
            "u-space": "DOC_25_U_SPACE__REGULATION__EU__2021_664",
            "sera": "DOC_15_STANDARDISED_EUROPEAN_RULES_OF_THE_AIR",
            "rules of the air": "DOC_15_STANDARDISED_EUROPEAN_RULES_OF_THE_AIR",
            "ground handling": "DOC_30_GROUND_HANDLING__GH___REGULATIONS__EU__2025_23_AND_2025_20",
            "part-gh": "DOC_30_GROUND_HANDLING__GH___REGULATIONS__EU__2025_23_AND_2025_20",
            "part-21": "DOC_13_INITIAL_AIRWORTHINESS_AND_ENVIRONMENTAL_PROTECTION__REGULATION__EU__NO_748_2012",
            "initial airworthiness": "DOC_13_INITIAL_AIRWORTHINESS_AND_ENVIRONMENTAL_PROTECTION__REGULATION__EU__NO_748_2012",
            "mmel": "DOC_16_MASTER_MINIMUM_EQUIPMENT_LIST__EAR_FOR_CS_MMEL",
            "cs-mmel": "DOC_16_MASTER_MINIMUM_EQUIPMENT_LIST__EAR_FOR_CS_MMEL",
            "basic regulation": "DOC_40_THE_BASIC_REGULATION__REGULATION__EU__2018_1139",
            "occurrence reporting": "DOC_36_OCCURRENCE_REPORTING__REGULATION__EU__NO_376_2014"
        }
        for alias, target_id in alias_map.items():
            if alias in q_lower or q_lower in alias:
                for r in all_regs:
                    if r["id"] == target_id:
                        return r

        # 3. Substring match on title
        for r in all_regs:
            if q_lower in r["title"].lower():
                return r

        return all_regs[0] if all_regs else None

    def get_regulation_concepts_subgraph(self, regulation_query: str) -> Dict[str, Any]:
        """
        Maps out applicable concepts covered by a regulation and identifies
        strongly connected cross-regulatory edge nodes bridging those concepts.
        """
        doc = self.resolve_regulation(regulation_query)
        if not doc:
            return {"error": f"Regulation '{regulation_query}' could not be identified."}

        doc_id = doc["id"]
        doc_prefix = doc_id

        # 1. Query Native Kùzu Concepts
        res_concepts = self.conn.execute(f"""
            MATCH (d:RegulationDocument {{id: '{doc_id}'}})-[:CONTAINS_ANNEX]->(a:Annex)<-[:BELONGS_TO_ANNEX]-(p:Provision)-[:GOVERNS_CONCEPT]->(c:Concept)
            RETURN c.id, c.name, c.category, count(DISTINCT p) as rule_count
            ORDER BY rule_count DESC
            LIMIT 16;
        """)

        concept_map: Dict[str, Dict[str, Any]] = {}
        while res_concepts.has_next():
            row = res_concepts.get_next()
            c_id, c_name, c_cat, r_count = row
            concept_map[c_id] = {
                "id": c_id,
                "name": c_name,
                "category": c_cat or "General",
                "rule_count": r_count,
                "is_custom": False,
                "connected_regulations": []
            }

        # 2. Blend in Custom Concepts that have rules in this regulation
        try:
            from ingestion.graph.custom_concepts import get_custom_concept_manager
            mgr = get_custom_concept_manager()
            custom_list = mgr.load_all()
            for cc in custom_list:
                c_info = cc.get("concept", cc)
                c_id = c_info.get("id") or cc.get("id", "")
                c_name = c_info.get("name", "")
                c_cat = c_info.get("category", "Custom Concept")

                matching_rules = 0
                for annex, provs in cc.get("provisions_by_annex", {}).items():
                    for p in provs:
                        pid = p.get("id", "")
                        if pid.startswith(doc_prefix) or (doc_id in pid):
                            matching_rules += 1

                if matching_rules > 0:
                    if c_id not in concept_map:
                        concept_map[c_id] = {
                            "id": c_id,
                            "name": c_name,
                            "category": c_cat,
                            "rule_count": matching_rules,
                            "is_custom": True,
                            "connected_regulations": []
                        }
                    else:
                        concept_map[c_id]["rule_count"] = max(concept_map[c_id]["rule_count"], matching_rules)
        except Exception:
            pass

        # Sort concepts by rule count and keep top 14
        sorted_concepts = sorted(concept_map.values(), key=lambda x: x["rule_count"], reverse=True)[:14]

        all_regs = {r["id"]: r for r in self.get_all_regulations()}

        # 3. For each applicable concept, find top connected OTHER regulations
        for c in sorted_concepts:
            c_id = c["id"]
            if not c["is_custom"]:
                res_cross = self.conn.execute(f"""
                    MATCH (c:Concept {{id: '{c_id}'}})<-[:GOVERNS_CONCEPT]-(p2:Provision)-[:BELONGS_TO_ANNEX]->(a2:Annex)<-[:CONTAINS_ANNEX]-(d2:RegulationDocument)
                    WHERE d2.id <> '{doc_id}'
                    RETURN d2.id, d2.title, count(DISTINCT p2) as other_count
                    ORDER BY other_count DESC
                    LIMIT 3;
                """)
                while res_cross.has_next():
                    d2_id, d2_title, ocnt = res_cross.get_next()
                    reg_meta = all_regs.get(d2_id, {})
                    c["connected_regulations"].append({
                        "id": d2_id,
                        "code": reg_meta.get("code") or d2_id.replace("DOC_", "").split("__")[0],
                        "title": d2_title,
                        "shared_rules": ocnt
                    })
            else:
                # Custom concept cross-regulations from provisions_by_annex
                try:
                    raw_cc = mgr.get_concept(c_id)
                    if raw_cc:
                        doc_counts = {}
                        for annex, provs in raw_cc.get("provisions_by_annex", {}).items():
                            for p in provs:
                                pid = p.get("id", "")
                                if pid.startswith("DOC_"):
                                    extracted_doc = pid.split("_ERULES-")[0]
                                    if extracted_doc != doc_id:
                                        doc_counts[extracted_doc] = doc_counts.get(extracted_doc, 0) + 1

                        top_other = sorted(doc_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                        for other_doc_id, cnt in top_other:
                            reg_meta = all_regs.get(other_doc_id, {})
                            c["connected_regulations"].append({
                                "id": other_doc_id,
                                "code": reg_meta.get("code") or other_doc_id.replace("DOC_", "").split("__")[0],
                                "title": reg_meta.get("title") or other_doc_id,
                                "shared_rules": cnt
                            })
                except Exception:
                    pass

        return {
            "regulation": doc,
            "applicable_concepts": sorted_concepts,
            "total_concepts": len(sorted_concepts),
            "all_regulations": [r for r in all_regs.values()][:15]
        }


    def get_node_details(self, node_id_or_code: str) -> Dict[str, Any]:
        """
        Deep-inspection of any graph node (Provision, Annex, Concept, or Stakeholder),
        returning full verbatim contents, upstream/downstream legal hierarchy,
        incoming and outgoing citations, and operational context.
        """
        identifier = node_id_or_code.strip()
        clean_id = identifier
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

        # 1. Check if it's a Provision
        res_p = self.conn.execute(f"""
            MATCH (p:Provision)
            WHERE p.id = '{identifier}' OR p.id = '{clean_id}'
               OR p.code = '{identifier}' OR p.code = '{clean_id}'
               OR p.base_code = '{identifier}' OR p.base_code = '{clean_id}'
               OR p.code STARTS WITH '{clean_id}'
            RETURN p.id, p.code, p.base_code, p.title, p.content_type, p.legal_force, p.subject, p.text, p.word_count
            LIMIT 1;
        """)

        if res_p.has_next():
            row = res_p.get_next()
            prov_id, prov_code, base_code, title, c_type, legal_force, subject, full_text, word_count = row

            # Parent Annex
            annex_info = None
            res_annex = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[:BELONGS_TO_ANNEX]->(a:Annex)
                RETURN a.id, a.code, a.name
                LIMIT 1;
            """)
            if res_annex.has_next():
                a_row = res_annex.get_next()
                annex_info = {"id": a_row[0], "code": a_row[1], "name": a_row[2]}

            # Upstream Legal Context (What does this provision satisfy or explain?)
            upstream = []
            res_up_sat = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[:SATISFIES]->(target:Provision)
                RETURN target.id, target.code, target.title, target.content_type, target.legal_force
            """)
            while res_up_sat.has_next():
                u = res_up_sat.get_next()
                upstream.append({"id": u[0], "code": u[1], "title": u[2], "content_type": u[3], "legal_force": u[4], "rel": "SATISFIES"})

            res_up_exp = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[:EXPLAINS]->(target:Provision)
                RETURN target.id, target.code, target.title, target.content_type, target.legal_force
            """)
            while res_up_exp.has_next():
                u = res_up_exp.get_next()
                upstream.append({"id": u[0], "code": u[1], "title": u[2], "content_type": u[3], "legal_force": u[4], "rel": "EXPLAINS"})

            # Downstream Soft Law (What AMCs / GMs attach to this provision?)
            downstream_amcs = []
            res_down_amc = self.conn.execute(f"""
                MATCH (amc:Provision)-[:SATISFIES]->(p:Provision {{id: '{prov_id}'}})
                RETURN amc.id, amc.code, amc.title, amc.legal_force, amc.text, amc.word_count
            """)
            while res_down_amc.has_next():
                d = res_down_amc.get_next()
                downstream_amcs.append({
                    "id": d[0], "code": d[1], "title": d[2], "legal_force": d[3],
                    "text_preview": d[4][:240] + "..." if len(d[4]) > 240 else d[4],
                    "word_count": d[5]
                })

            downstream_gms = []
            res_down_gm = self.conn.execute(f"""
                MATCH (gm:Provision)-[:EXPLAINS]->(p:Provision {{id: '{prov_id}'}})
                RETURN gm.id, gm.code, gm.title, gm.legal_force, gm.text, gm.word_count
            """)
            while res_down_gm.has_next():
                d = res_down_gm.get_next()
                downstream_gms.append({
                    "id": d[0], "code": d[1], "title": d[2], "legal_force": d[3],
                    "text_preview": d[4][:240] + "..." if len(d[4]) > 240 else d[4],
                    "word_count": d[5]
                })

            # Citations: Outgoing
            outgoing_citations = []
            res_out = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[:CROSS_REFERENCES]->(target:Provision)
                RETURN target.id, target.code, target.title, target.content_type
            """)
            while res_out.has_next():
                o = res_out.get_next()
                outgoing_citations.append({"id": o[0], "code": o[1], "title": o[2], "content_type": o[3]})

            # Citations: Incoming (Blast Radius dependencies)
            incoming_citations = []
            res_in = self.conn.execute(f"""
                MATCH (source:Provision)-[:CROSS_REFERENCES]->(p:Provision {{id: '{prov_id}'}})
                RETURN source.id, source.code, source.title, source.content_type
            """)
            while res_in.has_next():
                i = res_in.get_next()
                incoming_citations.append({"id": i[0], "code": i[1], "title": i[2], "content_type": i[3]})

            # Stakeholders
            stakeholders = []
            res_stk = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[r:APPLIES_TO]->(s:Stakeholder)
                RETURN s.id, s.name, s.role_type, r.obligation
            """)
            while res_stk.has_next():
                s = res_stk.get_next()
                stakeholders.append({"id": s[0], "name": s[1], "role_type": s[2], "obligation": s[3]})

            # Concepts
            concepts = []
            res_c = self.conn.execute(f"""
                MATCH (p:Provision {{id: '{prov_id}'}})-[r:GOVERNS_CONCEPT]->(c:Concept)
                RETURN c.id, c.name, c.category, r.relevance
            """)
            while res_c.has_next():
                c = res_c.get_next()
                concepts.append({"id": c[0], "name": c[1], "category": c[2], "relevance": c[3]})

            # Semantic Parallels (SIMILAR_TO)
            similar_provisions = []
            try:
                res_sim = self.conn.execute(f"""
                    MATCH (p:Provision {{id: '{prov_id}'}})-[r:SIMILAR_TO]->(target:Provision)
                    OPTIONAL MATCH (target)-[:BELONGS_TO_ANNEX]->(a:Annex)
                    RETURN target.id, target.code, target.title, target.content_type, target.legal_force, r.score, r.method, r.reason, a.code
                    ORDER BY r.score DESC
                    LIMIT 10;
                """)
                while res_sim.has_next():
                    row = res_sim.get_next()
                    score_val = float(row[5])
                    similar_provisions.append({
                        "id": row[0],
                        "code": row[1],
                        "title": row[2],
                        "content_type": row[3],
                        "legal_force": row[4],
                        "score": round(score_val, 3),
                        "score_pct": int(round(score_val * 100)),
                        "method": row[6],
                        "reason": row[7],
                        "annex": row[8] or "EASA"
                    })
            except Exception:
                pass

            # Synthesize GraphRAG Context block
            rag_lines = [
                f"# EASA REGULATORY CONTEXT: {prov_code} - {title}",
                f"- Legal Tier: {legal_force} ({c_type})",
                f"- Annex: {annex_info['code'] if annex_info else 'General'} ({annex_info['name'] if annex_info else ''})",
                f"- Word Count: {word_count}",
                "",
                "## Verbatim Text",
                full_text,
                ""
            ]

            if upstream:
                rag_lines.append("## Upstream Regulatory Mandate")
                for u in upstream:
                    rag_lines.append(f"- [{u['rel']}] {u['code']}: {u['title']} ({u['legal_force']})")
                rag_lines.append("")

            if downstream_amcs:
                rag_lines.append("## Acceptable Means of Compliance (Presumption of Compliance)")
                for a in downstream_amcs:
                    rag_lines.append(f"- {a['code']}: {a['title']}")
                rag_lines.append("")

            if downstream_gms:
                rag_lines.append("## Guidance Material (Explanatory Guidance)")
                for g in downstream_gms:
                    rag_lines.append(f"- {g['code']}: {g['title']}")
                rag_lines.append("")

            if outgoing_citations:
                rag_lines.append("## Direct Regulatory Citations (Cross-References)")
                for c in outgoing_citations:
                    rag_lines.append(f"- Cites {c['code']}: {c['title']}")
                rag_lines.append("")

            if incoming_citations:
                rag_lines.append(f"## Dependent Provisions ({len(incoming_citations)} Inbound Dependencies)")
                for i in incoming_citations[:8]:
                    rag_lines.append(f"- Cited by {i['code']}: {i['title']}")
                if len(incoming_citations) > 8:
                    rag_lines.append(f"- ...and {len(incoming_citations) - 8} more provisions")
                rag_lines.append("")

            if stakeholders:
                rag_lines.append("## Obligated Stakeholders")
                for s in stakeholders:
                    rag_lines.append(f"- {s['name']} ({s['role_type']}): {s['obligation']}")
                rag_lines.append("")

            if concepts:
                rag_lines.append("## Operational Concepts Governed")
                for c in concepts:
                    rag_lines.append(f"- {c['name']} ({c['category']})")
                rag_lines.append("")

            if similar_provisions:
                rag_lines.append("## Semantic Parallels across Regulations (SIMILAR_TO)")
                for sim in similar_provisions:
                    rag_lines.append(f"- [{sim['score_pct']}% Match] {sim['code']}: {sim['title']} ({sim['annex']}) - {sim['reason']}")
                rag_lines.append("")

            rag_md = "\n".join(rag_lines)
            return {
                "kind": "Provision",
                "id": prov_id,
                "code": prov_code,
                "base_code": base_code,
                "title": title,
                "content_type": c_type,
                "legal_force": legal_force,
                "subject": subject,
                "text": full_text,
                "full_text": full_text,
                "text_snippet": full_text[:300] if len(full_text) > 300 else full_text,
                "word_count": word_count,
                "annex": annex_info,
                "upstream": upstream,
                "upstream_rules": upstream,
                "downstream_amcs": downstream_amcs,
                "acceptable_means_of_compliance": downstream_amcs,
                "downstream_gms": downstream_gms,
                "guidance_material": downstream_gms,
                "outgoing_citations": outgoing_citations,
                "incoming_citations": incoming_citations,
                "stakeholders": stakeholders,
                "concepts": concepts,
                "similar_provisions": similar_provisions,
                "graph_rag_markdown": rag_md,
                "graphrag_context": rag_md
            }

        # 2. Check if it's an Annex
        clean_annex = clean_id.replace("ANNEX_", "").strip()
        res_a = self.conn.execute(f"""
            MATCH (a:Annex)
            WHERE a.id = '{identifier}' OR a.id = '{clean_id}'
               OR a.code = '{clean_annex}' OR a.name =~ '(?i).*{clean_annex}.*'
            RETURN a.id, a.code, a.name
            LIMIT 1;
        """)
        if res_a.has_next():
            a = res_a.get_next()
            res_cnt = self.conn.execute(f"""
                MATCH (p:Provision)-[:BELONGS_TO_ANNEX]->(a:Annex {{id: '{a[0]}'}})
                RETURN p.content_type, count(*)
            """)
            type_counts = {}
            while res_cnt.has_next():
                row = res_cnt.get_next()
                type_counts[row[0]] = row[1]

            annex_text = f"Regulatory Annex {a[1]}: {a[2]}. Contains {sum(type_counts.values())} codified provisions governing European air operations."
            rag_annex = [
                f"# EASA REGULATORY ANNEX: {a[1]} - {a[2]}",
                f"- Codified provisions: {sum(type_counts.values())}",
                "- Provisions breakdown: " + ", ".join(f"{k}: {v}" for k, v in type_counts.items()),
                "",
                "## Scope & Description",
                annex_text
            ]
            return {
                "kind": "Annex",
                "id": a[0],
                "code": a[1],
                "name": a[2],
                "title": f"Annex {a[1]}: {a[2]}",
                "content_type": "ANNEX",
                "type_breakdown": type_counts,
                "total_provisions": sum(type_counts.values()),
                "text": annex_text,
                "full_text": annex_text,
                "text_snippet": annex_text,
                "graph_rag_markdown": "\n".join(rag_annex),
                "graphrag_context": "\n".join(rag_annex)
            }

        # 3. Check if Concept
        clean_concept = clean_id.replace("CONCEPT_", "").replace("CON_", "").replace("_", " ").strip()
        res_con = self.conn.execute(f"""
            MATCH (c:Concept)
            WHERE c.id = '{identifier}' OR c.id = '{clean_id}'
               OR c.name =~ '(?i).*{clean_concept}.*'
            RETURN c.id, c.name, c.category
            LIMIT 1;
        """)
        if res_con.has_next():
            c = res_con.get_next()
            sub = self.get_concept_subgraph(c[1])
            c_text = f"Aviation Concept: {c[1]} (Category: {c[2]}). Governed across multiple EASA Annexes by {sub.get('total_governing_provisions', 0)} provisions."
            rag_concept = [
                f"# AVIATION CONCEPT: {c[1]}",
                f"- Category: {c[2]}",
                f"- Total governing provisions: {sub.get('total_governing_provisions', 0)}",
                "",
                "## Scope",
                c_text
            ]
            return {
                "kind": "Concept",
                "id": c[0],
                "code": c[1],
                "name": c[1],
                "title": f"Concept: {c[1]} ({c[2]})",
                "category": c[2],
                "content_type": "CONCEPT",
                "total_provisions": sub.get("total_governing_provisions", 0),
                "provisions_by_annex": sub.get("provisions_by_annex", {}),
                "text": c_text,
                "full_text": c_text,
                "text_snippet": c_text,
                "graph_rag_markdown": "\n".join(rag_concept),
                "graphrag_context": "\n".join(rag_concept)
            }

        # 4. Check Stakeholder
        clean_stk = clean_id.replace("STAKEHOLDER_", "").replace("STK_", "").replace("_", " ").strip()
        res_s = self.conn.execute(f"""
            MATCH (s:Stakeholder)
            WHERE s.id = '{identifier}' OR s.id = '{clean_id}'
               OR s.name =~ '(?i).*{clean_stk}.*'
            RETURN s.id, s.name, s.role_type
            LIMIT 1;
        """)
        if res_s.has_next():
            s = res_s.get_next()
            res_rules = self.conn.execute(f"""
                MATCH (p:Provision)-[r:APPLIES_TO]->(s:Stakeholder {{id: '{s[0]}'}})
                RETURN p.code, p.title, r.obligation
                LIMIT 20;
            """)
            rules = []
            while res_rules.has_next():
                row = res_rules.get_next()
                rules.append({"code": row[0], "title": row[1], "obligation": row[2]})

            stk_text = f"Regulated Stakeholder: {s[1]} ({s[2]}). Obligated across provisions within the Air Operations framework."
            rag_stk = [
                f"# AVIATION STAKEHOLDER: {s[1]}",
                f"- Role Type: {s[2]}",
                "",
                "## Regulatory Obligations",
                stk_text
            ]
            for r_item in rules[:10]:
                rag_stk.append(f"- {r_item['code']}: {r_item['title']} ({r_item['obligation']})")

            return {
                "kind": "Stakeholder",
                "id": s[0],
                "code": s[1],
                "name": s[1],
                "title": f"Stakeholder: {s[1]} ({s[2]})",
                "role_type": s[2],
                "content_type": "STAKEHOLDER",
                "sample_obligations": rules,
                "text": stk_text,
                "full_text": stk_text,
                "text_snippet": stk_text,
                "graph_rag_markdown": "\n".join(rag_stk),
                "graphrag_context": "\n".join(rag_stk)
            }

        return {"error": f"Node '{identifier}' not found in graph."}

    def find_compliance_path(self, source_code: str, target_code: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        Finds citation or hierarchical paths connecting two provisions.
        """
        query = f"""
            MATCH p = (a:Provision)-[:CROSS_REFERENCES*1..{max_depth}]->(b:Provision)
            WHERE (a.code = '{source_code}' OR a.base_code = '{source_code}')
              AND (b.code = '{target_code}' OR b.base_code = '{target_code}')
            RETURN [n IN nodes(p) | n.code] as path_codes
            LIMIT 5;
        """
        try:
            res = self.conn.execute(query)
            paths = []
            while res.has_next():
                paths.append(res.get_next()[0])
            return {
                "source": source_code,
                "target": target_code,
                "paths_found": len(paths),
                "paths": paths
            }
        except Exception as e:
            return {"error": str(e), "source": source_code, "target": target_code}

    def build_graph_rag_context(self, seed_codes: List[str]) -> str:
        """
        Takes seed codes (e.g. from vector search results) and expands their 1-hop
        compliance neighborhood into a clean, formatted structural context block.
        """
        context_parts = []
        for code in seed_codes:
            chain = self.get_compliance_chain(code)
            if "error" in chain:
                continue

            rule = chain["anchor_rule"]
            annex = chain["annex"]
            amcs = chain["acceptable_means_of_compliance"]
            gms = chain["guidance_material"]

            part = [
                f"### [REGULATION] {rule['code']} - {rule['title']}",
                f"**Legal Force:** {rule['legal_force']} (Implementing Rule)",
                f"**Annex:** {annex['code']} ({annex['name']})",
                f"**Mandatory Text:** {rule['text_snippet']}",
            ]

            if amcs:
                part.append("\n**Acceptable Means of Compliance (AMC - Presumption of Compliance):**")
                for amc in amcs[:2]:
                    part.append(f"- **{amc['code']}:** {amc['title']}")

            if gms:
                part.append("\n**Guidance Material (GM - Explanatory Context):**")
                for gm in gms[:2]:
                    part.append(f"- **{gm['code']}:** {gm['title']}")

            context_parts.append("\n".join(part))

        return "\n\n---\n\n".join(context_parts)
