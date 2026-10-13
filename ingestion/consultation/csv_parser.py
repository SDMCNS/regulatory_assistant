"""
csv_parser.py - Robust Parser and Column Mapper for Stakeholder Feedback CSVs.

Handles various consultation feedback spreadsheet formats (e.g. EASA CRT, FAA Regulations.gov,
ICAO state letters, UK CAA, custom public comment spreadsheets).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


# Standard column aliases for consultation feedback
ALIASES_COMMENT_ID = ["comment_id", "id", "c_id", "comment_no", "comment_number", "no", "num", "ref_no", "item"]
ALIASES_STAKEHOLDER = ["stakeholder", "stakeholder_name", "organization", "organisation", "submitter", "author", "company", "name", "entity"]
ALIASES_GROUP = ["group", "category", "stakeholder_group", "stakeholder_type", "type", "sector", "industry_sector"]
ALIASES_SECTION = ["section", "article", "paragraph", "target", "target_section", "ref", "provision", "topic", "amc", "gm", "rule_ref", "page_ref", "chapter"]
ALIASES_COMMENT = ["comment", "feedback", "text", "comment_text", "remarks", "content", "issue", "description", "observations"]
ALIASES_PROPOSED_TEXT = ["proposed_text", "proposed_change", "suggestion", "alternative", "amendment", "revised_text", "text_change", "remedy"]
ALIASES_RATIONALE = ["rationale", "reason", "justification", "impact", "safety_justification", "economic_impact", "background"]


def normalize_header(header: str) -> str:
    """Normalizes header string for fuzzy alias matching."""
    return re.sub(r"[^\w]", "_", header.strip().lower()).strip("_")


def find_column_match(headers: List[str], aliases: List[str]) -> Optional[str]:
    """Finds best matching header from list of aliases."""
    normalized_map = {normalize_header(h): h for h in headers}

    # 1. Exact match
    for alias in aliases:
        if alias in normalized_map:
            return normalized_map[alias]

    # 2. Substring match
    for norm_h, original_h in normalized_map.items():
        for alias in aliases:
            if alias in norm_h:
                return original_h

    return None


def detect_csv_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    """Maps CSV headers to canonical consultation fields."""
    return {
        "comment_id": find_column_match(headers, ALIASES_COMMENT_ID),
        "stakeholder_name": find_column_match(headers, ALIASES_STAKEHOLDER),
        "stakeholder_group": find_column_match(headers, ALIASES_GROUP),
        "target_section": find_column_match(headers, ALIASES_SECTION),
        "comment_text": find_column_match(headers, ALIASES_COMMENT),
        "proposed_text": find_column_match(headers, ALIASES_PROPOSED_TEXT),
        "rationale": find_column_match(headers, ALIASES_RATIONALE),
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
    # Look for Article X, Section X, AMC X, GM X, Paragraph X
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


def parse_feedback_csv(
    csv_content: str,
    delimiter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses stakeholder feedback CSV and returns standardized records + metadata.
    """
    # Detect delimiter if not given
    if delimiter is None:
        sample = csv_content[:4096]
        if "\t" in sample and sample.count("\t") > sample.count(","):
            delimiter = "\t"
        elif ";" in sample and sample.count(";") > sample.count(","):
            delimiter = ";"
        else:
            delimiter = ","

    f = io.StringIO(csv_content)
    reader = csv.reader(f, delimiter=delimiter)

    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ValueError("CSV file is completely empty.")

    col_map = detect_csv_columns(raw_headers)

    # If comment_text is still None, pick the longest text column or first column with text
    header_indices = {h: idx for idx, h in enumerate(raw_headers)}

    parsed_comments: List[Dict[str, Any]] = []

    for row_idx, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue

        def get_val(col_key: str) -> str:
            col_name = col_map.get(col_key)
            if col_name and col_name in header_indices:
                idx = header_indices[col_name]
                if idx < len(row):
                    return row[idx].strip()
            return ""

        raw_comment = get_val("comment_text")

        # If comment text was not mapped, pick the column with the highest length in this row
        if not raw_comment:
            longest_cell = max(row, key=len) if row else ""
            if len(longest_cell) > 10:
                raw_comment = longest_cell.strip()

        if not raw_comment:
            continue

        comment_id = get_val("comment_id") or f"CMT-{row_idx:03d}"
        stakeholder_name = get_val("stakeholder_name") or "Stakeholder"
        stakeholder_group = get_val("stakeholder_group") or infer_stakeholder_group(stakeholder_name, raw_comment)
        target_section = get_val("target_section") or infer_target_section_from_text(raw_comment)
        proposed_text = get_val("proposed_text")
        rationale = get_val("rationale")

        parsed_comments.append({
            "comment_id": comment_id,
            "stakeholder_name": stakeholder_name,
            "stakeholder_group": stakeholder_group,
            "target_section": target_section,
            "comment_text": raw_comment,
            "proposed_text": proposed_text,
            "rationale": rationale,
            "row_index": row_idx,
        })

    mapping_summary = {
        "total_rows": len(parsed_comments),
        "detected_columns": {k: v for k, v in col_map.items() if v is not None},
        "delimiter_used": delimiter,
    }

    return parsed_comments, mapping_summary
