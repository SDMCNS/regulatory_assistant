"""
furniture.py - Boilerplate, Header, and Footer Cleaning for Skybrary PDFs.

Removes repeated headers, running footers, page numbering lines, and legal boilerplate
to ensure clean text in chunks and embedding texts.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple


# Regexes for common isolated header/footer patterns
PAGE_NUMBER_RE = re.compile(
    r"^(?:(?:page|p\.)\s*)?\d+(?:\s*(?:of|/)\s*\d+)?$",
    re.IGNORECASE,
)

ELI_FOOTER_RE = re.compile(
    r"^.*(?:ELI:\s*http://data\.europa\.eu/eli/|OJ\s+[L|C]\s*,\s*\d+\.\d+\.\d+).*$",
    re.IGNORECASE,
)

EASA_FOOTER_RE = re.compile(
    r"^.*(?:TE\.SDIR\.\d+|European Union Aviation Safety Agency|Confirm revision status through|An agency of the European Union|Proprietary document\.\s*Copies are not controlled).*$",
    re.IGNORECASE,
)

FSF_FOOTER_RE = re.compile(
    r"^.*(?:FLIGHT SAFETY FOUNDATION\s*\||SAFETY FORUM \d+ REPORT).*$",
    re.IGNORECASE,
)

FAA_TC_FOOTER_RE = re.compile(
    r"^.*(?:Original Issue\s+Page\s+\d+\s+of\s+\d+|Aviation Safety\s*/\s*Safety Information|Distributed by:\s*Flight Standards).*$",
    re.IGNORECASE,
)

AUTHOR_LINE_RE = re.compile(
    r"^(?:Jacques Leroux,\s*Ph\.D\.|April \d{4}\.\s*Sixth issue October \d{4}\.)$",
    re.IGNORECASE,
)


def is_furniture_line(line: str) -> bool:
    """Returns True if an individual line matches known boilerplate/footer signatures."""
    s = line.strip()
    if not s:
        return False

    if PAGE_NUMBER_RE.match(s):
        return True
    if ELI_FOOTER_RE.match(s):
        return True
    if EASA_FOOTER_RE.match(s):
        return True
    if FSF_FOOTER_RE.match(s):
        return True
    if FAA_TC_FOOTER_RE.match(s):
        return True
    if AUTHOR_LINE_RE.match(s):
        return True

    return False


def clean_page_furniture(page_text: str) -> str:
    """Cleans furniture from an individual page."""
    lines = page_text.split("\n")
    cleaned: List[str] = []

    for line in lines:
        if is_furniture_line(line):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def strip_document_furniture(pages: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """
    Two-pass document-level furniture stripper:
    1. Analyzes repeating top lines (headers) and bottom lines (footers) across all pages.
    2. Removes lines that repeat verbatim across multiple pages (>= 3 times), as well
       as known regulatory footer patterns.
    """
    if len(pages) <= 1:
        # For single page, apply pattern cleaner only
        return [(num, clean_page_furniture(text)) for num, text in pages]

    # Count frequencies of first 2 and last 3 non-empty lines on each page
    top_counter: Counter[str] = Counter()
    bottom_counter: Counter[str] = Counter()

    for _, text in pages:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            continue
        # Check top candidates
        for l in lines[:2]:
            if len(l) < 120:  # Headers are rarely massive blocks
                top_counter[l] += 1
        # Check bottom candidates
        for l in lines[-3:]:
            bottom_counter[l] += 1

    # Repeating threshold: appears on at least 3 pages or >30% of pages
    threshold = max(3, int(len(pages) * 0.3))
    repeating_headers = {l for l, count in top_counter.items() if count >= threshold}
    repeating_footers = {l for l, count in bottom_counter.items() if count >= threshold}

    cleaned_pages: List[Tuple[int, str]] = []

    for num, text in pages:
        lines = text.split("\n")
        page_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                page_lines.append(line)
                continue

            # Check if repeating header/footer or matches known patterns
            if stripped in repeating_headers or stripped in repeating_footers:
                continue
            if is_furniture_line(stripped):
                continue

            page_lines.append(line)

        cleaned_pages.append((num, "\n".join(page_lines)))

    return cleaned_pages
