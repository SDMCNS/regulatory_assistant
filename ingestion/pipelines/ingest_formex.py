"""
Formex XML ingestion pipeline.

Scans a directory of EU Formex XML/ZIP files, groups them into coherent packages,
classifies them into Core Regulations, Directives, Decisions (Qualifiers DB),
Corrigenda, and Annexes. Consolidates technical annexes into their primary regulations,
isolates master metadata wrappers (.doc/.toc), and persists everything to SQLite + FAISS.

Usage::

    python -m ingestion.pipelines.ingest_formex ./data/regulations -l 10 --reset
"""

import sys
import os
import json
import re
import shutil
import hashlib
import zipfile
import logging
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

from lxml import etree

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from ingestion.euroform.parser import parse_formex
from ingestion.euroform.render import render_block
from ingestion.pipelines.chunking_pipeline import ChunkerPipeline
from ingestion.retrieval.embed_chunks import run_embedding_pipeline
from ingestion.core.config import settings
from ingestion.core.formex_package import (
    FormexPackage,
    FormexFileMeta,
    LegalClassification,
    discover_formex_packages,
    iter_formex_packages,
    classify_package,
    extract_root_and_metadata,
    is_aviation_text,
    resolve_canonical_celex,
    parse_eu_doc_number,
    AVIATION_KEYWORDS,
    AVIATION_PATTERN,
    IGNORED_FILES,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("ingestion_pipeline.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("IngestionPipeline")

# Footnote markers emitted by euroform, e.g. "[^E0001]"
_NOTE_MARK = re.compile(r"\s?\[\^([^\]]+)\]")
CELEX_PATTERN = re.compile(r"\b([1-9][0-9]{4}[A-Z]{1,2}[0-9]{3,4})\b")


# ═══════════════════════════════════════════════════════════════════════════
# Euroform → Legacy-Tree Adapter
# ═══════════════════════════════════════════════════════════════════════════

def _euroform_doc_to_tree(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a parsed euroform document dict into the node-tree schema."""
    notes = doc.get("notes") or {}
    used: Set[str] = set()

    def clean(text: Optional[str]) -> str:
        return _NOTE_MARK.sub("", text or "").strip()

    def mk(
        tag: str,
        number=None,
        heading=None,
        text: str = "",
        attributes: Optional[Dict[str, str]] = None,
        children: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        node_notes: List[str] = []
        for src in (text, heading):
            for nid in _NOTE_MARK.findall(f" {src or ''}"):
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
                attrs["TI.ART"] = b["number"]
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
                for i in b.get("items", [])
            ])
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
    root["notes"] = [v for k, v in notes.items() if k not in used]
    return root


def _metadata_from_euroform(doc: Dict[str, Any], celex_id: Optional[str], file_path: str) -> Dict[str, Any]:
    """Build the flat metadata dict expected by downstreams from euroform."""
    m = doc.get("metadata") or {}
    oj = m.get("official_journal") or {}
    ids = m.get("identifiers") or []

    meta: Dict[str, Any] = {
        "celex": celex_id or file_path,
        "title": doc.get("title", ""),
        "oj_collection": oj.get("collection", ""),
        "oj_number": oj.get("number", ""),
        "date": (m.get("date") or "").replace("-", ""),
        "publication_date": m.get("date"),
        "file_path": file_path,
        "parser_engine": "euroform",
    }
    if m.get("language"):
        meta["language"] = m["language"]
    if m.get("document_type"):
        meta["document_type"] = m["document_type"]
    if ids:
        meta["doc_numbers"] = ids
    if m.get("eea_relevance"):
        meta["eea_relevance"] = True
    if doc.get("anonymised"):
        meta["anonymised"] = True
    return meta


def resolve_celex_id(file_path: str) -> Optional[str]:
    """Multi-pass CELEX ID extraction."""
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        tree = etree.parse(file_path, parser)
        root = tree.getroot()
        for xpath in [".//NO.CELEX", ".//CELEX", ".//SAME.AS", ".//ELI"]:
            elem = root.find(xpath)
            if elem is not None and elem.text:
                match = CELEX_PATTERN.search(elem.text.strip())
                if match:
                    return match.group(1)
    except Exception:
        pass

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            header_text = f.read(2000)
            match = CELEX_PATTERN.search(header_text)
            if match:
                return match.group(1)
    except Exception:
        pass

    match = CELEX_PATTERN.search(file_path)
    if match:
        return match.group(1)

    oj_match = re.search(r"L_([12][0-9]{3})([0-9]{3})", os.path.basename(file_path))
    if oj_match:
        year, doc_num = oj_match.group(1), oj_match.group(2)
        return f"3{year}D{doc_num.zfill(4)}"

    return None


def is_aviation_related(file_path: Path) -> bool:
    """Returns True if any aviation keywords are found in file header/title."""
    try:
        for event, elem in etree.iterparse(
            str(file_path),
            events=("end",),
            tag=("TITLE", "TITLE.FINAL", "TI", "STI", "PREAMBLE.INIT"),
        ):
            text = "".join(elem.itertext()).strip()
            if text and AVIATION_PATTERN.search(text):
                elem.clear()
                return True
            elem.clear()
    except Exception:
        pass
    return False


def find_xml_files(input_dir: Path, extract_zips: bool = True) -> List[Path]:
    """Backward-compatible discovery: returns all non-ignored XML files."""
    xml_paths: List[Path] = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            p = Path(root) / file
            fl = file.lower()
            if extract_zips and fl.endswith(".zip"):
                tgt = p.parent / f"_extracted_{p.stem}"
                if not tgt.exists():
                    try:
                        with zipfile.ZipFile(p, "r") as zr:
                            zr.extractall(tgt)
                    except Exception:
                        continue
                for zroot, _, zfiles in os.walk(tgt):
                    for zf in zfiles:
                        if zf.lower().endswith(".xml") and zf.lower() not in IGNORED_FILES:
                            xml_paths.append(Path(zroot) / zf)
            elif fl.endswith(".xml") and fl not in IGNORED_FILES:
                xml_paths.append(p)
    return sorted(xml_paths)


# ═══════════════════════════════════════════════════════════════════════════
# Regulations Archive
# ═══════════════════════════════════════════════════════════════════════════

def resolve_regulations_dir(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).resolve()
    configured = getattr(settings, "REGULATIONS_DIR", None)
    if configured:
        return Path(configured).resolve()
    db_path = Path(getattr(settings, "SQLITE_DB_PATH", Path("data/sqlite/regulatory_knowledge.db")))
    return db_path.resolve().parent.parent / "regulations"


class RegulationArchive:
    """Keeps XML sources and parsed JSON in the archive."""
    INDEX_NAME = "regulations_index.json"

    def __init__(self, directory: Path, create: bool = True):
        self.directory = Path(directory)
        if create:
            self.directory.mkdir(parents=True, exist_ok=True)
        self.index_path = self.directory / self.INDEX_NAME
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._owners: Dict[str, str] = {}
        self._load()

    def _load(self):
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            for e in data.get("regulations", []):
                self._entries[e["file_name"]] = e
                self._owners[e["file_name"]] = e.get("source_path", "")
        except Exception as e:
            logger.warning(f"[Archive] Could not read existing index {self.index_path}: {e}")

    def save(self):
        payload = {
            "updated": datetime.now().isoformat(timespec="seconds"),
            "count": len(self._entries),
            "regulations": sorted(self._entries.values(), key=lambda e: e["file_name"].lower()),
        }
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.index_path)

    def _archive_name(self, src: Path) -> str:
        name, src_key = src.name, str(src.resolve())
        owner = self._owners.get(name)
        if owner in (None, "", src_key):
            return name
        base, dot, rest = name.partition(".")
        return f"{base}__{hashlib.sha1(src_key.encode()).hexdigest()[:8]}{dot}{rest}"

    @staticmethod
    def _json_name(archive_name: str) -> str:
        return (archive_name[:-4] if archive_name.lower().endswith(".xml") else archive_name) + ".json"

    def store_source(self, src: Path) -> str:
        name = self._archive_name(src)
        dest = self.directory / name
        st = src.stat()
        if not dest.exists() or dest.stat().st_size != st.st_size or dest.stat().st_mtime < st.st_mtime:
            shutil.copy2(src, dest)
        self._owners[name] = str(src.resolve())
        return name

    def store_json_and_index(
        self, archive_name: str, src: Path, parsed: Dict[str, Any],
        celex: str, regulation: str, num_records: int,
    ):
        json_name = self._json_name(archive_name)
        tmp = (self.directory / json_name).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(parsed, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        os.replace(tmp, self.directory / json_name)

        self._entries[archive_name] = {
            "file_name": archive_name,
            "regulation": regulation,
            "celex": celex,
            "num_records": num_records,
            "json_file": json_name,
            "source_path": str(src.resolve()),
        }
        self.save()

    def purge(self):
        for e in list(self._entries.values()):
            for key in ("file_name", "json_file"):
                f = self.directory / e.get(key, "")
                if e.get(key) and f.is_file():
                    try:
                        f.unlink()
                    except Exception:
                        pass
        if self.index_path.exists():
            self.index_path.unlink()
        self._entries.clear()
        self._owners.clear()
        logger.info(f"Cleared regulations archive: {self.directory}")


def reset_environment(regulations_dir: Optional[Path] = None):
    logger.info("=" * 60)
    logger.info("RESET OPTION TRIGGERED: Wiping old DB and generated files...")
    logger.info("=" * 60)

    db_path = getattr(settings, "SQLITE_DB_PATH", Path("data/sqlite/regulatory_knowledge.db"))
    vector_dir = getattr(settings, "VECTOR_INDEX_DIR", Path("data/vector_store/"))
    jsonl_path = getattr(settings, "JSONL_OUTPUT_PATH", Path("data/jsonl/fragments.jsonl"))

    files_to_remove = [
        Path(db_path),
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        Path(jsonl_path),
        Path("ingested_regulations_summary.txt"),
    ]

    for f in files_to_remove:
        if f.exists():
            try:
                f.unlink()
                logger.info(f"Removed file: {f}")
            except Exception as e:
                logger.warning(f"Failed to remove {f}: {e}")

    vector_path = Path(vector_dir)
    if vector_path.exists() and vector_path.is_dir():
        for file in vector_path.glob("*"):
            if file.is_file():
                try:
                    file.unlink()
                    logger.info(f"Removed vector artifact: {file}")
                except Exception as e:
                    logger.warning(f"Failed to remove vector artifact {file}: {e}")

    if regulations_dir is not None:
        RegulationArchive(regulations_dir, create=False).purge()

    logger.info("Environment reset complete. Starting fresh ingestion.\n")


# ═══════════════════════════════════════════════════════════════════════════
# Summary Report
# ═══════════════════════════════════════════════════════════════════════════

def write_summary_report(
    output_file: Path,
    core_records: List[Dict[str, Any]],
    qualifier_records: List[Dict[str, Any]],
    execution_time: str,
    total_packages_scanned: int,
    total_annexes_grouped: int,
    total_wrappers_skipped: int,
):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write("                 EU AVIATION REGULATIONS CONSOLIDATED INGESTION REPORT\n")
        f.write(f" Generated At               : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f" Total Publication Packages : {total_packages_scanned}\n")
        f.write(f" Core Regulations Ingested  : {len(core_records)} (Active Knowledge Base Target)\n")
        f.write(f" Attached Annexes Grouped   : {total_annexes_grouped} (Consolidated with parent regulations)\n")
        f.write(f" Supporting Qualifiers DB   : {len(qualifier_records)} (Decisions & Corrigenda linked by ID)\n")
        f.write(f" Master Wrappers Isolated   : {total_wrappers_skipped} (.doc/.toc wrappers excluded)\n")
        f.write(f" Total Ingestion Duration   : {execution_time}\n")
        f.write("=" * 100 + "\n\n")

        f.write("#" * 100 + "\n")
        f.write(" SECTION 1: CORE AVIATION REGULATIONS (KNOWLEDGE BASE)\n")
        f.write("#" * 100 + "\n\n")

        if not core_records:
            f.write("No core aviation regulations were ingested during this run.\n\n")
        else:
            for idx, rec in enumerate(core_records, 1):
                f.write(f"[{idx}] {rec['celex']} | {rec.get('doc_number', 'N/A')} | File: {rec['file_name']}\n")
                f.write(f"    Title          : {rec['title']}\n")
                f.write(f"    Chunks         : {rec.get('num_chunks', 0)} chunks generated\n")
                if rec.get("annex_files"):
                    f.write(f"    Attached Annexes ({len(rec['annex_files'])}): {', '.join(rec['annex_files'])}\n")
                if rec.get("amends_regs"):
                    f.write(f"    Amends Regs    : {', '.join(rec['amends_regs'])}\n")
                if rec.get("repeals_regs"):
                    f.write(f"    Repeals Regs   : {', '.join(rec['repeals_regs'])}\n")
                f.write("-" * 100 + "\n")

        f.write("\n" + "#" * 100 + "\n")
        f.write(" SECTION 2: SUPPORTING QUALIFIERS (DECISIONS & CORRIGENDA DATABASE)\n")
        f.write(" Associated back to their target regulations by reference ID.\n")
        f.write("#" * 100 + "\n\n")

        if not qualifier_records:
            f.write("No supporting qualifiers were registered during this run.\n\n")
        else:
            for idx, q in enumerate(qualifier_records, 1):
                f.write(f"[{idx}] {q['qualifier_type']} | {q['qualifier_id']} | Date: {q.get('date', 'N/A')}\n")
                f.write(f"    Title               : {q['title']}\n")
                f.write(f"    Supports Regulation : {q.get('target_regulation_ref') or '[Autonomous / General]'}\n")
                f.write(f"    Source File         : {q['source_file']}\n")
                f.write("-" * 100 + "\n")

    logger.info(f"Consolidated ingestion summary report saved to: {output_file.resolve()}")


# ═══════════════════════════════════════════════════════════════════════════
# Core Ingestion Processing
# ═══════════════════════════════════════════════════════════════════════════

def process_regulation_package(
    pkg: FormexPackage,
    chunker_pipeline: ChunkerPipeline,
    archive: RegulationArchive,
) -> Optional[Dict[str, Any]]:
    """Parses a Core Regulation package, merges attached Annexes, generates chunks,
    and updates SQLite."""
    if not pkg.primary_file:
        logger.warning(f"Package in {pkg.folder_path.name} has no primary file. Skipping.")
        return None

    primary_path = pkg.primary_file.path

    # 1. Parse primary Act XML
    doc = parse_formex(str(primary_path))
    if not (doc.get("body") or doc.get("preamble") or doc.get("final")):
        logger.warning(f"euroform produced empty content for {primary_path.name}")
        return None

    # 2. Parse and attach all Annexes
    attached_annexes = []
    for annex_meta in pkg.annex_files:
        try:
            annex_doc = parse_formex(str(annex_meta.path))
            annex_title = annex_doc.get("title") or annex_meta.title or f"ANNEX ({annex_meta.filename})"
            attached_annexes.append({
                "title": annex_title,
                "body": annex_doc.get("body", []),
                "metadata": annex_doc.get("metadata", {}),
                "source_file": annex_meta.filename,
            })
            # Also store source annex XML in archive
            archive.store_source(annex_meta.path)
            logger.info(f"Attached annex {annex_meta.filename} to {primary_path.name}")
        except Exception as e:
            logger.warning(f"Failed to parse annex {annex_meta.filename}: {e}")

    if attached_annexes:
        doc["annexes"] = attached_annexes

    # 3. Canonical CELEX & Metadata Enrichment
    celex_id = pkg.celex or resolve_celex_id(str(primary_path)) or f"ACT_{primary_path.stem.upper()}"
    act_title = doc.get("title") or pkg.title or primary_path.stem

    metadata = _metadata_from_euroform(doc, celex_id, str(primary_path))
    metadata["doc_number"] = pkg.doc_number
    metadata["celex"] = celex_id
    metadata["status"] = pkg.status
    metadata["annex_count"] = len(attached_annexes)
    metadata["annex_files"] = [a.filename for a in pkg.annex_files]
    metadata["amends_regs"] = pkg.amends_regs
    metadata["repeals_regs"] = pkg.repeals_regs
    metadata["keywords"] = pkg.matched_keywords
    metadata["wrapper_files"] = [w.filename for w in pkg.wrapper_files]
    doc["metadata"] = metadata
    doc["title"] = act_title

    # 4. Store primary source & JSON in archive
    archive_name = archive.store_source(primary_path)
    archive.store_json_and_index(
        archive_name, primary_path, doc, celex_id, act_title, 0
    )
    json_file_path = archive.directory / archive._json_name(archive_name)

    # 5. Process through ChunkerPipeline
    chunks = chunker_pipeline.process_file(json_file_path)
    chunks_len = len(chunks)

    # Update index with exact chunk count
    if archive_name in archive._entries:
        archive._entries[archive_name]["num_records"] = chunks_len
        archive.save()

    logger.info(f"Ingested {act_title[:70]}... -> {chunks_len} chunks (including {len(attached_annexes)} annexes)")

    return {
        "celex": celex_id,
        "doc_number": pkg.doc_number,
        "title": act_title,
        "file_name": primary_path.name,
        "num_chunks": chunks_len,
        "annex_files": [a.filename for a in pkg.annex_files],
        "amends_regs": pkg.amends_regs,
        "repeals_regs": pkg.repeals_regs,
    }


def process_qualifier_package(
    pkg: FormexPackage,
    chunker_pipeline: ChunkerPipeline,
    archive: RegulationArchive,
) -> Optional[Dict[str, Any]]:
    """Parses a Decision or Corrigendum and records it in the qualifiers database."""
    primary_meta = pkg.primary_file or (pkg.corrigendum_files[0] if pkg.corrigendum_files else None)
    if not primary_meta:
        return None

    primary_path = primary_meta.path
    q_type = "CORRIGENDUM" if pkg.classification == LegalClassification.CORRIGENDUM else "DECISION"

    content_snippet = ""
    try:
        doc = parse_formex(str(primary_path))
        body_blocks = doc.get("body", [])
        content_parts = []
        for b in body_blocks[:5]:
            if b.get("text"):
                content_parts.append(b["text"])
        content_snippet = "\n\n".join(content_parts)
    except Exception:
        content_snippet = primary_meta.title or ""

    qualifier_id = primary_path.stem
    target_ref = pkg.target_regulation or ""
    parent_reg_id = None

    if target_ref:
        t_match = re.search(r"(\d+)/(\d+)", target_ref)
        if t_match:
            n1, n2 = t_match.group(1), t_match.group(2)
            yr = n2 if len(n2) == 4 else n1
            num = n1 if yr == n2 else n2
            parent_reg_id = resolve_canonical_celex("R", yr, num)

    pub_date = (pkg.primary_file.title or "")[:20] if pkg.primary_file else None

    # Archive source XML
    archive.store_source(primary_path)

    # Store in qualifiers table
    chunker_pipeline.store_qualifier(
        qualifier_id=qualifier_id,
        title=pkg.title,
        qualifier_type=q_type,
        parent_regulation_id=parent_reg_id,
        target_regulation_ref=target_ref,
        celex=pkg.celex,
        date=pub_date,
        source_file=primary_path.name,
        content_text=content_snippet,
        metadata={
            "amends": pkg.amends_regs,
            "repeals": pkg.repeals_regs,
            "keywords": pkg.matched_keywords,
            "folder": str(pkg.folder_path),
        }
    )

    logger.info(f"Registered {q_type}: {pkg.title[:70]}... -> Supporting {target_ref or '[Autonomous]'}")

    return {
        "qualifier_id": qualifier_id,
        "qualifier_type": q_type,
        "title": pkg.title,
        "target_regulation_ref": target_ref,
        "source_file": primary_path.name,
        "date": pub_date,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(
    input_directory: str,
    limit: Optional[int] = None,
    reset: bool = False,
    defrag: bool = False,
    regulations_dir: Optional[str] = None,
    include_non_aviation: bool = False,
):
    input_path = Path(input_directory)
    if not input_path.exists():
        logger.error(f"Input directory does not exist: {input_directory}")
        sys.exit(1)

    archive_dir = resolve_regulations_dir(regulations_dir)
    if reset:
        reset_environment(archive_dir)

    # Initialise pipeline components
    db_path = str(archive_dir / "sqlite" / "chunks.db")
    chunker_pipeline = ChunkerPipeline(db_path)
    archive = RegulationArchive(archive_dir)
    logger.info(f"Regulations archive: {archive_dir}")

    # Metrics
    ingested_core: List[Dict[str, Any]] = []
    registered_qualifiers: List[Dict[str, Any]] = []
    total_annexes_grouped = 0
    total_wrappers_skipped = 0
    filtered_out = 0
    failed_docs = 0
    scanned_packages = 0

    pipeline_start_time = time.time()

    for pkg in iter_formex_packages(input_path):
        scanned_packages += 1
        if limit is not None and limit > 0 and len(ingested_core) >= limit:
            logger.info(f"\nReached target limit of {limit} core aviation regulation(s). Stopping scan.")
            break

        # Check Aviation Relevance
        if not include_non_aviation and not pkg.is_aviation:
            filtered_out += 1
            continue

        elapsed_str = str(timedelta(seconds=int(time.time() - pipeline_start_time)))
        limit_str = f" / Target: {limit}" if limit else ""
        logger.info(
            f"\n--- [Package {scanned_packages} | Ingested Core: {len(ingested_core)}{limit_str} | Qualifiers: {len(registered_qualifiers)}] "
            f"Elapsed: {elapsed_str} ---"
        )
        logger.info(f"Package: {pkg.folder_path.name} | Type: {pkg.classification.value} | Title: {pkg.title[:80]}")

        # Account for metadata wrappers safely skipped
        total_wrappers_skipped += len(pkg.wrapper_files)

        try:
            if pkg.classification in (LegalClassification.CORE_REGULATION, LegalClassification.DIRECTIVE, LegalClassification.INTERNATIONAL_AGREEMENT):
                rec = process_regulation_package(pkg, chunker_pipeline, archive)
                if rec:
                    ingested_core.append(rec)
                    total_annexes_grouped += len(pkg.annex_files)
            elif pkg.classification in (LegalClassification.QUALIFIER_DECISION, LegalClassification.CORRIGENDUM, LegalClassification.RECOMMENDATION):
                q_rec = process_qualifier_package(pkg, chunker_pipeline, archive)
                if q_rec:
                    registered_qualifiers.append(q_rec)
            else:
                logger.info(f"Skipping package of type {pkg.classification.value}")
        except Exception as e:
            failed_docs += 1
            logger.error(f"Error processing package {pkg.folder_path.name}: {e}", exc_info=True)

    # Generate Embeddings for new chunks
    logger.info("Running embedding pipeline for new chunks...")
    try:
        run_embedding_pipeline(db_path=Path(db_path))
    except Exception as e:
        logger.warning(f"Embedding pipeline step skipped / error: {e}")

    total_duration = str(timedelta(seconds=int(time.time() - pipeline_start_time)))

    # Generate Summary Report
    summary_txt_path = Path("ingested_regulations_summary.txt")
    write_summary_report(
        summary_txt_path,
        ingested_core,
        registered_qualifiers,
        total_duration,
        scanned_packages,
        total_annexes_grouped,
        total_wrappers_skipped,
    )

    # Defrag if requested
    if defrag:
        try:
            import sqlite3
            logger.info("Running VACUUM and WAL checkpoint on SQLite DB...")
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.execute("VACUUM;")
            logger.info("Database defragmentation complete.")
        except Exception as e:
            logger.warning(f"Defrag warning: {e}")

    logger.info("=" * 60)
    logger.info("CONSOLIDATED INGESTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Packages Scanned      : {scanned_packages}")
    logger.info(f"Core Regulations Ingested   : {len(ingested_core)}")
    logger.info(f"Attached Annexes Grouped    : {total_annexes_grouped}")
    logger.info(f"Supporting Qualifiers Saved : {len(registered_qualifiers)}")
    logger.info(f"Master Wrappers Excluded    : {total_wrappers_skipped}")
    logger.info(f"Non-Aviation Filtered Out   : {filtered_out}")
    logger.info(f"Errors / Failures           : {failed_docs}")
    logger.info(f"Total Execution Time        : {total_duration}")
    logger.info(f"Summary Report File         : {summary_txt_path.resolve()}")
    logger.info("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Ingest Formex XML regulations into SQLite and FAISS with package grouping."
    )
    arg_parser.add_argument(
        "input_directory",
        type=str,
        help="Path to directory containing Formex XML or ZIP files.",
    )
    arg_parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Maximum number of core aviation regulations to ingest.",
    )
    arg_parser.add_argument(
        "-r", "--reset",
        action="store_true",
        help="Clear existing database, vector indices, and output summary files before running.",
    )
    arg_parser.add_argument(
        "-d", "--defrag",
        action="store_true",
        help="Run SQLite VACUUM and WAL checkpoint optimization after ingestion.",
    )
    arg_parser.add_argument(
        "--regulations-dir",
        type=str,
        default=None,
        help="Where to copy matched XML files, their JSON and regulations_index.json.",
    )
    arg_parser.add_argument(
        "--all-domains",
        action="store_true",
        help="Ingest all legal acts regardless of aviation domain relevance.",
    )

    args = arg_parser.parse_args()
    run_pipeline(
        input_directory=args.input_directory,
        limit=args.limit,
        reset=args.reset,
        defrag=args.defrag,
        regulations_dir=args.regulations_dir,
        include_non_aviation=args.all_domains,
    )
