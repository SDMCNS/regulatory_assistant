#!/usr/bin/env python3
"""
formex_to_json - turn Formex 4 XML (EU Publications Office) into clean JSON/dicts.

What is kept
    * The document's real text: title, preamble (visas + recitals), articles,
      paragraphs, lists, tables, annexes, quotes, annotations, footnotes,
      signature block.
    * A small, useful metadata subset (language, date, document type,
      OJ reference, document numbers, EEA/ANSM relevance).

What is dropped
    * Bibliographic / production plumbing: BIB.* blocks, PAGE.*, NO.SEQ,
      PROD.ID, FIN.ID, DURAB, file references, INCLUSIONS, core-metadata refs.
    * The generated table of contents (TOC) - it only duplicates the body
      (use keep_toc=True to retain it).
    * Presentation markup (HT bold/italic/UC, FT typing, MARGIN layout hints).
    * Anonymisation boilerplate notes ("Information erased or replaced ...").
    * XML namespaces, IDs and layout attributes that carry no text.

Output shape (see build_schema() / `--schema` for the full JSON Schema)
    {
      "format": "formex", "root": "ACT",
      "metadata": {...}, "title": "...", "title_lines": [...],
      "preamble": {"initial", "visas", "recitals_intro", "recitals", "final"},
      "body": [ block, ... ],          # articles, sections, tables, ...
      "final": {"content": [ block, ... ]},
      "notes": {"E0001": "footnote text"}
    }
    A block is {"type": ..., ...}. Nodes with plain content carry "text";
    nodes with structure carry "content" (a list of blocks).

Usage
    python formex_to_json.py act.fmx.xml -o act.json
    python formex_to_json.py act.fmx.xml --text        # plain-text rendering
    python formex_to_json.py --schema > formex_schema.json

    from formex_to_json import parse_formex, render_text
    doc = parse_formex("act.fmx.xml")

Only the standard library is used. Namespaces are ignored (EUR-Lex files
use one, older files do not).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

Block = dict[str, Any]

_BR = "\x00"  # sentinel for <BR/> so it survives whitespace normalisation

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _local(el: ET.Element) -> str | None:
    t = el.tag
    return t.rsplit("}", 1)[-1] if isinstance(t, str) else None


def _child(el: ET.Element | None, tag: str) -> ET.Element | None:
    if el is None:
        return None
    for c in el:
        if _local(c) == tag:
            return c
    return None


def _children(el: ET.Element, tag: str) -> list[ET.Element]:
    return [c for c in el if _local(c) == tag]


def _int(v: str | None, default: int = 1) -> int:
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
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _plain(el: ET.Element | None) -> str | None:
    """Raw text of an element, whitespace-normalised (metadata use)."""
    if el is None:
        return None
    return _norm("".join(el.itertext())) or None


def _iso(date_el: ET.Element) -> str | None:
    raw = date_el.get("ISO") or "".join(date_el.itertext()).strip()
    raw = re.sub(r"\D", "", raw)
    if len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if len(raw) == 6:
        return f"{raw[:4]}-{raw[4:]}"
    return raw or None


_SUP = dict(zip("0123456789+-−=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ"))
_SUB = dict(zip("0123456789+-−=()aehiklmnoprstx", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₕᵢₖₗₘₙₒₚᵣₛₜₓ"))


def _script(text: str, table: dict[str, str], marker: str) -> str:
    t = text.strip()
    if not t:
        return ""
    if all(ch in table for ch in t):
        return "".join(table[ch] for ch in t)
    return f"{marker}{t}" if t.isalnum() else f"{marker}({t})"


def _wrap(s: str) -> str:
    return s if re.fullmatch(r"[\w.,]+", s) else f"({s})"


# --------------------------------------------------------------------------
# Element classification
# --------------------------------------------------------------------------

# Elements whose content is mixed text and never a block of its own.
INLINE_TAGS = {
    "HT", "FT", "DATE", "NOTE", "QUOT.START", "QUOT.END", "BR", "IE",
    "ANONYMOUS", "LINK", "ADDR", "REF.DOC", "REF.DOC.OJ", "REF.DOC.ECR",
    "REF.DOC.SE", "REF.NP.ECR", "NO.CASE", "NO.ECLI", "NO.ELI", "NO.DOC.C",
    "PL.DATE",
    # formulas
    "FORMULA", "EXPR", "EXPONENT", "IND", "FRACTION", "DIVIDEND", "DIVISOR",
    "ROOT", "DEGREE", "OVERLINE", "VECTOR", "BAR", "SUM", "PRODUCT",
    "INTEGRAL", "FUNCTION", "OP.CMP", "OP.MATH", "FMT.VALUE", "OVER", "UNDER",
}

# Text-bearing elements that become their own paragraph even when they have
# no child elements (everything typed t_btx / t_btx.seq block-ish in the manual).
FLAT_TAGS = {
    "P", "TXT", "ALINEA", "KEYWORD", "VISA", "TERM", "DEFINITION", "INTRO",
    "HINT", "NAME.COMMON", "NOTICE", "DESCRIPTION", "APPLICANT", "ITEM.CONT",
    "PREAMBLE.INIT", "PREAMBLE.FINAL", "TI", "STI", "TI.CJT", "SIGNATORY",
    "NO.P", "NO.PARAG", "TI.ART", "STI.ART", "CURR.TITLE",
}

# Pure plumbing: never contributes text.
DROP_TAGS = {
    "DOCUMENT.REF", "DOCUMENT.REF.CONS", "NO.SEQ", "PROD.ID", "FIN.ID",
    "DURAB", "INCLUSIONS", "REF.CORE.METADATA", "REF.BIB.RECORD", "REF.PHYS",
    "ASSOCIATED.TO", "ASSOCIATES", "PDF.ECR", "PDF.GEN", "PAPER.GEN",
    "FMX.GEN", "NO.DOC.SUMMARY", "DOC.CORR", "DOC.CORR.SE",
}


class FormexParser:
    def __init__(self, keep_toc: bool = False, include_metadata: bool = True,
                 nest_points: bool = True):
        self.nest_points = nest_points
        self.keep_toc = keep_toc
        self.include_metadata = include_metadata
        self._block: dict[str, Callable[[ET.Element], list[Block]]] = {
            "ARTICLE": self._h_article,
            "PARAG": self._h_parag,
            "SUBDIV": self._h_titled("subdivision"),
            "DIVISION": self._h_titled("division"),
            "GR.SEQ": self._h_titled("section"),
            "NP": self._h_np,
            "NP.ECR": self._h_np,
            "ITEM": lambda c: [self._item(c)],
            "CONSID": lambda c: [self._item(c)],
            "LIST": self._h_list,
            "DLIST": self._h_dlist,
            "DLIST.ITEM": self._h_dlist_item,
            "TBL": self._h_tbl,
            "QUOT.S": self._h_quote,
            "ANNOTATION": self._h_annotation,
            "COMMENT": self._h_annotation,
            "MARGIN": self._h_annotation,
            "GR.NOTES": self._h_gr_notes,
            "INCL.ELEMENT": self._h_figure,
            "ADDR.S": self._h_addr_s,
            "SIGNATURE": self._h_signature,
            "TITLE": self._h_title,
            "TOC": lambda c: self._blocks(c) if self.keep_toc else [],
        }
        for t in FLAT_TAGS:
            self._block.setdefault(t, self._flat)
        self._inline_h: dict[str, Callable[[ET.Element], str]] = {
            "HT": self._i_ht, "NOTE": self._i_note, "BR": lambda c: _BR,
            "IE": lambda c: "", "QUOT.START": self._i_quot,
            "QUOT.END": self._i_quot, "ANONYMOUS": self._i_anon,
            "LINK": self._i_link, "INCL.ELEMENT": lambda c: "",
            "EXPONENT": lambda c: _script(self._ninline(c), _SUP, "^"),
            "IND": lambda c: _script(self._ninline(c), _SUB, "_"),
            "FRACTION": self._i_fraction, "ROOT": self._i_root,
        }
        self._reset()

    # ---------------------------------------------------------------- state
    def _reset(self) -> None:
        self.notes: dict[str, str] = {}
        self._note_uses: dict[str, int] = {}
        self._anon_refs: set[str] = set()
        self._anonymised = False
        self._auto_note = 0

    def _dropped(self, tag: str | None) -> bool:
        if tag is None:
            return True
        if tag in DROP_TAGS or tag.startswith(("BIB.", "PAGE.")):
            return True
        return tag == "TOC" and not self.keep_toc

    # ------------------------------------------------------------- entry
    def parse_element(self, root: ET.Element) -> dict[str, Any]:
        self._reset()
        doc: dict[str, Any] = {"format": "formex", "root": _local(root)}

        if self.include_metadata:
            meta = self._metadata(root)
            if meta:
                doc["metadata"] = meta

        skip: set[Any] = set()
        title_el = _child(root, "TITLE")
        if title_el is not None:
            info = self._title_info(title_el)
            doc.update(_compact({
                "title": info["text"],
                "title_lines": info["lines"] if len(info["lines"]) > 1 else None,
                "subtitle": info["subtitle"],
            }))
            skip.add(title_el)

        pre = _child(root, "PREAMBLE")
        if pre is not None:
            skip.add(pre)
        fin = _child(root, "FINAL")
        if fin is not None:
            skip.add(fin)

        if pre is not None:
            doc["preamble"] = self._preamble(pre)
            if self.nest_points:
                for key in ("recitals", "other"):
                    if key in doc["preamble"]:
                        doc["preamble"][key] = group_points(doc["preamble"][key])
        body = self._blocks(root, skip=skip)
        if self.nest_points:
            body = group_points(body)
        if body:
            doc["body"] = body
        if fin is not None:
            fin_blocks = self._blocks(fin)
            doc["final"] = {"content": group_points(fin_blocks) if self.nest_points else fin_blocks}

        for ref in self._anon_refs:  # drop anonymisation boilerplate
            if not self._note_uses.get(ref):
                self.notes.pop(ref, None)
        if self.notes:
            doc["notes"] = self.notes
        if self._anonymised:
            doc["anonymised"] = True
        return doc

    # ------------------------------------------------------------ metadata
    def _metadata(self, root: ET.Element) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        for bib in root:
            tag = _local(bib)
            if tag == "BIB.INSTANCE":
                self._bib_instance(bib, meta)
            elif tag == "BIB.DOC":
                self._bib_common(bib, meta)
                authors = [_plain(a) for a in _children(bib, "AUTHOR")]
                meta.setdefault("authors", [a for a in authors if a])
                eli = _plain(_child(bib, "NO.ELI"))
                if eli:
                    meta["eli"] = eli
        return _compact(meta)

    def _bib_instance(self, bib: ET.Element, meta: dict[str, Any]) -> None:
        ref = _child(bib, "DOCUMENT.REF")
        if ref is not None:
            oj = _compact({
                "collection": _plain(_child(ref, "COLL")),
                "number": _plain(_child(ref, "NO.OJ")),
                "year": _plain(_child(ref, "YEAR")),
                "language": _plain(_child(ref, "LG.OJ")),
            })
            if oj:
                meta["official_journal"] = oj
        meta["language"] = _plain(_child(bib, "LG.DOC"))
        meta["document_type"] = _plain(_child(bib, "DOC.TYPE"))
        dates = [d for d in (_iso(x) for x in _children(bib, "DATE")) if d]
        if dates:
            meta["date"] = dates[0]
            if len(dates) > 1:
                meta["other_dates"] = dates[1:]
        cases = [c for c in (_plain(x) for x in _children(bib, "NO.CASE")) if c]
        if cases:
            meta["case_numbers"] = cases
        self._bib_common(bib, meta)

    def _bib_common(self, bib: ET.Element, meta: dict[str, Any]) -> None:
        ids = [self._no_doc(n) for n in _children(bib, "NO.DOC")]
        ids = [i for i in ids if i]
        if ids:
            meta.setdefault("identifiers", []).extend(ids)
        if _child(bib, "EEA") is not None:
            meta["eea_relevance"] = True
        if _child(bib, "ANSM") is not None:
            meta["ansm_relevance"] = True

    @staticmethod
    def _no_doc(nd: ET.Element) -> dict[str, Any]:
        cur = _plain(_child(nd, "NO.CURRENT"))
        year = _plain(_child(nd, "YEAR"))
        com = _plain(_child(nd, "COM"))
        fmt = (nd.get("FORMAT") or "").upper()
        order = [ch for ch in fmt if ch in "NY"] or ["N", "Y"]
        parts = [cur if ch == "N" else year for ch in order]
        number = "/".join(p for p in parts if p)
        if com:
            number = f"{number}/{com}" if number else com
        return _compact({"type": nd.get("TYPE"), "number": number,
                         "current": cur, "year": year, "community": com})

    # ------------------------------------------------------- block engine
    def _blocks(self, el: ET.Element, skip: set[Any] | tuple = ()) -> list[Block]:
        out: list[Block] = []
        buf: list[str] = [el.text or ""]

        def flush() -> None:
            txt = _norm("".join(buf))
            buf.clear()
            if txt:
                out.append({"type": "text", "text": txt})

        for c in el:
            tag = _local(c)
            if tag is not None and not (c in skip or tag in skip) and not self._dropped(tag):
                # Known inline tags, and unknown leaf elements (e.g. PLACE),
                # stay inside the running sentence instead of splitting it.
                if tag in INLINE_TAGS or (tag not in self._block and not len(c)):
                    buf.append(self._inline_child(c))
                else:
                    flush()
                    out.extend(self._child_blocks(c))
            buf.append(c.tail or "")
        flush()
        return out

    def _child_blocks(self, c: ET.Element) -> list[Block]:
        tag = _local(c)
        if self._dropped(tag):
            return []
        h = self._block.get(tag or "")
        if h:
            return h(c)
        if len(c):  # unknown container: be transparent, never lose text
            return self._blocks(c)
        t = _norm(self._inline_child(c))
        return [{"type": "text", "text": t}] if t else []

    def _flat(self, c: ET.Element) -> list[Block]:
        return self._blocks(c)

    def _text(self, el: ET.Element | None) -> str | None:
        if el is None:
            return None
        return render_blocks(self._blocks(el)) or None

    def _node(self, type_: str, blocks: list[Block], **fields: Any) -> Block:
        node: Block = {"type": type_}
        node.update(_compact(fields))
        if len(blocks) == 1 and blocks[0]["type"] == "text":
            node["text"] = blocks[0]["text"]
        elif blocks:
            node["content"] = blocks
        return node

    # ------------------------------------------------------------- inline
    def _inline(self, el: ET.Element) -> str:
        parts = [el.text or ""]
        for c in el:
            parts.append(self._inline_child(c))
            parts.append(c.tail or "")
        return "".join(parts)

    def _ninline(self, el: ET.Element) -> str:
        return _norm(self._inline(el))

    def _inline_child(self, c: ET.Element) -> str:
        tag = _local(c)
        if self._dropped(tag):
            return ""
        h = self._inline_h.get(tag or "")
        return h(c) if h else self._inline(c)

    def _i_ht(self, c: ET.Element) -> str:
        kind = (c.get("TYPE") or "").upper()
        text = self._inline(c)
        if kind == "SUP":
            return _script(text, _SUP, "^")
        if kind == "SUB":
            return _script(text, _SUB, "_")
        return text

    def _i_quot(self, c: ET.Element) -> str:
        default = "\u201c" if _local(c) == "QUOT.START" else "\u201d"
        try:
            return chr(int(c.get("CODE", ""), 16))
        except ValueError:
            return default

    def _i_link(self, c: ET.Element) -> str:
        text = self._inline(c)
        if text.strip():
            return text
        for k, v in c.attrib.items():
            if k.rsplit("}", 1)[-1].upper() in ("HREF", "URI", "URL"):
                return v
        return ""

    def _i_anon(self, c: ET.Element) -> str:
        self._anonymised = True
        n = _child(c, "NOTE")
        if n is not None:
            ref = n.get("NOTE.REF") or n.get("NOTE.ID")
            if ref:
                self._anon_refs.add(ref)
        ph = (c.get("PLACEHOLDER") or "").strip()
        return ph or "[anonymised]"

    def _i_fraction(self, c: ET.Element) -> str:
        a, b = _child(c, "DIVIDEND"), _child(c, "DIVISOR")
        if a is None or b is None:
            return self._inline(c)
        return f"{_wrap(self._ninline(a))}/{_wrap(self._ninline(b))}"

    def _i_root(self, c: ET.Element) -> str:
        deg = _child(c, "DEGREE")
        parts = [c.text or ""]
        for k in c:
            if k is not deg:
                parts.append(self._inline_child(k))
            parts.append(k.tail or "")
        prefix = _script(self._ninline(deg), _SUP, "^") if deg is not None else ""
        return f"{prefix}\u221a({_norm(''.join(parts))})"

    # -------------------------------------------------------------- notes
    def _i_note(self, c: ET.Element) -> str:
        nid, ref = c.get("NOTE.ID"), c.get("NOTE.REF")
        if nid and len(c):
            self._register_note(c)
        if not (nid or ref):
            self._auto_note += 1
            nid = f"n{self._auto_note}"
            txt = render_blocks(self._blocks(c))
            if txt:
                self.notes[nid] = txt
        key = nid or ref or ""
        self._note_uses[key] = self._note_uses.get(key, 0) + 1
        return f"[^{key}]"

    def _register_note(self, c: ET.Element) -> None:
        nid = c.get("NOTE.ID")
        if nid:
            txt = render_blocks(self._blocks(c))
            if txt:
                self.notes[nid] = txt

    def _h_gr_notes(self, c: ET.Element) -> list[Block]:
        for n in _children(c, "NOTE"):
            self._register_note(n)
        return []

    # ------------------------------------------------- structural handlers
    def _title_info(self, el: ET.Element) -> dict[str, Any]:
        ti, sti = _child(el, "TI"), _child(el, "STI")
        if ti is None and sti is None:
            t = self._text(el)
            return {"text": t, "lines": [t] if t else [], "subtitle": None}
        lines = [render_block(b) for b in self._blocks(ti)] if ti is not None else []
        lines = [ln for ln in lines if ln]
        sub = self._text(sti)
        return {"text": " ".join(lines) or None, "lines": lines, "subtitle": sub}

    def _h_title(self, c: ET.Element) -> list[Block]:
        info = self._title_info(c)
        if not info["text"] and not info["subtitle"]:
            return []
        return [_compact({"type": "heading", "text": info["text"] or info["subtitle"],
                          "subtitle": info["subtitle"] if info["text"] else None})]

    def _h_titled(self, type_: str) -> Callable[[ET.Element], list[Block]]:
        def handler(c: ET.Element) -> list[Block]:
            t = _child(c, "TITLE")
            info = self._title_info(t) if t is not None else {}
            number = self._text(_child(c, "NO.GR.SEQ"))
            blocks = self._blocks(c, skip={"TITLE", "NO.GR.SEQ"})
            return [self._node(type_, blocks, number=number,
                               title=info.get("text"), subtitle=info.get("subtitle"))]
        return handler

    def _h_article(self, c: ET.Element) -> list[Block]:
        blocks = self._blocks(c, skip={"TI.ART", "STI.ART"})
        return [self._node("article", blocks, identifier=c.get("IDENTIFIER"),
                           number=self._text(_child(c, "TI.ART")),
                           subtitle=self._text(_child(c, "STI.ART")))]

    def _h_parag(self, c: ET.Element) -> list[Block]:
        blocks = self._blocks(c, skip={"NO.PARAG"})
        return [self._node("paragraph", blocks, number=self._text(_child(c, "NO.PARAG")),
                           identifier=c.get("IDENTIFIER"))]

    def _h_np(self, c: ET.Element) -> list[Block]:
        return [self._node("item", self._blocks(c, skip={"NO.P"}),
                           number=self._text(_child(c, "NO.P")))]

    def _item(self, c: ET.Element) -> Block:
        """ITEM / CONSID: unwrap the NP they usually contain."""
        blocks = self._blocks(c)
        if blocks and blocks[0]["type"] == "item":
            first, rest = blocks[0], blocks[1:]
            if not rest:
                return first
            content = first.get("content") or (
                [{"type": "text", "text": first["text"]}] if "text" in first else [])
            head = {k: v for k, v in first.items() if k not in ("text", "content")}
            return {**head, "content": content + rest}
        return self._node("item", blocks)

    def _h_list(self, c: ET.Element) -> list[Block]:
        items: list[Block] = []
        for k in c:
            tag = _local(k)
            if self._dropped(tag):
                continue
            items.append(self._item(k) if tag == "ITEM"
                         else self._node("item", self._child_blocks(k)))
        style = (c.get("TYPE") or "").lower() or None
        return [_compact({"type": "list", "style": style, "items": items})]

    def _dlist_item(self, it: ET.Element) -> dict[str, Any]:
        term, dfn = self._text(_child(it, "TERM")), self._text(_child(it, "DEFINITION"))
        if term is None and dfn is None:
            dfn = self._text(it)
        return _compact({"term": term, "definition": dfn})

    def _h_dlist(self, c: ET.Element) -> list[Block]:
        items = [self._dlist_item(i) for i in _children(c, "DLIST.ITEM")]
        return [{"type": "definition_list", "items": items}] if items else []

    def _h_dlist_item(self, c: ET.Element) -> list[Block]:
        return [{"type": "definition_list", "items": [self._dlist_item(c)]}]

    def _h_quote(self, c: ET.Element) -> list[Block]:
        blocks = self._blocks(c)
        return [{"type": "quote", "content": blocks}] if blocks else []

    def _h_annotation(self, c: ET.Element) -> list[Block]:
        t = _child(c, "TITLE")
        info = self._title_info(t) if t is not None else {}
        blocks = self._blocks(c, skip={"TITLE"})
        node = self._node("annotation", blocks, kind=(_local(c) or "").lower(),
                          title=info.get("text"))
        return [node] if ("text" in node or "content" in node) else []

    def _h_figure(self, c: ET.Element) -> list[Block]:
        cap = self._text(_child(c, "CAPTION"))
        return [_compact({"type": "figure", "ref": c.get("FILEREF"), "caption": cap})]

    def _h_addr_s(self, c: ET.Element) -> list[Block]:
        lines = [render_block(b) for b in self._blocks(c)]
        return [{"type": "text", "text": "\n".join(x for x in lines if x)}]

    def _h_signature(self, c: ET.Element) -> list[Block]:
        sigs = [self._text(s) for s in _children(c, "SIGNATORY")]
        rest = self._blocks(c, skip={"PL.DATE", "SIGNATORY"})
        return [_compact({
            "type": "signature",
            "place_and_date": self._text(_child(c, "PL.DATE")),
            "signatories": [s for s in sigs if s],
            "content": rest,
        })]

    # ------------------------------------------------------------- tables
    def _h_tbl(self, c: ET.Element) -> list[Block]:
        title_el = _child(c, "TITLE")
        title = self._title_info(title_el)["text"] if title_el is not None else None
        rows: list[tuple[bool, dict[int, str]]] = []
        spans: list[dict[str, int]] = []

        def add_row(row: ET.Element) -> None:
            cells: dict[int, str] = {}
            for cell in row:
                if _local(cell) != "CELL":
                    continue
                col = _int(cell.get("COL"), len(cells) + 1)
                cells[col] = self._text(cell) or ""
                cs, rs = _int(cell.get("COLSPAN")), _int(cell.get("ROWSPAN"))
                if cs > 1 or rs > 1:
                    spans.append(_compact({"row": len(rows), "col": col,
                                           "colspan": cs if cs > 1 else None,
                                           "rowspan": rs if rs > 1 else None}))
            rows.append(((row.get("TYPE") or "").upper() == "HEADER", cells))

        def walk(container: ET.Element) -> None:
            for r in container:
                tag = _local(r)
                if tag == "ROW":
                    add_row(r)
                elif tag == "BLK":
                    ti = _child(r, "TI.BLK")
                    if ti is not None:
                        rows.append((False, {1: self._text(ti) or ""}))
                    walk(r)

        for k in c:
            tag = _local(k)
            if tag == "GR.NOTES":
                self._h_gr_notes(k)
            elif tag == "CORPUS":
                walk(k)

        width = max([_int(c.get("COLS"), 0)] + [max(r, default=0) for _, r in rows])
        grid = [[r.get(i, "") for i in range(1, width + 1)] for _, r in rows]
        n_head = 0
        while n_head < len(rows) and rows[n_head][0]:
            n_head += 1
        return [_compact({"type": "table", "title": title, "columns": width,
                          "header": grid[:n_head], "rows": grid[n_head:],
                          "spans": spans})]

    # ----------------------------------------------------------- preamble
    def _preamble(self, el: ET.Element) -> dict[str, Any]:
        out: dict[str, Any] = {}
        visas: list[str] = []
        recitals: list[Block] = []
        other: list[Block] = []
        for c in el:
            tag = _local(c)
            if tag == "PREAMBLE.INIT":
                out["initial"] = self._text(c)
            elif tag == "PREAMBLE.FINAL":
                out["final"] = self._text(c)
            elif tag == "GR.VISA":
                for v in c:
                    vt = _local(v)
                    if vt == "VISA":
                        t = self._text(v)
                        if t:
                            visas.append(t)
                    elif vt == "GR.VISA.INIT":
                        out["visas_intro"] = self._text(v)
                    else:
                        other.extend(self._child_blocks(v))
            elif tag == "GR.CONSID":
                for v in c:
                    vt = _local(v)
                    if vt == "CONSID":
                        recitals.append(self._item(v))
                    elif vt == "GR.CONSID.INIT":
                        out["recitals_intro"] = self._text(v)
                    else:
                        other.extend(self._child_blocks(v))
            else:
                other.extend(self._child_blocks(c))
        out.update({"visas": visas, "recitals": recitals, "other": other})
        return _compact(out)


# --------------------------------------------------------------------------
# Point nesting: (1) > (a) > (i) > bullets
# --------------------------------------------------------------------------
# Formex often stores "(1) ... (a) ... (b) ... (2) ..." as flat siblings, and a
# bullet list as a sibling that follows its point. For storage/embedding each
# numbered point must stay whole, so sub-points and bullet lists are moved
# inside the point they belong to.

_ROMAN = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
_STARTERS = {"num": "1", "alpha": "a", "roman": "i", "ualpha": "A"}


def _point_token(number: str) -> str:
    return number.strip().strip("()[].:;").strip()


def _wrap_of(number: str) -> str:
    raw = number.strip().rstrip(".;:")
    if raw.startswith("(") and raw.endswith(")"):
        return "paren"          # (1) (a) (i)
    if raw.endswith(")"):
        return "close"          # 1) a)
    return "dot" if number.strip().endswith(".") else "bare"   # 1.  /  1


def _signature(number: str, stack: list) -> tuple[str, str, str] | None:
    """(style, wrap, token) for a point label, or None if it is not a point label.

    Style is what a human reads off the label: 1 / a / i / A / 1.1 ..., and the
    wrapper ((x), x., x)) - so "1." and "(1)" are different levels. The
    letter-vs-roman ambiguity of (i), (v), (x) is settled from the sequence:
    (h) -> (i) continues the alphabet, (a) -> (i) starts a roman sub-list.
    """
    token, wrap = _point_token(number), _wrap_of(number)
    if re.fullmatch(r"\d+[a-z]?", token):
        return "num", wrap, token
    if re.fullmatch(r"\d+(\.\d+)+", token):
        return f"num{token.count('.') + 1}", wrap, token
    if token.isalpha() and token.islower():
        if len(token) > 1:
            return ("roman" if _ROMAN.match(token) else "alpha"), wrap, token
        prev = next((sig[2] for sig, _t in reversed(stack)
                     if sig[0] == "alpha" and sig[1] == wrap), None)
        if prev and len(prev) == 1 and ord(prev) + 1 == ord(token):
            return "alpha", wrap, token
        return ("roman" if token in "ivx" else "alpha"), wrap, token
    if token.isalpha() and token.isupper():
        return "ualpha", wrap, token
    return None


def _attach(parent: Block, child: Block) -> None:
    if "content" not in parent:
        parent["content"] = ([{"type": "text", "text": parent.pop("text")}]
                             if "text" in parent else [])
    parent["content"].append(child)


def _regroup(blocks: list[Block]) -> list[Block]:
    """Single pass with the previous point kept in memory (a stack of open points).

    * new label already open in the stack  -> sibling: close it and everything below
      (unless it is a starter such as "1"/"a"/"i" - that is a restart, so a child)
    * new label not open                   -> child of the current point
    * a list (dash/bullet/lettered)        -> belongs to the current point
    * anything else (plain paragraph)      -> closes all open points
    """
    out: list[Block] = []
    stack: list[tuple[tuple[str, str, str], str, Block]] = []  # (sig, token, node)
    for b in blocks:
        if b.get("type") in ("item", "paragraph") and b.get("number"):
            sig = _signature(b["number"], [(e[0], e[1]) for e in stack])
            if sig:
                style, wrap, token = sig
                idx = next((i for i, e in enumerate(stack)
                            if e[0][0] == style and e[0][1] == wrap), None)
                restart = style in _STARTERS and token == _STARTERS[style]
                if idx is not None and not restart:
                    del stack[idx:]                     # sibling of an open point
                if stack:
                    _attach(stack[-1][2], b)            # child of the current point
                else:
                    out.append(b)
                stack.append((sig, token, b))
                continue
        if b.get("type") == "list" and stack:
            _attach(stack[-1][2], b)
            continue
        stack.clear()
        out.append(b)
    return out


def group_points(blocks: list[Block]) -> list[Block]:
    """Recursively nest lettered/roman sub-points and lists under their point."""
    for b in blocks:
        if "content" in b:
            b["content"] = group_points(b["content"])
        if b.get("type") == "list":
            b["items"] = group_points(b["items"])
    return _regroup(blocks)


# --------------------------------------------------------------------------
# Plain-text rendering
# --------------------------------------------------------------------------


def _body_of(b: Block) -> str:
    if "content" in b:
        return "\n".join(x for x in (render_block(c) for c in b["content"]) if x)
    return b.get("text", "")


def render_block(b: Block) -> str:
    t = b["type"]
    if t in ("text", "heading"):
        return b["text"] if t == "text" else "\n".join(
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
        for it in b["items"]:
            line = render_block(it)
            lines.append(f"- {line}" if dash and not it.get("number") else line)
        return "\n".join(lines)
    if t == "definition_list":
        return "\n".join(f"{i.get('term', '')}: {i.get('definition', '')}".strip(": ")
                         for i in b["items"])
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
    return "\n".join(x for x in (render_block(b) for b in blocks) if x)


def render_text(doc: dict[str, Any]) -> str:
    """Render a parsed document as readable plain text."""
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
        parts.append(render_blocks(doc["final"]["content"]))
    if doc.get("notes"):
        parts.append("\n".join(f"[^{k}] {v}" for k, v in doc["notes"].items()))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# JSON Schema for the output
# --------------------------------------------------------------------------


def build_schema() -> dict[str, Any]:
    S: dict[str, Any] = {"type": "string"}
    blocks = {"type": "array", "items": {"$ref": "#/$defs/block"}}
    body = {"text": S, "content": blocks}

    def node(t: str, props: dict[str, Any] | None = None, req: tuple = ()) -> dict:
        p: dict[str, Any] = {"type": {"const": t}}
        p.update(props or {})
        return {"type": "object", "properties": p,
                "required": ["type", *req], "additionalProperties": False}

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


# --------------------------------------------------------------------------
# Public API / CLI
# --------------------------------------------------------------------------


def parse_formex(source: str | bytes | Path, *, keep_toc: bool = False,
                 include_metadata: bool = True, nest_points: bool = True) -> dict[str, Any]:
    """Parse a Formex file path, XML string, or XML bytes into a dict."""
    if isinstance(source, bytes):
        root = ET.fromstring(source)
    elif isinstance(source, str) and source.lstrip().startswith("<"):
        root = ET.fromstring(source.encode("utf-8"))
    else:
        root = ET.parse(str(source)).getroot()
    return FormexParser(keep_toc, include_metadata, nest_points).parse_element(root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse Formex 4 XML into JSON.")
    ap.add_argument("input", nargs="?", help="Formex XML file")
    ap.add_argument("-o", "--output", help="write to file instead of stdout")
    ap.add_argument("--text", action="store_true", help="emit plain text, not JSON")
    ap.add_argument("--keep-toc", action="store_true", help="keep table of contents")
    ap.add_argument("--no-metadata", action="store_true", help="omit metadata block")
    ap.add_argument("--schema", action="store_true", help="print the JSON Schema and exit")
    a = ap.parse_args(argv)

    if a.schema:
        out = json.dumps(build_schema(), indent=2, ensure_ascii=False)
    else:
        if not a.input:
            ap.error("input file required (or use --schema)")
        doc = parse_formex(a.input, keep_toc=a.keep_toc, include_metadata=not a.no_metadata)
        out = render_text(doc) if a.text else json.dumps(doc, indent=2, ensure_ascii=False)

    if a.output:
        Path(a.output).write_text(out + "\n", encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
