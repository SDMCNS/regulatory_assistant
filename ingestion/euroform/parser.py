"""Core Formex parser and conversion functions."""
from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

from .constants import _BR, _SUB, _SUP, DROP_TAGS, FLAT_TAGS, INLINE_TAGS
from .helpers import (
    _child,
    _children,
    _compact,
    _int,
    _iso,
    _local,
    _norm,
    _plain,
    _script,
    _wrap,
)
from .nesting import group_points
from .render import render_block, render_blocks, render_text

Block = dict[str, Any]


class FormexParser:
    """Parser that converts Formex 4 XML elements into structured Python dicts."""

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
            "HT": self._i_ht,
            "NOTE": self._i_note,
            "BR": lambda c: _BR,
            "IE": lambda c: "",
            "QUOT.START": self._i_quot,
            "QUOT.END": self._i_quot,
            "ANONYMOUS": self._i_anon,
            "LINK": self._i_link,
            "INCL.ELEMENT": lambda c: "",
            "EXPONENT": lambda c: _script(self._ninline(c), _SUP, "^"),
            "IND": lambda c: _script(self._ninline(c), _SUB, "_"),
            "FRACTION": self._i_fraction,
            "ROOT": self._i_root,
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
        """Parse an XML root ElementTree element into a Formex document dict."""
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
# Public API functions
# --------------------------------------------------------------------------


def parse_formex(
    source: str | bytes | Path | io.IOBase,
    *,
    keep_toc: bool = False,
    include_metadata: bool = True,
    nest_points: bool = True,
) -> dict[str, Any]:
    """Parse a Formex file path, XML string, XML bytes, or file-like object into a dict."""
    if isinstance(source, bytes):
        root = ET.fromstring(source)
    elif hasattr(source, "read"):
        content = source.read()
        if isinstance(content, str):
            content = content.encode("utf-8")
        root = ET.fromstring(content)
    elif isinstance(source, str):
        stripped = source.lstrip("\ufeff").strip()
        if stripped.startswith("<"):
            root = ET.fromstring(source.encode("utf-8"))
        else:
            root = ET.parse(str(source)).getroot()
    else:
        root = ET.parse(str(source)).getroot()

    return FormexParser(keep_toc, include_metadata, nest_points).parse_element(root)


def formex_to_json(
    source: str | bytes | Path | io.IOBase,
    *,
    keep_toc: bool = False,
    include_metadata: bool = True,
    nest_points: bool = True,
    indent: int | None = 2,
    ensure_ascii: bool = False,
) -> str:
    """Parse Formex XML and serialize directly to a JSON string."""
    doc = parse_formex(
        source,
        keep_toc=keep_toc,
        include_metadata=include_metadata,
        nest_points=nest_points,
    )
    return json.dumps(doc, indent=indent, ensure_ascii=ensure_ascii)


def formex_to_text(
    source: str | bytes | Path | io.IOBase,
    *,
    keep_toc: bool = False,
    include_metadata: bool = True,
    nest_points: bool = True,
) -> str:
    """Parse Formex XML and render directly to formatted plain text."""
    doc = parse_formex(
        source,
        keep_toc=keep_toc,
        include_metadata=include_metadata,
        nest_points=nest_points,
    )
    return render_text(doc)
