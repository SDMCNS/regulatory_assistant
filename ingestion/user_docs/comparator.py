"""
comparator.py - On-Upload Search and Compare for Duplicates and Updates.

Compares an uploaded document against the database catalog:
- Detects exact duplicates (identical hash or verbatim text).
- Detects regulatory updates (newer edition, revision, or amendment of an existing standard).
- Identifies candidate predecessors for executive superseding or suppression.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ingestion.core.config import settings


# Authoritative aviation regulation identifier patterns
RE_REG_CODES = [
    # EU / EC regulations e.g. (EU) 2018/1139, Regulation 139/2014, (EC) No 216/2008
    re.compile(r"\b(?:(?:Regulation|Reg\.?)\s*)?\(?(?:EU|EC|EEC)\)?\s*(?:No\.?\s*)?(\d{1,4}\/\d{2,4}|\d{4}\/\d{1,4})\b", re.IGNORECASE),
    # EASA ED Decisions e.g. ED Decision 2021/015/R, Decision 2014/012/R
    re.compile(r"\bED\s+Decision\s+(\d{4}\/\d{3}\/R)\b", re.IGNORECASE),
    # EASA Certification Specifications e.g. CS-25, CS-E, CS-FSTD, AMC-20
    re.compile(r"\b(CS-(?:25|23|27|29|E|ETSO|FSTD(?:\(A\)|\(H\))?|ACNS|AWO|LSA|VLA|MMEL|GEN-MMEL|FCD|CCD|31GB|31HB|31TGB))\b", re.IGNORECASE),
    re.compile(r"\b(AMC-20)\b", re.IGNORECASE),
    # Aviation Implementing Rules & Parts e.g. Part-CAT, Part-ORO, Part-SPA, Part-M, Part-145, Part-CAMO, Part-21
    re.compile(r"\b(Part-(?:CAT|ORO|SPA|SPO|NCO|NCC|FCL|MED|DTO|ATO|CC|ARA|ORA|21|M|145|CAMO|CAO|66|147|T|ML|ADR))\b", re.IGNORECASE),
    # FAA 14 CFR Parts e.g. 14 CFR Part 25, Part 121, Part 91, Part 135
    re.compile(r"\b(?:14\s+CFR\s+)?(?:Part\s+)(\d+[A-Z]?)\b", re.IGNORECASE),
    # ICAO Annexes & Documents e.g. ICAO Annex 6, Doc 9859
    re.compile(r"\bICAO\s+(Annex\s+\d+|Doc\s+\d+)\b", re.IGNORECASE),
]


def extract_regulation_codes(text: str) -> List[str]:
    """Extracts distinctive aviation regulation identifiers from text and title."""
    codes: List[str] = []
    for pattern in RE_REG_CODES:
        for m in pattern.finditer(text):
            val = m.group(0).strip()
            # Normalize spaces and casing
            norm = re.sub(r"\s+", " ", val).upper()
            if norm not in codes:
                codes.append(norm)
    return codes


def normalize_title(title: str) -> str:
    """Normalizes title for similarity comparison."""
    t = (title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\b(the|and|or|of|for|on|in|to|with|an|a|is|by|easy|access|rules)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def calculate_title_similarity(t1: str, t2: str) -> float:
    """Calculates composite word Jaccard and SequenceMatcher similarity between titles."""
    n1 = normalize_title(t1)
    n2 = normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    # Jaccard on words
    w1 = set(n1.split())
    w2 = set(n2.split())
    jaccard = len(w1 & w2) / max(len(w1 | w2), 1)

    # Sequence matcher ratio
    seq_ratio = difflib.SequenceMatcher(None, n1, n2).ratio()

    # Blend 60% Jaccard, 40% SequenceMatcher
    return (0.6 * jaccard) + (0.4 * seq_ratio)


def search_and_compare_document(
    title: str,
    raw_text: str,
    sha256_hash: str,
    date_str: Optional[str] = None,
    pub_year: Optional[int] = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Searches the SQLite catalog and FTS index for duplicates or predecessors of the uploaded document.
    Categorizes matches as 'exact_duplicate', 'update', or 'similar'.
    Recommends executive action: 'supersede', 'suppress', or 'none'.
    """
    db_path = settings.SQLITE_PATH
    if not db_path.exists():
        return {
            "has_conflict": False,
            "suggested_action": "none",
            "suggested_target_doc_id": None,
            "matches": []
        }

    matches: List[Dict[str, Any]] = []
    reg_codes = extract_regulation_codes(f"{title}\n{raw_text[:8000]}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Exact SHA-256 Hash Check in documents metadata
        cursor.execute("""
            SELECT document_id, title, date, source, is_active, superseded_by, metadata_json 
            FROM documents 
            WHERE metadata_json LIKE ?
            LIMIT 5
        """, (f'%"sha256": "{sha256_hash}"%',))
        hash_rows = cursor.fetchall()
        for r in hash_rows:
            matches.append({
                "document_id": r["document_id"],
                "title": r["title"] or r["document_id"],
                "source": r["source"] or "Unknown",
                "date": r["date"] or "",
                "is_active": bool(r["is_active"] if r["is_active"] is not None else 1),
                "superseded_by": r["superseded_by"],
                "similarity_score": 1.0,
                "match_type": "exact_duplicate",
                "comparison_details": f"Exact cryptographic match (identical SHA-256 hash {sha256_hash[:12]}...)."
            })

        # 2. Regulation Code / Key Standard Query
        matched_doc_ids = {m["document_id"] for m in matches}
        for code in reg_codes:
            clean_code = code.replace("(", "").replace(")", "").strip()
            if len(clean_code) < 4:
                continue
            cursor.execute("""
                SELECT document_id, title, date, source, is_active, superseded_by, metadata_json 
                FROM documents 
                WHERE (title LIKE ? OR document_id LIKE ?)
                LIMIT 4
            """, (f"%{clean_code}%", f"%{clean_code}%"))
            for r in cursor.fetchall():
                doc_id = r["document_id"]
                if doc_id in matched_doc_ids:
                    continue
                matched_doc_ids.add(doc_id)

                sim = calculate_title_similarity(title, r["title"] or "")
                # Extract year from existing doc
                old_date = r["date"] or ""
                old_year = None
                ym = re.search(r"\b(19\d\d|20\d\d)\b", old_date + " " + (r["title"] or ""))
                if ym:
                    old_year = int(ym.group(1))

                is_newer = (pub_year is not None and old_year is not None and pub_year > old_year)
                is_same_year = (pub_year is not None and old_year is not None and pub_year == old_year)

                if is_newer:
                    m_type = "update"
                    detail = f"Shares regulatory standard '{clean_code}' with a newer publication date ({pub_year} vs {old_year})."
                    score = max(sim, 0.88)
                elif is_same_year and sim > 0.85:
                    m_type = "exact_duplicate"
                    detail = f"Shares regulatory standard '{clean_code}' from the same year ({pub_year}) with high title similarity."
                    score = max(sim, 0.90)
                else:
                    m_type = "update" if sim > 0.60 else "similar"
                    detail = f"Shares regulatory standard '{clean_code}' ({r['title'] or doc_id})."
                    score = max(sim, 0.75)

                matches.append({
                    "document_id": doc_id,
                    "title": r["title"] or doc_id,
                    "source": r["source"] or "Unknown",
                    "date": old_date,
                    "is_active": bool(r["is_active"] if r["is_active"] is not None else 1),
                    "superseded_by": r["superseded_by"],
                    "similarity_score": round(score, 3),
                    "match_type": m_type,
                    "comparison_details": detail
                })

        # 3. Catalog Title Scan (Fuzzy & Semantic Title Comparison)
        cursor.execute("""
            SELECT document_id, title, date, source, is_active, superseded_by 
            FROM documents
        """)
        all_docs = cursor.fetchall()
        for r in all_docs:
            doc_id = r["document_id"]
            if doc_id in matched_doc_ids:
                continue
            doc_title = r["title"] or ""
            sim = calculate_title_similarity(title, doc_title)

            if sim >= 0.70:
                matched_doc_ids.add(doc_id)
                old_date = r["date"] or ""
                ym = re.search(r"\b(19\d\d|20\d\d)\b", old_date + " " + doc_title)
                old_year = int(ym.group(1)) if ym else None

                if sim >= 0.95:
                    m_type = "exact_duplicate"
                    detail = f"Almost identical title match ({sim:.0%} similarity)."
                elif pub_year and old_year and pub_year > old_year:
                    m_type = "update"
                    detail = f"High title similarity ({sim:.0%}) with newer publication year ({pub_year} vs {old_year})."
                elif "amendment" in title.lower() or "revision" in title.lower() or "issue" in title.lower():
                    m_type = "update"
                    detail = f"High title similarity ({sim:.0%}) indicating an amendment or revised issue."
                else:
                    m_type = "similar"
                    detail = f"Significant title overlap ({sim:.0%} similarity)."

                matches.append({
                    "document_id": doc_id,
                    "title": doc_title or doc_id,
                    "source": r["source"] or "Unknown",
                    "date": old_date,
                    "is_active": bool(r["is_active"] if r["is_active"] is not None else 1),
                    "superseded_by": r["superseded_by"],
                    "similarity_score": round(sim, 3),
                    "match_type": m_type,
                    "comparison_details": detail
                })

    # Sort matches by similarity descending
    matches.sort(key=lambda m: (m["similarity_score"], 1 if m["match_type"] == "update" else 0), reverse=True)
    matches = matches[:top_k]

    # Executive recommendation
    suggested_action = "none"
    suggested_target_doc_id = None

    if matches:
        top_match = matches[0]
        if top_match["match_type"] == "update" and top_match["similarity_score"] >= 0.70:
            suggested_action = "supersede"
            suggested_target_doc_id = top_match["document_id"]
        elif top_match["match_type"] == "exact_duplicate" and top_match["similarity_score"] >= 0.90:
            suggested_action = "suppress"
            suggested_target_doc_id = top_match["document_id"]

    return {
        "has_conflict": len(matches) > 0 and matches[0]["similarity_score"] >= 0.70,
        "suggested_action": suggested_action,
        "suggested_target_doc_id": suggested_target_doc_id,
        "matches": matches
    }
