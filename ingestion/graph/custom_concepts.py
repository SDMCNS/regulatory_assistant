"""
custom_concepts.py - Persistent Storage and Generation of User-Suggested Aviation Concepts.

Allows users to suggest, generate, and codify custom concept ontology meshes:
1. Discovers governing provisions across EASA Annexes using semantic & lexical matching.
2. Persists user-defined concepts to data/custom_concepts.json.
3. Merges custom concepts with native Kùzu graph taxonomy.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ingestion.core.config import settings

logger = logging.getLogger("custom_concepts")

CUSTOM_CONCEPTS_FILE = settings.DATA_DIR / "custom_concepts.json"
_file_lock = threading.Lock()


class CustomConceptManager:
    """Manages persistent storage and generation of user-suggested aviation concepts."""

    def __init__(self, storage_file: Optional[Path] = None):
        self.storage_file = Path(storage_file or CUSTOM_CONCEPTS_FILE)
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensures the storage file exists with valid JSON structure."""
        if not self.storage_file.exists():
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with _file_lock:
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump({"concepts": []}, f, indent=2)

    def load_all(self) -> List[Dict[str, Any]]:
        """Loads all custom concepts from disk."""
        self._ensure_storage()
        try:
            with _file_lock:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("concepts", [])
        except Exception as e:
            logger.error(f"Error loading custom concepts from {self.storage_file}: {e}")
            return []

    def save_all(self, concepts: List[Dict[str, Any]]) -> None:
        """Saves custom concepts list to disk atomically."""
        self._ensure_storage()
        try:
            with _file_lock:
                temp_file = self.storage_file.with_suffix(".tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump({"concepts": concepts}, f, indent=2, ensure_ascii=False)
                temp_file.replace(self.storage_file)
        except Exception as e:
            logger.error(f"Error saving custom concepts to {self.storage_file}: {e}")

    def get_concept(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Finds a custom concept by exact ID or name (case-insensitive)."""
        clean_id = identifier.strip().lower()
        concepts = self.load_all()
        for c in concepts:
            c_info = c.get("concept", {})
            if c_info.get("id", "").lower() == clean_id:
                return c
            if c_info.get("name", "").lower() == clean_id:
                return c
            if c.get("id", "").lower() == clean_id:
                return c
            if c.get("name", "").lower() == clean_id:
                return c
        return None

    def delete_concept(self, identifier: str) -> bool:
        """Removes a custom concept by ID or name."""
        clean_id = identifier.strip().lower()
        concepts = self.load_all()
        initial_len = len(concepts)
        filtered = [
            c for c in concepts
            if c.get("concept", {}).get("id", "").lower() != clean_id
            and c.get("concept", {}).get("name", "").lower() != clean_id
            and c.get("id", "").lower() != clean_id
            and c.get("name", "").lower() != clean_id
        ]
        if len(filtered) < initial_len:
            self.save_all(filtered)
            return True
        return False

    def generate_concept(
        self,
        name: str,
        category: Optional[str] = None,
        description: Optional[str] = None,
        eng: Optional[Any] = None,
        hyde: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generates and persists a new concept mesh by discovering governing provisions in Kùzu.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Concept name cannot be empty")

        # 1. Check if already exists in custom concepts
        existing = self.get_concept(clean_name)
        if existing:
            return existing

        # Generate ID
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', clean_name).strip('_').upper()
        concept_id = f"CONCEPT_CUSTOM_{slug}"

        # 2. Extract search terms
        stop_words = {
            "and", "the", "for", "with", "from", "into", "during", "under", "over",
            "operations", "operation", "requirements", "requirement", "procedures",
            "procedure", "management", "system", "systems", "general", "rules", "rule"
        }
        raw_tokens = re.findall(r'[a-zA-Z0-9\-]+', f"{clean_name} {description or ''}")
        keywords = [
            t.lower() for t in raw_tokens
            if len(t) > 2 and t.lower() not in stop_words
        ]
        if not keywords:
            keywords = [clean_name.lower()]

        # 3. Query Kùzu for governing provisions
        discovered_provs: Dict[str, Dict[str, Any]] = {}

        if eng is not None and getattr(eng, "conn", None) is not None:
            # Cypher keyword match
            for kw in keywords[:6]:
                safe_kw = kw.replace("'", "\\'")
                try:
                    res = eng.conn.execute(f"""
                        MATCH (p:Provision)
                        WHERE (contains(lower(p.title), '{safe_kw}') OR contains(lower(p.text), '{safe_kw}'))
                        AND p.content_type IN ['IR', 'AMC', 'GM', 'CS']
                        OPTIONAL MATCH (p)-[:BELONGS_TO_ANNEX]->(a:Annex)
                        RETURN p.id, p.code, p.title, p.subject, p.content_type, p.legal_force, a.code, a.name
                        LIMIT 25;
                    """)
                    while res.has_next():
                        row = res.get_next()
                        p_id, p_code, p_title, p_subj, p_ctype, p_force, a_code, a_name = row
                        annex = (a_code if a_code and a_code != "n/a" else None) or (p_subj if p_subj and p_subj != "n/a" else None) or "General"
                        relevance = 0.95 if safe_kw in (p_title or "").lower() else 0.75
                        if p_id not in discovered_provs or relevance > discovered_provs[p_id]["relevance"]:
                            discovered_provs[p_id] = {
                                "id": p_id,
                                "code": p_code,
                                "title": p_title,
                                "subject": p_subj,
                                "content_type": p_ctype,
                                "legal_force": p_force,
                                "relevance": relevance,
                                "annex_name": a_name or annex,
                                "annex": annex
                            }
                except Exception as e:
                    logger.warning(f"Error querying provisions for keyword '{kw}': {e}")

        # 4. Complement with HyDE semantic search if available
        if hyde is not None:
            try:
                hyde_query = f"{clean_name}. {description or ''}".strip()
                cands = hyde.search_candidates(hyde_query, top_k=20, active_sources={"EASA"})
                cand_list = cands.get("candidates") or cands.get("candidate_nodes") or []
                for cand in cand_list:
                    p_id = cand.get("id")
                    if p_id and p_id not in discovered_provs:
                        discovered_provs[p_id] = {
                            "id": p_id,
                            "code": cand.get("code", p_id),
                            "title": cand.get("title", ""),
                            "subject": cand.get("subject", ""),
                            "content_type": cand.get("content_type", "IR"),
                            "legal_force": cand.get("legal_force", "Hard Law"),
                            "relevance": round(float(cand.get("similarity_score", 0.70)), 2),
                            "annex_name": cand.get("annex", "General"),
                            "annex": cand.get("annex", "General")
                        }
            except Exception as e:
                logger.warning(f"HyDE complement error in concept generation: {e}")

        # 5. Group by Annex
        provisions_by_annex: Dict[str, List[Dict[str, Any]]] = {}
        for p in discovered_provs.values():
            annex = p.pop("annex", "General")
            if annex not in provisions_by_annex:
                provisions_by_annex[annex] = []
            provisions_by_annex[annex].append(p)

        # 6. Deduce Category if needed
        final_category = (category or "").strip()
        if not final_category:
            annex_counts = {ann: len(provs) for ann, provs in provisions_by_annex.items()}
            top_annex = max(annex_counts.keys(), key=lambda k: annex_counts[k]) if annex_counts else "General"
            if "CAT" in top_annex or "OPS" in top_annex:
                final_category = "Flight Operations"
            elif "ORO" in top_annex or "GEN" in top_annex:
                final_category = "Governance & Compliance"
            elif "CS" in top_annex or "AIR" in top_annex or "M" in top_annex:
                final_category = "Airworthiness & Certification"
            elif "FCL" in top_annex or "MED" in top_annex:
                final_category = "Personnel Licensing"
            elif "ADR" in top_annex:
                final_category = "Aerodromes & Ground Handling"
            else:
                final_category = "Operational Aviation Safety"

        total_provisions = sum(len(provs) for provs in provisions_by_annex.values())

        concept_obj = {
            "id": concept_id,
            "concept": {
                "id": concept_id,
                "name": clean_name,
                "category": final_category,
                "description": description or f"Aviation ontology concept for {clean_name}",
                "is_custom": True,
                "created_at": datetime.utcnow().isoformat()
            },
            "total_governing_provisions": total_provisions,
            "provisions_by_annex": provisions_by_annex,
            "is_custom": True
        }

        # Save to disk
        all_concepts = self.load_all()
        # Overwrite or append
        all_concepts = [c for c in all_concepts if c.get("concept", {}).get("id") != concept_id and c.get("id") != concept_id]
        all_concepts.append(concept_obj)
        self.save_all(all_concepts)

        return concept_obj


_custom_concept_manager: Optional[CustomConceptManager] = None


def get_custom_concept_manager() -> CustomConceptManager:
    """Singleton getter for custom concept manager."""
    global _custom_concept_manager
    if _custom_concept_manager is None:
        _custom_concept_manager = CustomConceptManager()
    return _custom_concept_manager
