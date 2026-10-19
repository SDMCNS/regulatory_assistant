"""
text_blocks.py - Required Document Text Blocks Extraction and Management.

Extracts all distinct (Document Title, Chapter/Section) references from stakeholder comments
and constructs the requirement checklist of text blocks the user must provide.
Matches existing uploaded documents and allows dynamic provision/editing of missing text blocks.
"""

from __future__ import annotations

import re
from typing import Dict, Any, List, Optional, Tuple


def normalize_identifier(text: str) -> str:
    """Normalizes document title and chapter/section for grouping."""
    return re.sub(r"[^\w\d]", "", (text or "").lower())


def find_matching_content_in_docs(
    doc_title: str,
    chapter_sec: str,
    documents: List[Dict[str, Any]]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Attempts to locate matching section content from uploaded consultation documents.
    Returns (matched_section_title, content_snippet).
    """
    if not documents:
        return None, None

    clean_sec = chapter_sec.lower().strip()
    sec_num_match = re.search(r"(?:article|art\.?|section|sec\.?|chapter|annex)\s*([0-9a-zivx\.\-]+)", clean_sec)
    sec_token = sec_num_match.group(1) if sec_num_match else None

    # Search in all documents
    for doc in documents:
        for sec in doc.get("sections", []):
            st_title = sec.get("title", "")
            st_lower = st_title.lower()

            # Exact or token match
            if sec_token and re.search(rf"\b{re.escape(sec_token)}\b", st_lower):
                return st_title, sec.get("content", "")

            if clean_sec in st_lower or st_lower in clean_sec:
                return st_title, sec.get("content", "")

    return None, None


def build_required_text_blocks(
    comments: List[Dict[str, Any]],
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Builds structured checklist of text blocks the user will need to provide,
    grouped by Document Title and Chapter/Section.
    """
    grouped_blocks: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for c in comments:
        raw_doc_title = (c.get("document_title") or c.get("matched_document_title") or "").strip()
        if not raw_doc_title or raw_doc_title.lower() in ["general", "none", "n/a", ""]:
            # If documents exist, default to first document's title
            if documents and documents[0].get("title"):
                raw_doc_title = documents[0].get("title", "Consultation Document")
            else:
                raw_doc_title = "Consultation Document"

        raw_sec = (c.get("chapter_section") or c.get("target_section") or "General / Whole Document").strip()
        key = (raw_doc_title, raw_sec)

        if key not in grouped_blocks:
            grouped_blocks[key] = {
                "document_title": raw_doc_title,
                "chapter_section": raw_sec,
                "pages": set(),
                "comment_ids": [],
                "organisations": set(),
                "categories": set(),
                "quoted_snippets": [],
                "has_critical_comments": False,
                "comment_count": 0,
            }

        block = grouped_blocks[key]
        block["comment_count"] += 1
        block["comment_ids"].append(c.get("comment_id"))

        if c.get("page"):
            block["pages"].add(str(c.get("page")).strip())

        org = c.get("organisation_name") or c.get("stakeholder_name")
        if org:
            block["organisations"].add(org)

        cat = c.get("stakeholder_category") or c.get("stakeholder_group")
        if cat:
            block["categories"].add(cat)

        orig_text = c.get("original_text", "").strip()
        if orig_text and len(orig_text) > 10 and orig_text not in block["quoted_snippets"]:
            if len(block["quoted_snippets"]) < 3:
                block["quoted_snippets"].append(orig_text)

        sentiment = c.get("sentiment", "")
        importance = c.get("importance", "").lower()
        if sentiment in ["Strongly Critical", "Concerned"] or importance in ["high", "critical", "mandatory"]:
            block["has_critical_comments"] = True

    # Assemble structured text block records
    result_blocks: List[Dict[str, Any]] = []
    block_counter = 1

    for (d_title, c_sec), b_data in grouped_blocks.items():
        block_id = f"BLOCK-{block_counter:03d}"
        block_counter += 1

        # Check if content exists in uploaded documents
        matched_title, matched_content = find_matching_content_in_docs(d_title, c_sec, documents)

        is_provided = bool(matched_content and len(matched_content.strip()) > 30)

        # Fallback snippet from original quoted text in comments if document not provided
        fallback_snippet = "\n---\n".join(b_data["quoted_snippets"]) if b_data["quoted_snippets"] else ""

        orgs_list = sorted(list(b_data["organisations"]))
        result_blocks.append({
            "block_id": block_id,
            "document_title": d_title,
            "chapter_section": c_sec,
            "page_references": sorted(list(b_data["pages"])),
            "comment_count": b_data["comment_count"],
            "comment_ids": b_data["comment_ids"],
            "commenting_organisations": orgs_list,
            "referencing_stakeholders": orgs_list,
            "stakeholder_categories": sorted(list(b_data["categories"])),
            "quoted_snippets": b_data["quoted_snippets"],
            "status": "provided" if is_provided else "missing",
            "content": matched_content if is_provided else fallback_snippet,
            "matched_document_title": matched_title or d_title,
            "criticality": "High" if b_data["has_critical_comments"] else "Normal",
            "action_required": "None (Text Available)" if is_provided else "User must provide / paste document text block",
        })

    # Sort blocks: missing first, then high criticality, then comment count descending
    result_blocks.sort(key=lambda b: (
        0 if b["status"] == "missing" else 1,
        0 if b["criticality"] == "High" else 1,
        -b["comment_count"]
    ))

    return result_blocks
