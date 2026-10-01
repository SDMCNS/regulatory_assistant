"""Helper utilities for XML element manipulation and text processing."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from .constants import _BR


def _local(el: ET.Element) -> str | None:
    """Return local tag name stripped of XML namespace."""
    t = el.tag
    return t.rsplit("}", 1)[-1] if isinstance(t, str) else None


def _child(el: ET.Element | None, tag: str) -> ET.Element | None:
    """Return the first direct child element matching local tag name."""
    if el is None:
        return None
    for c in el:
        if _local(c) == tag:
            return c
    return None


def _children(el: ET.Element, tag: str) -> list[ET.Element]:
    """Return all direct child elements matching local tag name."""
    return [c for c in el if _local(c) == tag]


def _int(v: str | None, default: int = 1) -> int:
    """Convert string to integer or return default on failure."""
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _norm(s: str) -> str:
    """Collapse whitespace (incl. NBSP); keep explicit <BR/> as newline."""
    s = re.sub(r"\s+", " ", s)
    parts = [p.strip() for p in s.split(_BR)]
    return "\n".join(p for p in parts if p)


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    """Strip None, empty strings, empty lists, and empty dicts from dictionary."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _plain(el: ET.Element | None) -> str | None:
    """Raw text of an element, whitespace-normalised (for metadata extraction)."""
    if el is None:
        return None
    return _norm("".join(el.itertext())) or None


def _iso(date_el: ET.Element) -> str | None:
    """Normalize date element into ISO-like YYYY-MM-DD or YYYY-MM string."""
    raw = date_el.get("ISO") or "".join(date_el.itertext()).strip()
    raw = re.sub(r"\D", "", raw)
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if len(raw) == 6:
        return f"{raw[:4]}-{raw[4:]}"
    return raw or None


def _script(text: str, table: dict[str, str], marker: str) -> str:
    """Convert text using Unicode sub/superscript map, or fall back to marker."""
    t = text.strip()
    if not t:
        return ""
    if all(ch in table for ch in t):
        return "".join(table[ch] for ch in t)
    return f"{marker}{t}" if t.isalnum() else f"{marker}({t})"


def _wrap(s: str) -> str:
    """Wrap complex expressions in parentheses if not simple alphanumeric/punctuation."""
    return s if re.fullmatch(r"[\w.,]+", s) else f"({s})"
