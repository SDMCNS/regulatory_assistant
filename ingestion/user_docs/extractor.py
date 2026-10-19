"""
extractor.py - Text and Metadata Extractor for User-Supplied Documents.

Extracts text, page boundaries, title, publication date, and cryptographic hash
from PDF, Markdown, Plain Text, HTML, and other file types.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .word_parser import (
    extract_word_doc,
    extract_word_docx,
    is_word_binary_doc,
    is_word_docx,
)


RE_DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD
    re.compile(r"\b(20\d{2}|19\d{2})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b"),
    # DD.MM.YYYY or DD/MM/YYYY
    re.compile(r"\b(0[1-9]|[12]\d|3[01])[-/.](0[1-9]|1[0-2])[-/.](20\d{2}|19\d{2})\b"),
    # DD Month YYYY (e.g. 15 July 2024 or 15.Jul.2024)
    re.compile(r"\b(0?[1-9]|[12]\d|3[01])[\s.](Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[\s.,]+(20\d{2}|19\d{2})\b", re.IGNORECASE),
    # Month YYYY (e.g. November 2025)
    re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[\s,]+(20\d{2}|19\d{2})\b", re.IGNORECASE),
    # Year alone in context (e.g. Issue 2024, Ed. 2023, Revision 2026)
    re.compile(r"\b(?:Issue|Edition|Revision|Rev|Year|Date|Amdt)?\s*(20\d{2})\b", re.IGNORECASE),
]


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(256 * 1024):
            h.update(chunk)
    return h.hexdigest()


def extract_date_from_text(text: str) -> Tuple[Optional[str], Optional[int]]:
    """Extracts first valid date and 4-digit publication year from text."""
    # Search first 15000 characters
    head = text[:15000]
    for pattern in RE_DATE_PATTERNS:
        m = pattern.search(head)
        if m:
            matched_str = m.group(0).strip()
            # Find the 4-digit year in the match
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", matched_str)
            year = int(year_match.group(1)) if year_match else None
            return matched_str, year

    # Fallback: search for any standalone 4-digit year between 1970 and 2035
    ym = re.search(r"\b(19[7-9]\d|20[0-3]\d)\b", head)
    if ym:
        y = int(ym.group(1))
        return str(y), y

    return None, None


def clean_title_candidate(candidate: str, fallback_filename: str) -> str:
    """Sanitizes candidate title string."""
    candidate = re.sub(r"^#+\s*", "", candidate).strip()
    candidate = re.sub(r"^---\s*PAGE\s+\d+\s*---\s*", "", candidate).strip()
    candidate = candidate.replace("\n", " ").strip()
    if len(candidate) > 200:
        candidate = candidate[:200].rsplit(" ", 1)[0] + "..."
    if len(candidate) < 3 or candidate.isdigit():
        return Path(fallback_filename).stem.replace("_", " ").replace("-", " ").title()
    return candidate


def extract_user_document(
    file_path: Path,
    filename: str,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    extract_diagrams: bool = True
) -> Dict[str, Any]:
    """
    Extracts text, pages, title, date, and metrics from a user-supplied file.
    Supports PDF, Word (.doc / .docx), Markdown, Plain Text, HTML, and XML.
    Returns:
        {
            "raw_text": str,
            "title": str,
            "date": Optional[str],
            "year": Optional[int],
            "page_count": int,
            "word_count": int,
            "char_count": int,
            "sha256": str,
            "is_pdf": bool,
            "is_word": bool,
            "word_format": Optional[str],
            "author": Optional[str],
            "filename": str
        }
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()
    sha256_hash = compute_sha256(file_path)

    raw_text = ""
    title_candidate = None
    page_count = 1
    author = None
    doc_date = None
    is_word = False
    word_format = None

    detected_diagrams_list: List[Dict[str, Any]] = []

    if ext == ".pdf" and fitz is not None:
        try:
            doc = fitz.open(file_path)
            page_count = doc.page_count
            pages_text: List[str] = []

            meta = doc.metadata or {}
            pdf_meta_title = (meta.get("title") or "").strip()
            if pdf_meta_title and len(pdf_meta_title) > 3 and not pdf_meta_title.lower().startswith("untitled"):
                title_candidate = pdf_meta_title
            author = meta.get("author") or None

            first_page_lines: List[str] = []

            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                p_text = page.get_text("text").strip()
                if page_idx == 0:
                    first_page_lines = [l.strip() for l in p_text.splitlines() if l.strip()]

                # Visual Graphic & Diagram Detection and Gemini HyDE Summarizer
                if extract_diagrams:
                    try:
                        from .diagram_extractor import detect_page_graphics, generate_diagram_hyde_summary
                        page_graphics = detect_page_graphics(page, page_idx + 1)
                        if page_graphics:
                            for g in page_graphics:
                                hyde_summary = generate_diagram_hyde_summary(
                                    graphic_info=g,
                                    doc_title=title_candidate or Path(filename).stem,
                                    api_key=gemini_api_key,
                                    preferred_model=gemini_model
                                )
                                if hyde_summary:
                                    p_text += f"\n\n{hyde_summary}\n"
                                    detected_diagrams_list.append({
                                        "page": page_idx + 1,
                                        "figure_id": g.get("figure_id"),
                                        "type": g.get("graphic_type"),
                                        "caption": g.get("nearby_caption"),
                                        "summary_snippet": hyde_summary[:200] + "..." if len(hyde_summary) > 200 else hyde_summary
                                    })
                    except Exception as diag_err:
                        print(f"[Diagram Extractor Warning] Page {page_idx + 1}: {diag_err}")

                pages_text.append(f"--- PAGE {page_idx + 1} ---\n{p_text}")

            raw_text = "\n\n".join(pages_text)

            if not title_candidate and first_page_lines:
                for line in first_page_lines[:6]:
                    if len(line) > 4 and not line.isdigit() and not line.startswith("http"):
                        title_candidate = line
                        break

        except Exception as e:
            raw_text = f"Error reading PDF: {e}"

    elif ext in (".doc", ".dot") or is_word_binary_doc(file_path):
        # Legacy Microsoft Word 97-2003 (.doc) binary format
        is_word = True
        word_format = "doc"
        try:
            doc_res = extract_word_doc(file_path)
            raw_text = doc_res["raw_text"]
            title_candidate = doc_res.get("title")
            author = doc_res.get("author")
            doc_date = doc_res.get("created_date")
            page_count = doc_res.get("page_count", 1)

            if not title_candidate and raw_text:
                first_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
                if first_lines:
                    title_candidate = first_lines[0]
        except Exception as e:
            raw_text = f"Error reading Word .doc: {e}"

    elif ext in (".docx", ".dotx") or is_word_docx(file_path):
        # Modern Microsoft Word OpenXML (.docx) format
        is_word = True
        word_format = "docx"
        try:
            docx_res = extract_word_docx(file_path)
            raw_text = docx_res["raw_text"]
            title_candidate = docx_res.get("title")
            author = docx_res.get("author")
            doc_date = docx_res.get("created_date")
            page_count = docx_res.get("page_count", 1)

            if not title_candidate and raw_text:
                for line in raw_text.splitlines():
                    clean_line = line.strip()
                    if clean_line.startswith("# "):
                        title_candidate = clean_line[2:].strip()
                        break
                    elif clean_line and not title_candidate:
                        title_candidate = clean_line
        except Exception as e:
            raw_text = f"Error reading Word .docx: {e}"

    else:
        # Text, Markdown, HTML, XML, etc.
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
        except Exception as e:
            raw_text = f"Error reading file: {e}"

        # Markdown header extraction
        md_match = re.search(r"^#\s+(.+)$", raw_text, re.MULTILINE)
        if md_match:
            title_candidate = md_match.group(1).strip()
        else:
            first_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            if first_lines:
                title_candidate = first_lines[0]

    final_title = clean_title_candidate(title_candidate or "", filename)
    extracted_date, pub_year = extract_date_from_text(raw_text)
    final_date = doc_date or extracted_date

    # If pub_year was not found from regex but doc_date is YYYY-MM-DD
    if pub_year is None and final_date:
        ym = re.search(r"\b(19\d\d|20\d\d)\b", final_date)
        if ym:
            pub_year = int(ym.group(1))

    word_count = len(re.findall(r"\b\w+\b", raw_text))
    char_count = len(raw_text)

    return {
        "raw_text": raw_text,
        "title": final_title,
        "date": final_date,
        "year": pub_year,
        "page_count": page_count,
        "word_count": word_count,
        "char_count": char_count,
        "sha256": sha256_hash,
        "is_pdf": ext == ".pdf",
        "is_word": is_word,
        "word_format": word_format,
        "author": author,
        "filename": filename,
        "diagrams_detected": len(detected_diagrams_list),
        "diagrams": detected_diagrams_list
    }

