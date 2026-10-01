"""JSON Schema generator for parsed Formex documents."""
from __future__ import annotations

from typing import Any


def build_schema() -> dict[str, Any]:
    """Build and return JSON Schema (Draft 2020-12) for parsed Formex output."""
    S: dict[str, Any] = {"type": "string"}
    blocks = {"type": "array", "items": {"$ref": "#/$defs/block"}}
    body = {"text": S, "content": blocks}

    def node(t: str, props: dict[str, Any] | None = None, req: tuple = ()) -> dict[str, Any]:
        p: dict[str, Any] = {"type": {"const": t}}
        p.update(props or {})
        return {
            "type": "object",
            "properties": p,
            "required": ["type", *req],
            "additionalProperties": False,
        }

    ref = lambda n: {"$ref": f"#/$defs/{n}"}  # noqa: E731
    defs: dict[str, Any] = {
        "text": node("text", {"text": S}, ("text",)),
        "heading": node("heading", {"text": S, "subtitle": S}, ("text",)),
        "article": node("article", {"identifier": S, "number": S, "subtitle": S, **body}),
        "paragraph": node("paragraph", {"number": S, "identifier": S, **body}),
        "subdivision": node("subdivision", {"number": S, "title": S, "subtitle": S, **body}),
        "division": node("division", {"number": S, "title": S, "subtitle": S, **body}),
        "section": node("section", {"number": S, "title": S, "subtitle": S, **body}),
        "item": node("item", {"number": S, **body}),
        "list": node("list", {"style": S, "items": {"type": "array", "items": ref("item")}},
                     ("items",)),
        "definition_list": node("definition_list", {"items": {"type": "array", "items": {
            "type": "object",
            "properties": {"term": S, "definition": S},
            "additionalProperties": False}}}, ("items",)),
        "table": node("table", {
            "title": S, "columns": {"type": "integer"},
            "header": {"type": "array", "items": {"type": "array", "items": S}},
            "rows": {"type": "array", "items": {"type": "array", "items": S}},
            "spans": {"type": "array", "items": {
                "type": "object",
                "properties": {"row": {"type": "integer"}, "col": {"type": "integer"},
                               "colspan": {"type": "integer"},
                               "rowspan": {"type": "integer"}},
                "required": ["row", "col"]}},
        }),
        "quote": node("quote", {"content": blocks}, ("content",)),
        "annotation": node("annotation", {"kind": S, "title": S, **body}),
        "figure": node("figure", {"ref": S, "caption": S}),
        "signature": node("signature", {"place_and_date": S,
                                        "signatories": {"type": "array", "items": S},
                                        "content": blocks}),
    }
    names = list(defs)
    defs["block"] = {"oneOf": [ref(n) for n in names]}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Parsed Formex document",
        "type": "object",
        "properties": {
            "format": {"const": "formex"},
            "root": S,
            "metadata": {"type": "object", "properties": {
                "language": S, "document_type": S, "date": S,
                "other_dates": {"type": "array", "items": S},
                "official_journal": {"type": "object", "additionalProperties": S},
                "identifiers": {"type": "array", "items": {"type": "object"}},
                "case_numbers": {"type": "array", "items": S},
                "authors": {"type": "array", "items": S},
                "eli": S, "eea_relevance": {"type": "boolean"},
                "ansm_relevance": {"type": "boolean"}}},
            "title": S,
            "title_lines": {"type": "array", "items": S},
            "subtitle": S,
            "preamble": {"type": "object", "properties": {
                "initial": S, "visas_intro": S,
                "visas": {"type": "array", "items": S},
                "recitals_intro": S,
                "recitals": {"type": "array", "items": ref("item")},
                "final": S, "other": blocks}},
            "body": blocks,
            "final": {"type": "object", "properties": {"content": blocks},
                      "required": ["content"]},
            "notes": {"type": "object", "additionalProperties": S},
            "anonymised": {"type": "boolean"},
        },
        "required": ["format", "root"],
        "$defs": defs,
    }
