"""
detector.py - Format Detection for User-Supplied Documents.

Classifies uploaded documents into:
1. EASA_XML: EASA Easy Access Rules XML export
2. EU_FORMEX_XML: European Union Formex XML standard (EUR-Lex)
3. FAA_CFR_XML: US FAA 14 CFR XML volume / part export
4. USER_SKYBRARY: General user-supplied documents (PDF, TXT, MD, HTML, DOCX, etc.)
   processed via the standard Skybrary extraction and chunking workflow.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET


class DocFormat(str, Enum):
    EASA_XML = "easa_xml"
    EU_FORMEX_XML = "eu_formex_xml"
    FAA_CFR_XML = "faa_cfr_xml"
    USER_SKYBRARY = "user_skybrary"


def is_xml_file(file_path: Path, filename: str) -> bool:
    """Checks whether the file has an XML extension or starts with an XML declaration."""
    if filename.lower().endswith(".xml"):
        return True
    try:
        with open(file_path, "rb") as f:
            header = f.read(1024)
            return b"<?xml" in header or b"<html" not in header and (header.strip().startswith(b"<") and b">" in header)
    except Exception:
        return False


def detect_document_format(file_path: Path, filename: str) -> Dict[str, Any]:
    """
    Inspects file structure, content sample, and XML namespaces/tags to detect format.
    Returns format classification, human-readable workflow name, and detection rationale.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Non-XML files automatically follow the Skybrary workflow
    if not is_xml_file(file_path, filename):
        ext = file_path.suffix.lower().lstrip(".") or "document"
        return {
            "format": DocFormat.USER_SKYBRARY.value,
            "workflow": "Skybrary Workflow (User Supplied)",
            "category": "User Supplied",
            "origin": "user",
            "is_xml": False,
            "detection_reason": f"Standard {ext.upper()} document ingested via Skybrary extraction, chunking, and embedding pipeline."
        }

    # Inspect XML header and namespaces
    try:
        with open(file_path, "rb") as f:
            sample_bytes = f.read(128 * 1024)  # Read up to 128KB
            sample_str = sample_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return {
            "format": DocFormat.USER_SKYBRARY.value,
            "workflow": "Skybrary Workflow (User Supplied)",
            "category": "User Supplied",
            "origin": "user",
            "is_xml": True,
            "detection_reason": f"Failed reading XML header ({e}); fallback to Skybrary pipeline."
        }

    sample_lower = sample_str.lower()

    # 1. Detect EASA XML
    # EASA Easy Access Rules XML export uses erules-export namespace or OpenXML package with erules SDTs
    if (
        "easa.europa.eu/erules-export" in sample_lower
        or "erules-export" in sample_lower
        or "<er:topic" in sample_lower
        or ("erulesid=" in sample_lower and "typeofcontent=" in sample_lower)
        or ("openxmlformats.org/wordprocessingml" in sample_lower and "easy access rules" in sample_lower)
        or ("easa.europa.eu" in sample_lower and ("easyaccess" in sample_lower or "rules" in sample_lower or "erules" in sample_lower))
        or "<easa:easyaccess" in sample_lower
    ):
        return {
            "format": DocFormat.EASA_XML.value,
            "workflow": "EASA XML Workflow",
            "category": "EASA",
            "origin": "easa",
            "is_xml": True,
            "detection_reason": "Matches EASA Easy Access Rules XML namespace (easa.europa.eu/erules-export) and structural SDT topics."
        }

    # 2. Detect EU Formex XML
    # European Union Formex format (EUR-Lex standards, Formex DTD / schema, ACT / ENV.DOC / FORMEX root)
    if (
        "formex.publications.europa.eu" in sample_lower
        or "formex.dtd" in sample_lower
        or ("formex" in sample_lower and "<bib.instance>" in sample_lower)
        or ("<act" in sample_lower and ("<bib.instance>" in sample_lower or "<document.ref>" in sample_lower or "<enacting.terms>" in sample_lower))
        or re.search(r"<(act|env\.doc|formex|doc\.main)[\s>]", sample_lower) and ("<bib.instance>" in sample_lower or "<enacting.terms>" in sample_lower or "<preamble>" in sample_lower)
    ):
        return {
            "format": DocFormat.EU_FORMEX_XML.value,
            "workflow": "EU Formex XML Workflow",
            "category": "EU",
            "origin": "eu",
            "is_xml": True,
            "detection_reason": "Matches EU Formex XML schema / DTD standard with Formex legal structure (<BIB.INSTANCE>, <ENACTING.TERMS>)."
        }

    # 3. Detect FAA 14 CFR XML
    # GPO Code of Federal Regulations XML for Title 14
    if (
        "<cfrdoc" in sample_lower
        or "<cfrtitle" in sample_lower
        or ("<part>" in sample_lower and "<ear>pt." in sample_lower and ("14" in sample_lower or "cfr" in sample_lower))
        or ("<title>14</title>" in sample_lower and ("<part" in sample_lower or "<cfr" in sample_lower))
        or ("cfr" in sample_lower and "gpo.gov" in sample_lower)
    ):
        return {
            "format": DocFormat.FAA_CFR_XML.value,
            "workflow": "FAA CFR XML Workflow",
            "category": "FAA",
            "origin": "faa",
            "is_xml": True,
            "detection_reason": "Matches US Government Publishing Office (GPO) Code of Federal Regulations Title 14 XML format."
        }

    # 4. Default XML: Process as generic XML document via Skybrary workflow
    return {
        "format": DocFormat.USER_SKYBRARY.value,
        "workflow": "Skybrary Workflow (User Supplied)",
        "category": "User Supplied",
        "origin": "user",
        "is_xml": True,
        "detection_reason": "General XML file not matching specific EU Formex, EASA, or FAA schemas; routed to Skybrary text ingestion workflow."
    }
