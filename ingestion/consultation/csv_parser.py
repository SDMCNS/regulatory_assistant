"""
csv_parser.py - Robust Parser and Column Mapper for Stakeholder Feedback CSVs.

Supports user-configurable field grouping and matching against the standard consultation template:
1. ID
2. Please select the document title from the drop down below
3. Chapter/Section
4. Page
5. Original text in document
6. Comment
7. Type of Comment
8. Importance
9. Proposed new text (required in case of change request)
10. Stakeholder Category
11. Organisation Name
12. AF / CBA
13. Response to comment
14. Rationale and resulting changes (if applicable)
15. Overall ID#
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


# Standard consultation template fields defined by the regulatory consultation workflow
CONSULTATION_TEMPLATE_FIELDS: List[Dict[str, Any]] = [
    {
        "key": "comment_id",
        "label": "ID",
        "description": "Unique comment or line identifier",
        "required": False,
        "aliases": ["id", "comment_id", "c_id", "comment_no", "comment_number", "no", "num", "item", "row_id"]
    },
    {
        "key": "document_title",
        "label": "Please select the document title from the drop down below",
        "description": "Consulted document title or regulatory text name",
        "required": True,
        "aliases": [
            "please select the document title from the drop down below",
            "document title",
            "document",
            "doc_title",
            "title",
            "consulted_document",
            "regulation",
            "doc"
        ]
    },
    {
        "key": "chapter_section",
        "label": "Chapter/Section",
        "description": "Target chapter, section, article, paragraph or AMC/GM reference",
        "required": True,
        "aliases": [
            "chapter/section",
            "chapter_section",
            "chapter",
            "section",
            "article",
            "paragraph",
            "target",
            "target_section",
            "ref",
            "provision",
            "amc",
            "gm",
            "rule_ref",
            "clause"
        ]
    },
    {
        "key": "page",
        "label": "Page",
        "description": "Page number in the consulted document draft",
        "required": False,
        "aliases": ["page", "page_no", "page_num", "p", "pg", "page_ref"]
    },
    {
        "key": "original_text",
        "label": "Original text in document",
        "description": "Quoted or cited original drafting text from the consulted document",
        "required": False,
        "aliases": [
            "original text in document",
            "original text",
            "original_text",
            "source_text",
            "quoted_text",
            "current_text",
            "draft_text",
            "text in document"
        ]
    },
    {
        "key": "comment_text",
        "label": "Comment",
        "description": "Substantive feedback, observation, or objection from stakeholder",
        "required": True,
        "aliases": [
            "comment",
            "feedback",
            "comment_text",
            "remarks",
            "content",
            "issue",
            "description",
            "observations",
            "stakeholder_comment"
        ]
    },
    {
        "key": "comment_type",
        "label": "Type of Comment",
        "description": "Classification (e.g. Change Request, Clarification, Endorsement, Editorial)",
        "required": False,
        "aliases": [
            "type of comment",
            "comment_type",
            "type",
            "category_of_comment",
            "nature_of_comment",
            "kind"
        ]
    },
    {
        "key": "importance",
        "label": "Importance",
        "description": "Importance or priority level (Critical, High, Medium, Low)",
        "required": False,
        "aliases": ["importance", "priority", "criticality", "severity", "level"]
    },
    {
        "key": "proposed_text",
        "label": "Proposed new text (required in case of change request)",
        "description": "Concrete alternative drafting wording or amendment proposal",
        "required": False,
        "aliases": [
            "proposed new text (required in case of change request)",
            "proposed new text",
            "proposed_text",
            "proposed_change",
            "suggestion",
            "alternative",
            "amendment",
            "revised_text",
            "text_change",
            "remedy",
            "proposal"
        ]
    },
    {
        "key": "stakeholder_category",
        "label": "Stakeholder Category",
        "description": "Industry sector or stakeholder category (Airline, Airport, ANSP, OEM, etc.)",
        "required": False,
        "aliases": [
            "stakeholder category",
            "stakeholder_category",
            "stakeholder_group",
            "category",
            "sector",
            "group",
            "stakeholder_type",
            "industry_sector"
        ]
    },
    {
        "key": "organisation_name",
        "label": "Organisation Name",
        "description": "Submitting organisation, company, authority, or association",
        "required": False,
        "aliases": [
            "organisation name",
            "organization name",
            "organisation",
            "organization",
            "stakeholder_name",
            "stakeholder",
            "company",
            "submitter",
            "author",
            "name",
            "entity"
        ]
    },
    {
        "key": "af_cba",
        "label": "AF / CBA (Internal)",
        "description": "Internal reference field only (not an Assessment Factor; ignored for evaluation)",
        "required": False,
        "aliases": [
            "af / cba",
            "af/cba",
            "cba",
            "af",
            "cost benefit",
            "feasibility",
            "cost_benefit_analysis",
            "impact_assessment",
            "regulatory_impact"
        ]
    },
    {
        "key": "response_to_comment",
        "label": "Response to comment",
        "description": "Rulemaker / agency disposition or preliminary response",
        "required": False,
        "aliases": [
            "response to comment",
            "response",
            "agency_response",
            "reply",
            "disposition",
            "easa_response",
            "drafter_response"
        ]
    },
    {
        "key": "rationale_and_changes",
        "label": "Rationale and resulting changes (if applicable)",
        "description": "Submitter reasoning, justification, and resulting changes",
        "required": False,
        "aliases": [
            "rationale and resulting changes (if applicable)",
            "rationale and resulting changes",
            "rationale",
            "reason",
            "justification",
            "resulting changes",
            "impact",
            "safety_justification",
            "economic_impact",
            "background"
        ]
    },
    {
        "key": "overall_id",
        "label": "Overall ID#",
        "description": "Master consultation reference index number",
        "required": False,
        "aliases": [
            "overall id#",
            "overall id",
            "overall_id",
            "master_id",
            "global_id",
            "reference_id",
            "consultation_ref"
        ]
    }
]


def normalize_header(header: str) -> str:
    """Normalizes header string for fuzzy alias matching."""
    return re.sub(r"[^\w]", "_", header.strip().lower()).strip("_")


def find_best_header_match(headers: List[str], aliases: List[str]) -> Optional[str]:
    """Finds best matching header from list of aliases."""
    normalized_map = {normalize_header(h): h for h in headers}

    # 1. Exact match against normalized alias
    for alias in aliases:
        norm_alias = normalize_header(alias)
        if norm_alias in normalized_map:
            return normalized_map[norm_alias]

    # 2. Substring match
    for norm_h, original_h in normalized_map.items():
        for alias in aliases:
            norm_alias = normalize_header(alias)
            if len(norm_alias) >= 3 and (norm_alias in norm_h or norm_h in norm_alias):
                return original_h

    return None


def detect_csv_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    """Maps CSV headers to canonical consultation fields using template definitions."""
    mapping: Dict[str, Optional[str]] = {}
    used_headers = set()

    for field in CONSULTATION_TEMPLATE_FIELDS:
        key = field["key"]
        matched = find_best_header_match([h for h in headers if h not in used_headers], field["aliases"])
        if matched:
            mapping[key] = matched
            used_headers.add(matched)
        else:
            mapping[key] = None

    # Backward compatibility mappings
    mapping["stakeholder_name"] = mapping.get("organisation_name")
    mapping["stakeholder_group"] = mapping.get("stakeholder_category")
    mapping["target_section"] = mapping.get("chapter_section")
    mapping["rationale"] = mapping.get("rationale_and_changes")

    return mapping


def detect_delimiter(csv_content: str) -> str:
    """Auto-detects CSV delimiter (tab, semicolon, or comma)."""
    sample = csv_content[:4096]
    tab_count = sample.count("\t")
    semi_count = sample.count(";")
    comma_count = sample.count(",")

    if tab_count > semi_count and tab_count > comma_count:
        return "\t"
    elif semi_count > comma_count:
        return ";"
    return ","


def inspect_feedback_csv(csv_content: str, delimiter: Optional[str] = None) -> Dict[str, Any]:
    """
    Inspects a feedback CSV file and returns detected headers, sample preview,
    and recommended mapping against the standard consultation template before user confirms.
    """
    if delimiter is None:
        delimiter = detect_delimiter(csv_content)

    f = io.StringIO(csv_content)
    reader = csv.reader(f, delimiter=delimiter)

    try:
        raw_headers = [h.strip() for h in next(reader) if h.strip()]
    except StopIteration:
        raise ValueError("CSV file is completely empty.")

    detected_mapping = detect_csv_columns(raw_headers)
    mapped_header_set = {v for v in detected_mapping.values() if v}
    unmapped_headers = [h for h in raw_headers if h not in mapped_header_set]

    # Read first 5 rows for preview
    sample_rows: List[Dict[str, str]] = []
    total_estimated_rows = 0

    for idx, row in enumerate(reader):
        total_estimated_rows += 1
        if idx < 5 and row and any(cell.strip() for cell in row):
            row_dict = {}
            for h_idx, h_name in enumerate(raw_headers):
                val = row[h_idx].strip() if h_idx < len(row) else ""
                row_dict[h_name] = val
            sample_rows.append(row_dict)

    return {
        "headers": raw_headers,
        "delimiter": delimiter,
        "detected_delimiter": delimiter,
        "template_fields": CONSULTATION_TEMPLATE_FIELDS,
        "detected_mapping": {k: v for k, v in detected_mapping.items() if v is not None},
        "suggested_mapping": {k: v for k, v in detected_mapping.items() if v is not None},
        "unmapped_headers": unmapped_headers,
        "sample_rows": sample_rows,
        "row_count": total_estimated_rows,
        "total_estimated_rows": total_estimated_rows,
    }


def infer_stakeholder_group(name: str, text: str) -> str:
    """Infers stakeholder sector if not provided in CSV."""
    combined = f"{name} {text}".lower()

    if any(k in combined for k in ["airline", "air operator", "carrier", "air france", "lufthansa", "easyjet", "ryanair", "iata", "era", "a4e"]):
        return "Air Operator / Airline"
    elif any(k in combined for k in ["aerodrome", "airport", "runway", "aci europe", "gatwick", "schiphol", "fraport"]):
        return "Aerodrome Operator"
    elif any(k in combined for k in ["airbus", "boeing", "embraer", "safran", "rolls-royce", "oem", "manufacturer", "design org"]):
        return "Manufacturer / OEM"
    elif any(k in combined for k in ["ansp", "atc", "air traffic", "canso", "eurocontrol", "enav", "nats", "dfs"]):
        return "Air Navigation Service Provider (ANSP)"
    elif any(k in combined for k in ["caa", "dgac", "enac", "faa", "easa", "authority", "regulator", "ministry", "aviation administration"]):
        return "National Aviation Authority (NAA) / Regulator"
    elif any(k in combined for k in ["pilot", "eca", "cockpit", "crew", "union", "association", "ifalpa", "atco", "guild"]):
        return "Pilots / Crew / Professional Union"
    elif any(k in combined for k in ["mro", "maintenance", "part-145", "technician"]):
        return "Maintenance / MRO"
    elif any(k in combined for k in ["general aviation", "aeroclub", "iaopa", "glider", "ultralight"]):
        return "General Aviation / Aerial Work"
    elif any(k in combined for k in ["ngo", "university", "academic", "institute", "environmental", "public"]):
        return "Public / Academic / NGO"
    else:
        return "Stakeholder / Industry"


def infer_target_section_from_text(text: str) -> str:
    """Attempts to extract referenced article/section from comment body if not provided."""
    patterns = [
        re.compile(r"\b(Article\s+\d+(?:\(\d+\))?(?:\([a-z]\))?)\b", re.IGNORECASE),
        re.compile(r"\b(AMC\d*\s+[A-Z0-9\.\-]+)\b", re.IGNORECASE),
        re.compile(r"\b(GM\d*\s+[A-Z0-9\.\-]+)\b", re.IGNORECASE),
        re.compile(r"\b(Section\s+\d+(?:\.\d+)*)\b", re.IGNORECASE),
        re.compile(r"\b(Part\-[A-Z0-9]+(?:\.[A-Z0-9]+)*)\b", re.IGNORECASE),
        re.compile(r"\b(Paragraph\s+\d+(?:\.\d+)*)\b", re.IGNORECASE),
        re.compile(r"\b(Annex\s+[IVX0-9]+)\b", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return "General / Whole Document"


def parse_feedback_csv_with_mapping(
    csv_content: str,
    column_mapping: Optional[Dict[str, str]] = None,
    delimiter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses stakeholder feedback CSV using user-confirmed or auto-detected field mappings.
    Returns standardized records aligned with the 15 template fields.
    """
    if delimiter is None:
        delimiter = detect_delimiter(csv_content)

    f = io.StringIO(csv_content)
    reader = csv.reader(f, delimiter=delimiter)

    try:
        raw_headers = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ValueError("CSV file is completely empty.")

    # If column mapping is not provided or incomplete, auto-detect
    detected = detect_csv_columns(raw_headers)
    final_mapping: Dict[str, Optional[str]] = dict(detected)

    if column_mapping:
        for k, v in column_mapping.items():
            if v and v in raw_headers:
                final_mapping[k] = v

    header_indices = {h: idx for idx, h in enumerate(raw_headers)}

    parsed_comments: List[Dict[str, Any]] = []

    for row_idx, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue

        def get_val(key_or_alias: str) -> str:
            col_name = final_mapping.get(key_or_alias)
            if col_name and col_name in header_indices:
                idx = header_indices[col_name]
                if idx < len(row):
                    return row[idx].strip()
            return ""

        # Primary fields
        raw_comment = get_val("comment_text")
        # If comment text was not mapped, fallback to longest cell
        if not raw_comment:
            longest_cell = max(row, key=len) if row else ""
            if len(longest_cell) > 10:
                raw_comment = longest_cell.strip()

        if not raw_comment:
            continue

        comment_id = get_val("comment_id") or get_val("overall_id") or f"CMT-{row_idx:03d}"
        doc_title = get_val("document_title") or "Consultation Document"
        chapter_section = get_val("chapter_section") or infer_target_section_from_text(raw_comment)
        page = get_val("page")
        original_text = get_val("original_text")
        comment_type = get_val("comment_type") or ("Change Request" if get_val("proposed_text") else "Observation")
        importance = get_val("importance") or "Medium"
        proposed_text = get_val("proposed_text")
        org_name = get_val("organisation_name") or "Stakeholder"
        category = get_val("stakeholder_category") or infer_stakeholder_group(org_name, raw_comment)
        af_cba = get_val("af_cba")
        response_to_comment = get_val("response_to_comment")
        rationale = get_val("rationale_and_changes")
        overall_id = get_val("overall_id") or comment_id

        parsed_comments.append({
            # Template fields
            "comment_id": comment_id,
            "document_title": doc_title,
            "chapter_section": chapter_section,
            "page": page,
            "original_text": original_text,
            "comment_text": raw_comment,
            "comment_type": comment_type,
            "importance": importance,
            "proposed_text": proposed_text,
            "stakeholder_category": category,
            "organisation_name": org_name,
            "af_cba": af_cba,
            "response_to_comment": response_to_comment,
            "rationale_and_changes": rationale,
            "overall_id": overall_id,
            # Backward-compatible aliases
            "stakeholder_name": org_name,
            "stakeholder_group": category,
            "target_section": chapter_section,
            "rationale": rationale,
            "row_index": row_idx,
        })

    mapping_summary = {
        "total_rows": len(parsed_comments),
        "applied_mapping": {k: v for k, v in final_mapping.items() if v is not None},
        "delimiter_used": delimiter,
        "template_field_count": len(CONSULTATION_TEMPLATE_FIELDS)
    }

    return parsed_comments, mapping_summary


def parse_feedback_csv(
    csv_content: str,
    delimiter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Backward-compatible entry point for existing code."""
    return parse_feedback_csv_with_mapping(csv_content, column_mapping=None, delimiter=delimiter)
