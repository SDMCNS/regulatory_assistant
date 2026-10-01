"""Plain-text rendering for parsed Formex documents and blocks."""
from __future__ import annotations

from typing import Any

Block = dict[str, Any]


def _body_of(b: Block) -> str:
    """Extract and format the inner body text of a block."""
    if "content" in b:
        return "\n".join(x for x in (render_block(c) for c in b["content"]) if x)
    return b.get("text", "")


def render_block(b: Block) -> str:
    """Render a single block into formatted plain text."""
    t = b.get("type", "")
    if t in ("text", "heading"):
        return b.get("text", "") if t == "text" else "\n".join(
            x for x in (b.get("text"), b.get("subtitle")) if x)
    if t in ("article", "section", "division", "subdivision"):
        head = " \u2014 ".join(x for x in (b.get("number"), b.get("title"),
                                           b.get("subtitle")) if x)
        return "\n".join(x for x in (head, _body_of(b)) if x)
    if t in ("paragraph", "item"):
        return " ".join(x for x in (b.get("number"), _body_of(b)) if x)
    if t == "list":
        dash = b.get("style") in ("dash", "ndash", "bullet")
        lines = []
        for it in b.get("items", []):
            line = render_block(it)
            lines.append(f"- {line}" if dash and not it.get("number") else line)
        return "\n".join(lines)
    if t == "definition_list":
        return "\n".join(f"{i.get('term', '')}: {i.get('definition', '')}".strip(": ")
                         for i in b.get("items", []))
    if t == "table":
        rows = b.get("header", []) + b.get("rows", [])
        lines = [" | ".join(r) for r in rows]
        return "\n".join(x for x in [b.get("title")] + lines if x)
    if t == "quote":
        return "\n".join("> " + ln for ln in _body_of(b).splitlines())
    if t == "annotation":
        return " ".join(x for x in (f"[{b['title']}]" if b.get("title") else "",
                                    _body_of(b)) if x)
    if t == "figure":
        return f"[Figure: {b['caption']}]" if b.get("caption") else "[Figure]"
    if t == "signature":
        return "\n".join([b.get("place_and_date", "")] + b.get("signatories", [])
                         + ([_body_of(b)] if "content" in b else [])).strip()
    return _body_of(b)


def render_blocks(blocks: list[Block]) -> str:
    """Render a list of blocks into newline-separated plain text."""
    return "\n".join(x for x in (render_block(b) for b in blocks) if x)


def render_text(doc: dict[str, Any]) -> str:
    """Render a parsed Formex document dictionary as readable plain text."""
    parts: list[str] = []
    if doc.get("title"):
        parts.append(doc["title"])
    pre = doc.get("preamble")
    if pre:
        parts.append("\n".join(x for x in [
            pre.get("initial"), pre.get("visas_intro"), *pre.get("visas", []),
            pre.get("recitals_intro"), *(render_block(r) for r in pre.get("recitals", [])),
            pre.get("final")] if x))
        if pre.get("other"):
            parts.append(render_blocks(pre["other"]))
    parts.extend(x for x in (render_block(b) for b in doc.get("body", [])) if x)
    if doc.get("final"):
        parts.append(render_blocks(doc["final"].get("content", [])))
    if doc.get("notes"):
        parts.append("\n".join(f"[^{k}] {v}" for k, v in doc["notes"].items()))
    return "\n\n".join(parts)
