import os
import re
import json
import logging
import pprint
from typing import Dict, Any, List, Optional, Set
from lxml import etree

# Primary engine: the Formex -> JSON parser (formex_to_json.py, same folder / on PYTHONPATH)
_F2J_IMPORT_ERROR = None
try:
    from .formex_to_json import parse_formex, render_block
except Exception:  # not imported as part of a package
    try:
        from formex_to_json import parse_formex, render_block
    except Exception as err:
        parse_formex = None
        render_block = None
        _F2J_IMPORT_ERROR = str(err)

# Optional (opt-in) engine: the eurlex package
_EURLEX_IMPORT_ERROR = None
try:
    import eurlex
except Exception as err:
    eurlex = None
    _EURLEX_IMPORT_ERROR = str(err)

logger = logging.getLogger(__name__)


class FormexParser:
    """
    Adapter with three engines, tried in this order:

      1. (opt-in, use_eurlex=True) EUR-Lex HTML fetching via `eurlex-parser`.
      2. formex_to_json  - local, deterministic Formex 4 parser (default primary).
      3. local lxml-native heuristic parser (last-resort fallback for malformed XML
         or files the primary parser produces no text for).

    Public contract (unchanged):
        FormexParser(file_path, debug_dir="debug_output").parse()
            -> {"metadata": {...}, "structure": {tag, attributes, number, heading,
                                                 text, references, notes, children}}
    """

    PURE_CONTAINERS = {
        'ACT', 'DOC', 'PREAMBLE', 'ENACTING.TERMS', 'FINAL',
        'CHAPTER', 'SECTION', 'DIVISION', 'ANNEX', 'GR.SEQ',
        'RECITALS', 'CITATIONS', 'CONTENTS'
    }

    TEXT_CONTAINERS = {'P', 'TXT', 'NP', 'ALINEA', 'VISA', 'CONSID', 'RECITAL', 'ANNOTATION', 'ITEM', 'POINT'}
    NUMBERING_TAGS = {'NO.ARTICLE', 'NO.CHAPTER', 'NO.SECTION', 'NO.PARAG', 'NO.RECITAL', 'NO.POINT', 'NO.ANNEX'}
    MIN_SENTENCE_LEN = 15

    # Standard CELEX regex pattern: Sector (1-9), Year (4 digits), DocType (1-2 letters), Number (3-4 digits)
    CELEX_PATTERN = re.compile(r'\b([1-9][0-9]{4}[A-Z]{1,2}[0-9]{3,4})\b')

    # Footnote markers emitted by formex_to_json, e.g. "[^E0001]"
    _NOTE_MARK = re.compile(r'\s?\[\^([^\]]+)\]')

    def __init__(self, file_path: str, debug_dir: str = "debug_output", use_eurlex: bool = False):
        self.file_path = file_path
        self.debug_dir = debug_dir
        self.use_eurlex = use_eurlex  # additive, defaults keep the old call signature working

    def parse(self) -> Dict[str, Any]:
        """
        Public entry point expected by ingest_formex.py.
        """
        # Step 1: Extract CELEX ID using robust multi-pass extraction
        celex_id = self._resolve_celex_id()

        # Step 2 (opt-in): eurlex HTML fetching
        if self.use_eurlex:
            result = self._try_eurlex(celex_id)
            if result is not None:
                return result

        # Step 3: Primary local engine - formex_to_json
        result = self._try_formex_to_json(celex_id)
        if result is not None:
            return result

        # Step 4: Fallback Path - Local lxml Engine
        logger.info(f"[FormexParser] Executing fallback: Local 'lxml-native' parser for {self.file_path}")
        result = self._parse_with_lxml_native(celex_id)
        result["metadata"]["parser_engine"] = "lxml-native"
        return result

    # =========================================================================
    # Primary engine: formex_to_json
    # =========================================================================

    def _try_formex_to_json(self, celex_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if parse_formex is None:
            logger.warning(
                f"[FormexParser] formex_to_json not importable ('{_F2J_IMPORT_ERROR}'). "
                f"Defaulting to lxml-native fallback."
            )
            return None
        try:
            doc = parse_formex(self.file_path)
        except Exception as err:
            logger.warning(
                f"[FormexParser] formex_to_json failed for '{self.file_path}': {err}. "
                f"Falling back to lxml-native."
            )
            return None

        if not (doc.get("body") or doc.get("preamble") or doc.get("final")):
            logger.warning(
                f"[FormexParser] formex_to_json produced no text for '{self.file_path}' "
                f"(root <{doc.get('root')}>). Falling back to lxml-native."
            )
            return None

        self._save_debug_json(celex_id, doc)
        structure = self._transform_formex_doc_to_tree(doc)
        logger.info(f"[FormexParser] Parsed '{self.file_path}' with formex_to_json (root <{doc.get('root')}>).")
        return {
            "metadata": self._metadata_from_formex_doc(doc, celex_id),
            "structure": structure
        }

    def _metadata_from_formex_doc(self, doc: Dict[str, Any], celex_id: Optional[str]) -> Dict[str, Any]:
        m = doc.get("metadata") or {}
        oj = m.get("official_journal") or {}
        meta = {
            "celex": celex_id or self.file_path,
            "title": doc.get("title", ""),
            "oj_collection": oj.get("collection", ""),
            "oj_number": oj.get("number", ""),
            # same raw YYYYMMDD form the lxml engine took from the ISO attribute
            "date": (m.get("date") or "").replace("-", ""),
            "file_path": self.file_path,
            "parser_engine": "formex-to-json",
            "orphan_count": 0,
        }
        # additive, extra fields
        for src, dst in (("language", "language"), ("document_type", "document_type"),
                         ("identifiers", "doc_numbers"), ("eea_relevance", "eea_relevance")):
            if m.get(src):
                meta[dst] = m[src]
        if doc.get("anonymised"):
            meta["anonymised"] = True
        return meta

    def _transform_formex_doc_to_tree(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Map formex_to_json blocks onto the legacy node schema."""
        notes = doc.get("notes") or {}
        used: Set[str] = set()

        def clean(text: Optional[str]) -> str:
            return self._NOTE_MARK.sub("", text or "").strip()

        def mk(tag: str, number=None, heading=None, text: str = "",
               attributes: Optional[Dict[str, str]] = None,
               children: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            node_notes: List[str] = []
            for src in (text, heading):
                for nid in self._NOTE_MARK.findall(f" {src or ''}"):
                    if nid in notes and nid not in used:
                        used.add(nid)
                        node_notes.append(notes[nid])
            return {
                "tag": tag,
                "attributes": attributes or {},
                "number": number,
                "heading": clean(heading) or None,
                "text": clean(text),
                "references": [],
                "notes": node_notes,
                "children": children or [],
            }

        def hoist(node: Dict[str, Any]) -> Dict[str, Any]:
            """Point intro sentence -> the point's own text; children are then sub-points only."""
            kids = node["children"]
            if not node["text"] and kids and kids[0]["tag"] == "P" and not kids[0]["children"]:
                first = kids.pop(0)
                node["text"] = first["text"]
                node["notes"] += first["notes"]
            return node

        def kids_of(b: Dict[str, Any]) -> List[Dict[str, Any]]:
            return [conv(x) for x in b.get("content", [])]

        def conv(b: Dict[str, Any]) -> Dict[str, Any]:
            t = b["type"]
            text = b.get("text", "")
            kids = kids_of(b)
            if t == "text":
                return mk("P", text=text)
            if t == "article":
                ident = b.get("identifier")
                attrs = {}
                if ident:
                    attrs["IDENTIFIER"] = ident
                if b.get("number"):
                    attrs["TI.ART"] = b["number"]  # e.g. "Article 1" (heading holds the subtitle when present)
                return hoist(mk("ARTICLE", number=ident, heading=b.get("subtitle") or b.get("number"),
                                text=text, attributes=attrs, children=kids))
            if t == "paragraph":
                ident = b.get("identifier")
                return hoist(mk("PARAG", number=b.get("number"), text=text,
                                attributes={"IDENTIFIER": ident} if ident else {}, children=kids))
            if t == "item":
                return hoist(mk("ITEM", number=b.get("number"), text=text, children=kids))
            if t == "list":
                return mk("LIST", attributes={"TYPE": b["style"]} if b.get("style") else {},
                          children=[conv(i) for i in b.get("items", [])])
            if t == "definition_list":
                return mk("DLIST", children=[
                    mk("DLIST.ITEM", text=": ".join(x for x in (i.get("term"), i.get("definition")) if x))
                    for i in b.get("items", [])])
            if t == "table":
                lines = [" | ".join(r) for r in b.get("header", []) + b.get("rows", [])]
                return mk("TBL", heading=b.get("title"), text="\n".join(lines))
            if t in ("section", "division", "subdivision"):
                tag = {"section": "GR.SEQ", "division": "DIVISION", "subdivision": "SUBDIV"}[t]
                return mk(tag, number=b.get("number"), heading=b.get("title") or b.get("subtitle"),
                          text=text, children=kids)
            if t == "quote":
                return mk("QUOT.S", children=kids)
            if t == "annotation":
                return mk("ANNOTATION", heading=b.get("title"), text=text, children=kids)
            if t == "figure":
                return mk("INCL.ELEMENT", text=b.get("caption", ""),
                          attributes={"FILEREF": b["ref"]} if b.get("ref") else {})
            if t == "signature":
                return mk("SIGNATURE", text=render_block(b))
            if t == "heading":
                return mk("HEADING", text=b.get("text", ""))
            return mk(t.upper(), text=text, children=kids)

        children: List[Dict[str, Any]] = []

        pre = doc.get("preamble")
        if pre:
            pre_kids: List[Dict[str, Any]] = []
            if pre.get("initial"):
                pre_kids.append(mk("PREAMBLE.INIT", text=pre["initial"]))
            if pre.get("visas_intro"):
                pre_kids.append(mk("GR.VISA.INIT", text=pre["visas_intro"]))
            pre_kids += [mk("VISA", text=v) for v in pre.get("visas", [])]
            if pre.get("recitals_intro"):
                pre_kids.append(mk("GR.CONSID.INIT", text=pre["recitals_intro"]))
            for r in pre.get("recitals", []):
                node = conv(r)
                node["tag"] = "CONSID"
                pre_kids.append(node)
            pre_kids += [conv(b) for b in pre.get("other", [])]
            if pre.get("final"):
                pre_kids.append(mk("PREAMBLE.FINAL", text=pre["final"]))
            children.append(mk("PREAMBLE", heading="Preamble", children=pre_kids))

        children += [conv(b) for b in doc.get("body", [])]

        if doc.get("final"):
            children.append(mk("FINAL", heading="Final Provisions",
                               children=[conv(b) for b in doc["final"].get("content", [])]))

        root = mk(doc.get("root") or "ACT", heading=doc.get("title", ""), children=children)
        root["heading"] = doc.get("title", "")
        root["notes"] = [v for k, v in notes.items() if k not in used]  # unreferenced notes
        return root

    @classmethod
    def aggregate_text(cls, node: Dict[str, Any]) -> str:
        """
        Complete text of a node in reading order: its own number/heading/text followed
        by every descendant (sub-points, bullet lists, ...). Use this when a numbered
        point must be stored/embedded as ONE record instead of one record per child.
        """
        # ARTICLE.number is the raw IDENTIFIER ("002"), not a label - context carries "Article 2"
        num = None if node.get("tag") == "ARTICLE" else node.get("number")
        own = " ".join(x for x in (num, node.get("text")) if x)
        if node.get("tag") in ("TBL", "ANNOTATION") and node.get("heading"):
            own = f"{node['heading']}\n{own}".strip()
        parts = [own]
        parts += [cls.aggregate_text(c) for c in node.get("children", [])]
        return "\n".join(p for p in parts if p)

    # =========================================================================
    # Record builder: one record per complete thought
    # =========================================================================

    _POINT_TAGS = {"PARAG", "ITEM", "CONSID"}
    _WHOLE_TAGS = {"TBL", "LIST", "DLIST", "ANNOTATION", "QUOT.S", "SIGNATURE",
                   "INCL.ELEMENT", "HEADING", "P", "DLIST.ITEM"}
    _PREAMBLE_CITATION_TAGS = {"PREAMBLE.INIT", "GR.VISA.INIT", "VISA", "GR.CONSID.INIT", "PREAMBLE.FINAL"}

    @staticmethod
    def _is_numeric_point(number: Optional[str]) -> bool:
        return bool(number) and bool(re.fullmatch(r"\d+[a-z]?", number.strip().strip("()[].:;").strip()))

    @staticmethod
    def _is_lead_in(text: str) -> bool:
        """True when the text cannot stand alone: 'shall ensure that:' / '...systems in place to'."""
        t = (text or "").rstrip()
        return bool(t) and (t[-1] in ":;,\u2014\u2013-" or t[-1].isalnum())

    def _has_sublist(self, node: Dict[str, Any]) -> bool:
        return any(c["tag"] == "LIST" or (c["tag"] in self._POINT_TAGS
                                          and not self._is_numeric_point(c.get("number")))
                   for c in node["children"])

    def _pieces(self, node: Dict[str, Any], max_chars: int) -> List[str]:
        """Whole point as one string; only if over max_chars, split at sub-point
        boundaries repeating the lead-in so no piece is a fragment of a sentence."""
        full = self.aggregate_text(node)
        if not max_chars or len(full) <= max_chars or not node["children"]:
            return [full]
        lead = " ".join(x for x in (None if node.get("tag") == "ARTICLE" else node.get("number"),
                                    node.get("text")) if x)
        out: List[str] = []
        cur: List[str] = []
        cur_len = len(lead)
        for child in node["children"]:
            for piece in self._pieces(child, max_chars):
                if cur and cur_len + len(piece) + 1 > max_chars:
                    out.append((lead + "\n" + "\n".join(cur)).strip())
                    cur, cur_len = [], len(lead)
                cur.append(piece)
                cur_len += len(piece) + 1
        if cur:
            out.append((lead + "\n" + "\n".join(cur)).strip())
        return out

    def build_records(self, parsed: Dict[str, Any], max_chars: int = 6000,
                      id_fn=None) -> List[Dict[str, Any]]:
        """
        Turn parse() output into storage/embedding records.

        Reading rules (what a human does):
          * (1), (2), (3) ... standalone points -> one record each.
          * A point followed by (a)/(b)/(i)/bullets/... -> ONE record holding the lead-in
            and every sub-point (they are one sentence spread over several lines).
          * An article/section whose own text is a lead-in ('...shall:' / 'to') or which
            has a sub-list directly beneath it -> ONE record for the whole block.
          * Preamble citations (visas) are grouped; each recital is one record.
          * Tables, definition lists, signature/final block -> one record each.
          * Nothing is emitted with empty text.
          * A merged record longer than max_chars is split at sub-point boundaries with the
            lead-in repeated in every part (part/parts set).

        Record keys: seq, fragment_id, celex, tag, number, heading, context, text,
        embedding_text (context + text), part, parts, descendants.
        id_fn(celex, seq, record) may override fragment_id (default '<celex>-<seq:04d>').
        """
        celex = (parsed.get("metadata") or {}).get("celex") or ""
        records: List[Dict[str, Any]] = []

        def emit(node: Dict[str, Any], crumbs: List[str], text_override: Optional[str] = None):
            texts = [text_override] if text_override is not None else self._pieces(node, max_chars)
            texts = [t for t in texts if t and t.strip()]
            for i, t in enumerate(texts, 1):
                rec = {
                    "seq": len(records) + 1,
                    "celex": celex,
                    "tag": node["tag"],
                    "number": node.get("number"),
                    "heading": node.get("heading"),
                    "context": " > ".join(crumbs),
                    "text": t,
                    "embedding_text": (" > ".join(crumbs) + "\n" + t) if crumbs else t,
                    "part": i if len(texts) > 1 else None,
                    "parts": len(texts) if len(texts) > 1 else None,
                    "descendants": 0 if text_override is not None else self._count_descendants(node),
                }
                rec["fragment_id"] = (id_fn(celex, rec["seq"], rec) if id_fn
                                      else f"{celex}-{rec['seq']:04d}")
                records.append(rec)

        def label(node: Dict[str, Any]) -> str:
            head = node["attributes"].get("TI.ART") or node.get("number")
            return " \u2014 ".join(x for x in (head, node.get("heading")) if x)

        def walk(node: Dict[str, Any], crumbs: List[str]):
            tag, kids = node["tag"], node["children"]
            if tag in self._POINT_TAGS or tag in self._WHOLE_TAGS or tag == "FINAL":
                emit(node, crumbs)
                return
            if tag == "PREAMBLE":
                cit = [c for c in kids if c["tag"] in self._PREAMBLE_CITATION_TAGS]
                if cit:
                    emit(node, crumbs + ["Preamble"],
                         "\n".join(self.aggregate_text(c) for c in cit))
                for c in kids:
                    if c["tag"] not in self._PREAMBLE_CITATION_TAGS:
                        walk(c, crumbs + ["Preamble"])
                return
            lab = label(node) if tag != (parsed["structure"]["tag"]) else ""
            sub = crumbs + [lab] if lab else crumbs
            own = node.get("text", "")
            if own and kids and (self._is_lead_in(own) or self._has_sublist(node)):
                emit(node, sub)                      # lead-in + everything beneath = one thought
                return
            if own:
                emit(node, sub, own)
            for c in kids:
                walk(c, sub)

        root = parsed["structure"]
        title = root.get("heading") or ""
        walk(root, [title] if title else [])
        return records

    @classmethod
    def _count_descendants(cls, node: Dict[str, Any]) -> int:
        return sum(1 + cls._count_descendants(c) for c in node.get("children", []))

    def _save_debug_json(self, celex_id: Optional[str], doc: Dict[str, Any]):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            name = celex_id or os.path.splitext(os.path.basename(self.file_path))[0]
            path = os.path.join(self.debug_dir, f"{name}_formex_parsed.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            logger.info(f"[FormexParser Debug] Saved formex_to_json output to '{path}'")
        except Exception as e:
            logger.warning(f"[FormexParser Debug] Failed to write debug JSON for '{self.file_path}': {e}")

    # =========================================================================
    # Optional engine: eurlex HTML (opt-in via use_eurlex=True)
    # =========================================================================

    def _try_eurlex(self, celex_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if eurlex is not None and celex_id:
            try:
                logger.info(f"[FormexParser] Executing eurlex engine: Fetching EUR-Lex HTML for CELEX '{celex_id}'...")

                # Fetch raw data dictionary
                raw_data = eurlex.get_data_by_celex_id(celex_id, language="en")

                # Fetch raw HTML if available in eurlex methods or via request helper
                raw_html = None
                if hasattr(eurlex, "get_html_by_celex_id"):
                    try:
                        raw_html = eurlex.get_html_by_celex_id(celex_id, language="en")
                    except Exception:
                        pass
                elif hasattr(eurlex, "get_html"):
                    try:
                        raw_html = eurlex.get_html(celex_id, language="en")
                    except Exception:
                        pass

                # Save debug copies if we obtained raw_data or raw_html
                if raw_data or raw_html:
                    self._save_debug_artifacts(celex_id, raw_html, raw_data)

                if raw_data and isinstance(raw_data, dict):
                    structure = self._transform_eurlex_dict_to_tree(raw_data)
                    logger.info(
                        f"[FormexParser] Successfully ingested CELEX '{celex_id}' using eurlex HTML source.")
                    return {
                        "metadata": {
                            "celex": celex_id,
                            "title": raw_data.get("title", ""),
                            "file_path": self.file_path,
                            "parser_engine": "eurlex-parser-html",
                            "orphan_count": 0
                        },
                        "structure": structure
                    }
                else:
                    logger.warning(f"[FormexParser] Empty dictionary returned from EUR-Lex for CELEX '{celex_id}'.")
            except Exception as err:
                logger.warning(
                    f"[FormexParser] EUR-Lex HTML fetch failed for CELEX '{celex_id}': {err}. "
                    f"Trying local engines."
                )
        elif not eurlex:
            logger.warning(
                f"[FormexParser] `eurlex` package not available. Import error: '{_EURLEX_IMPORT_ERROR}'. "
                f"Trying local engines."
            )
        else:
            logger.warning(
                f"[FormexParser] Unable to extract CELEX ID from '{self.file_path}'. "
                f"Trying local engines."
            )
        return None

    # =========================================================================
    # Debug Artifact Exporter
    # =========================================================================

    def _save_debug_artifacts(self, celex_id: str, raw_html: Optional[str], raw_data: Dict[str, Any]):
        """Saves raw HTML and formatted dictionary outputs to local directory."""
        try:
            os.makedirs(self.debug_dir, exist_ok=True)

            # Save HTML file
            if raw_html:
                html_file = os.path.join(self.debug_dir, f"{celex_id}_raw.html")
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(raw_html)
                logger.info(f"[FormexParser Debug] Saved raw HTML copy to '{html_file}'")

            # Save Dict TXT file
            if raw_data:
                txt_file = os.path.join(self.debug_dir, f"{celex_id}_parsed_dict.txt")
                with open(txt_file, "w", encoding="utf-8") as f:
                    try:
                        f.write(json.dumps(raw_data, indent=2, ensure_ascii=False))
                    except TypeError:
                        f.write(pprint.pformat(raw_data))
                logger.info(f"[FormexParser Debug] Saved parsed dictionary text to '{txt_file}'")
        except Exception as e:
            logger.warning(f"[FormexParser Debug] Failed to write debug files for CELEX '{celex_id}': {e}")

    # =========================================================================
    # CELEX Resolution Pipeline (Multi-Pass)
    # =========================================================================

    def _resolve_celex_id(self) -> Optional[str]:
        """
        Attempts 4 sequential strategies to extract CELEX ID:
        1. Deep XML tag lookup (NO.CELEX, CELEX, SAME.AS, ELI)
        2. Full-text scan of first 2000 characters of the XML file
        3. Regex match on file path & folder names
        4. CELEX extraction from OJ Official Journal numbering (e.g. L_1980018 -> 31980...)
        """
        # Pass 1: Structural XML Search
        try:
            parser = etree.XMLParser(recover=True, remove_blank_text=True)
            tree = etree.parse(self.file_path, parser)
            root = tree.getroot()

            for xpath in [".//NO.CELEX", ".//CELEX", ".//SAME.AS", ".//ELI"]:
                elem = root.find(xpath)
                if elem is not None and elem.text:
                    text_val = elem.text.strip()
                    match = self.CELEX_PATTERN.search(text_val)
                    if match:
                        return match.group(1)
        except Exception:
            pass

        # Pass 2: Quick Raw Text Scan of XML Header
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                header_text = f.read(2000)
                match = self.CELEX_PATTERN.search(header_text)
                if match:
                    return match.group(1)
        except Exception:
            pass

        # Pass 3: Directory and File Path Regex
        match = self.CELEX_PATTERN.search(self.file_path)
        if match:
            return match.group(1)

        # Pass 4: OJ Filename Heuristic (e.g., L_1980018EN.01002401.xml -> Year 1980)
        oj_match = re.search(r'L_([12][0-9]{3})([0-9]{3})', os.path.basename(self.file_path))
        if oj_match:
            year, doc_num = oj_match.group(1), oj_match.group(2)
            # Standard EU decision/directive sector prefix heuristic
            potential_celex = f"3{year}D{doc_num.zfill(4)}"
            logger.info(f"[FormexParser] Derived candidate CELEX '{potential_celex}' from OJ filename pattern.")
            return potential_celex

        return None

    # =========================================================================
    # EUR-Lex HTML Dict -> Structural Tree Adapter
    # =========================================================================

    def _transform_eurlex_dict_to_tree(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_children = []

        # 1. Preamble
        preamble = data.get("preamble") or {}
        if isinstance(preamble, dict) and preamble.get("text"):
            doc_children.append({
                "tag": "PREAMBLE",
                "attributes": {},
                "number": None,
                "heading": "Preamble",
                "text": preamble.get("text", ""),
                "references": [],
                "notes": preamble.get("notes", []),
                "children": []
            })

        # 2. Articles
        articles = data.get("articles") or []
        for art in articles:
            parent_1 = art.get("metadata", {}).get("parent_title1")
            heading_prefix = f"[{parent_1}] " if parent_1 else ""

            doc_children.append({
                "tag": "ARTICLE",
                "attributes": {},
                "number": str(art.get("id", "")),
                "heading": f"{heading_prefix}{art.get('title', '')}".strip(),
                "text": art.get("text", ""),
                "references": [{"type": "REF", "raw_text": ref} for ref in art.get("references", [])],
                "notes": art.get("notes", []),
                "children": []
            })

        # 3. Final Part
        final_part = data.get("final_part")
        if final_part:
            doc_children.append({
                "tag": "FINAL",
                "attributes": {},
                "number": None,
                "heading": "Final Provisions",
                "text": str(final_part),
                "references": [],
                "notes": [],
                "children": []
            })

        # 4. Annexes
        annexes = data.get("annexes") or []
        for idx, ann in enumerate(annexes, 1):
            text_content = ann.get("text", "")
            if ann.get("table"):
                text_content = f"{text_content}\n\n{ann.get('table')}".strip()

            doc_children.append({
                "tag": "ANNEX",
                "attributes": {},
                "number": str(ann.get("id", f"ANNEX_{idx}")),
                "heading": ann.get("title", f"Annex {idx}"),
                "text": text_content,
                "references": [],
                "notes": [],
                "children": []
            })

        return {
            "tag": "ACT",
            "attributes": {},
            "number": None,
            "heading": data.get("title", ""),
            "text": "",
            "references": [{"type": "REF", "raw_text": ref} for ref in data.get("references", [])],
            "notes": data.get("notes", []),
            "children": doc_children
        }

    # =========================================================================
    # Fallback Engine (Local lxml)
    # =========================================================================

    def _parse_with_lxml_native(self, celex_id: Optional[str]) -> Dict[str, Any]:
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        tree = etree.parse(self.file_path, parser)
        root = tree.getroot()

        metadata = self._extract_metadata(root, celex_id)

        main_elem = root.find(".//ACT")
        if main_elem is None:
            main_elem = root.find(".//DOC")
        if main_elem is None:
            main_elem = root

        structure = self._parse_element(main_elem)

        captured_fingerprints: Set[str] = set()
        self._collect_captured_fingerprints(structure, captured_fingerprints)

        orphans = self._harvest_orphaned_texts_with_sources(root, captured_fingerprints)
        metadata["orphan_count"] = len(orphans)

        if orphans:
            tag_counts: Dict[str, int] = {}
            for o in orphans:
                tag_counts[o["tag"]] = tag_counts.get(o["tag"], 0) + 1
            breakdown = ", ".join([f"<{tag}>: {count}" for tag, count in tag_counts.items()])
            logger.warning(
                f"[lxml-native] Recovered {len(orphans)} orphan block(s) for CELEX '{metadata.get('celex')}'. "
                f"Source tag breakdown -> {breakdown}"
            )

            for idx, orphan in enumerate(orphans, 1):
                structure.setdefault("children", []).append({
                    "tag": "ORPHAN_TEXT",
                    "attributes": {
                        "recovered": "true",
                        "source_tag": orphan["tag"],
                        "xpath": orphan["xpath"]
                    },
                    "number": f"ORPH-{idx}",
                    "heading": f"Unclassified Provision (<{orphan['tag']}>)",
                    "text": orphan["text"],
                    "references": [],
                    "notes": [],
                    "children": []
                })

        return {
            "metadata": metadata,
            "structure": structure
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _extract_metadata(self, root: etree._Element, celex_id: Optional[str]) -> Dict[str, Any]:
        title_elem = root.find(".//TITLE")
        if title_elem is None:
            title_elem = root.find(".//TI")
        title = self._extract_full_text(title_elem) if title_elem is not None else ""

        oj_coll = root.find(".//COLL")
        oj_no = root.find(".//NO.OJ")
        oj_date = root.find(".//DATE")

        return {
            "celex": celex_id or self.file_path,
            "title": title,
            "oj_collection": self._extract_full_text(oj_coll) if oj_coll is not None else "",
            "oj_number": self._extract_full_text(oj_no) if oj_no is not None else "",
            "date": oj_date.attrib.get("ISO") if oj_date is not None and "ISO" in oj_date.attrib else "",
            "file_path": self.file_path
        }

    def _parse_element(self, element: etree._Element) -> Dict[str, Any]:
        raw_tag = element.tag if isinstance(element.tag, str) else ""
        tag = raw_tag.split('}')[-1].upper() if '}' in raw_tag else raw_tag.upper()

        num = (
                element.attrib.get("IDENTIFIER") or
                element.attrib.get("IDENT") or
                element.attrib.get("N") or
                self._extract_child_number(element)
        )

        notes = [self._extract_full_text(n) for n in element.findall("./NOTE")]
        links = self._extract_references_and_links(element)
        heading = self._extract_heading(element)

        children = []
        for child in element:
            if not isinstance(child.tag, str):
                continue

            child_raw = child.tag
            child_tag = child_raw.split('}')[-1].upper() if '}' in child_raw else child_raw.upper()

            if child_tag in self.NUMBERING_TAGS or child_tag in {'TI', 'STI', 'TI.ART', 'STI.ART', 'DEC.TITLE',
                                                                 'TI.SECTION', 'HEADER'}:
                continue

            child_node = self._parse_element(child)
            if child_node["text"] or child_node["heading"] or child_node["children"]:
                children.append(child_node)

        if tag in self.PURE_CONTAINERS or (len(children) > 0 and tag not in self.TEXT_CONTAINERS):
            direct_text = ""
        else:
            direct_text = self._extract_direct_leaf_text(element)

        if not direct_text and not children and tag not in self.PURE_CONTAINERS:
            direct_text = self._extract_full_text(element)
            if heading and direct_text.startswith(heading):
                direct_text = direct_text[len(heading):].strip()

        return {
            "tag": tag,
            "attributes": dict(element.attrib),
            "number": num,
            "heading": heading,
            "text": direct_text,
            "references": links,
            "notes": notes,
            "children": children
        }

    def _harvest_orphaned_texts_with_sources(
            self, root: etree._Element, captured_fingerprints: Set[str]
    ) -> List[Dict[str, str]]:
        orphans = []
        search_tags = self.TEXT_CONTAINERS.union({'P', 'TXT', 'NP', 'CELL', 'ANNOTATION', 'CONSID'})
        tree = etree.ElementTree(root)

        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue

            raw_tag = elem.tag
            tag_name = raw_tag.split('}')[-1].upper() if '}' in raw_tag else raw_tag.upper()

            if tag_name in search_tags:
                text = self._extract_full_text(elem)
                if not text or len(text) < self.MIN_SENTENCE_LEN:
                    continue

                fp = self._normalize_fingerprint(text)

                is_captured = False
                if fp in captured_fingerprints:
                    is_captured = True
                else:
                    for cap_fp in captured_fingerprints:
                        if fp in cap_fp or cap_fp in fp:
                            is_captured = True
                            break

                if not is_captured:
                    xpath_str = tree.getpath(elem) if hasattr(tree, 'getpath') else ""
                    orphans.append({
                        "text": text,
                        "tag": tag_name,
                        "xpath": xpath_str if xpath_str else ""
                    })
                    captured_fingerprints.add(fp)

        return orphans

    def _normalize_fingerprint(self, text: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', text).lower()

    def _collect_captured_fingerprints(self, node: Dict[str, Any], fingerprints: Set[str]):
        if node.get("text"):
            fp = self._normalize_fingerprint(node["text"])
            if len(fp) >= self.MIN_SENTENCE_LEN:
                fingerprints.add(fp)

        for child in node.get("children", []):
            self._collect_captured_fingerprints(child, fingerprints)

    def _extract_direct_leaf_text(self, elem: etree._Element) -> str:
        text_parts = []
        if elem.text and elem.text.strip():
            text_parts.append(elem.text.strip())

        for child in elem:
            child_tag = child.tag.split('}')[-1].upper() if '}' in child.tag else child.tag.upper()
            if child_tag in {'HT', 'QUOT.S', 'QUOT.E', 'DATE', 'REF.DOC.EC', 'LINK'}:
                text_parts.append(self._extract_full_text(child))
            if child.tail and child.tail.strip():
                text_parts.append(child.tail.strip())

        return self._normalize_whitespace(" ".join(text_parts))

    def _extract_child_number(self, elem: etree._Element) -> Optional[str]:
        for num_tag in self.NUMBERING_TAGS:
            num_elem = elem.find(f"./{num_tag}")
            if num_elem is not None:
                return self._extract_full_text(num_elem)
        return None

    def _extract_heading(self, elem: etree._Element) -> Optional[str]:
        heading_paths = ['./STI.ART', './STI', './TI.ART', './TI/P', './TI', './TITLE/TI', './NO.ANNEX', './TI.SECTION']
        for head_tag in heading_paths:
            head_elem = elem.find(head_tag)
            if head_elem is not None:
                text = self._extract_full_text(head_elem)
                if text:
                    return text
        return None

    def _extract_references_and_links(self, elem: etree._Element) -> List[Dict[str, Any]]:
        refs = []
        for ref in elem.findall("./REF.DOC.EC"):
            refs.append({
                "type": "REF.DOC.EC",
                "doc_type": ref.attrib.get("TYPE"),
                "year": ref.attrib.get("YEAR"),
                "number": ref.attrib.get("NO.DOC"),
                "raw_text": self._extract_full_text(ref)
            })
        for link in elem.findall("./LINK"):
            refs.append({
                "type": "LINK",
                "href": link.attrib.get("HREF"),
                "raw_text": self._extract_full_text(link)
            })
        return refs

    def _extract_full_text(self, elem: etree._Element) -> str:
        text = "".join(elem.itertext())
        text = text.replace('\u00a0', ' ').replace('\u202f', ' ')
        return self._normalize_whitespace(text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()
