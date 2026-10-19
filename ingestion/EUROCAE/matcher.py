"""
Matcher and Curated Reading Material Resolver for EUROCAE Standards.

Identifies relevant European aviation standards (published and upcoming)
to surface as supporting follow-up reading materials for research reports,
chat answers, and regulatory queries, strictly respecting that standard contents
are not used as source text for factual answer synthesis.
"""

import re
from typing import List, Dict, Optional, Any

from .models import EurocaeReadingMaterial
from .storage import search_standards
from .acronyms import AVIATION_ACRONYMS


def formulate_match_rationale(std_dict: Dict[str, Any], query: str) -> str:
    """
    Formulates a clear, informative rationale for why this standard is recommended
    as supporting follow-up reading.
    """
    title = std_dict.get("title", "")
    expanded = std_dict.get("expanded_title", "")
    status = std_dict.get("status", "Published")
    domain = std_dict.get("domain", "")
    wg = std_dict.get("working_group", "")
    easa_ref = std_dict.get("easa_reference")
    pub_date = std_dict.get("publication_date", "")

    rationale_parts = []

    if easa_ref:
        rationale_parts.append(f"Linked to European regulatory framework: {easa_ref}.")
    elif "mops" in title.lower():
        rationale_parts.append("Defines Minimum Operational Performance Standards (MOPS) and test procedures for equipment compliance.")
    elif "masps" in title.lower():
        rationale_parts.append("Defines Minimum Aviation System Performance Standards (MASPS) for end-to-end operational capability.")
    elif "guidance" in title.lower() or "guide" in title.lower():
        rationale_parts.append("Industry engineering and safety assessment guidance supporting certification.")

    if status.lower() == "published":
        date_str = f" in {pub_date}" if pub_date else ""
        rationale_parts.append(f"Published industry standard{date_str}.")
    elif status.lower() in ("ongoing", "planned"):
        date_str = f" (target {pub_date})" if pub_date else ""
        rationale_parts.append(f"Active standard under development by {wg}{date_str}.")

    if not rationale_parts:
        rationale_parts.append(f"Applicable industry standard in the {domain} domain.")

    return " ".join(rationale_parts)


def find_supporting_standards(
    query: str,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 4
) -> List[EurocaeReadingMaterial]:
    """
    Finds relevant published and upcoming EUROCAE standards matching a query or
    consulted regulatory chunks. Returns structured EurocaeReadingMaterial items.
    """
    if not query:
        return []

    # 1. Search standards database
    candidates = search_standards(query, top_k=top_k * 3)

    # If few candidates found, try looking for acronyms or key aviation terms in query
    if len(candidates) < top_k:
        query_upper = query.upper()
        found_acronyms = [a for a in AVIATION_ACRONYMS if a in query_upper and len(a) >= 3]
        if found_acronyms:
            for acr in found_acronyms:
                extra = search_standards(acr, top_k=top_k)
                for item in extra:
                    if not any(c["standard_id"] == item["standard_id"] for c in candidates):
                        candidates.append(item)

    if not candidates:
        return []

    results: List[EurocaeReadingMaterial] = []

    # Calculate normalized relevance scores
    # FTS5 bm25_rank is negative (e.g. -5.2 is better than -1.1)
    best_rank = min((c.get("bm25_rank", 0.0) for c in candidates), default=-1.0)
    worst_rank = max((c.get("bm25_rank", 0.0) for c in candidates), default=0.0)

    for idx, c in enumerate(candidates[:top_k]):
        raw_bm25 = c.get("bm25_rank", 0.0)

        # Normalize score between 0.65 and 0.98
        if best_rank < worst_rank:
            norm = (worst_rank - raw_bm25) / (worst_rank - best_rank + 1e-6)
            score = 0.65 + (norm * 0.33)
        else:
            score = max(0.65, 0.95 - (idx * 0.05))

        rationale = formulate_match_rationale(c, query)

        item = EurocaeReadingMaterial(
            standard_id=c["standard_id"],
            reference=c["reference"],
            title=c["title"],
            expanded_title=c.get("expanded_title") or c["title"],
            status=c.get("status", "Published"),
            organization=c.get("organization", "EUROCAE"),
            working_group=c.get("working_group"),
            working_group_desc=c.get("working_group_desc"),
            domain=c.get("domain"),
            publication_date=c.get("publication_date"),
            easa_reference=c.get("easa_reference"),
            relevance_score=round(score, 3),
            match_rationale=rationale,
            is_supporting_only=True
        )
        results.append(item)

    return results
