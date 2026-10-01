"""
Formex XML ingestion pipeline.

Scans a directory of EU Formex XML/ZIP files, filters for aviation-related
regulations, parses them via the local ``euroform`` library, builds canonical
legal fragments, extracts relationships, generates embeddings, and persists
everything to SQLite + FAISS.

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
# Local imports – everything is co-located inside ``ingestion``
# ---------------------------------------------------------------------------
# Ensure the project root and current directory are in sys.path
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IGNORED_XML_NAMES = {"manifest.xml", "mets.xml", "biblio.xml", "notice.xml"}

# CELEX regex: Sector (1-9), Year (4 digits), DocType (1-2 letters), Number (3-4 digits)
CELEX_PATTERN = re.compile(r"\b([1-9][0-9]{4}[A-Z]{1,2}[0-9]{3,4})\b")

# Footnote markers emitted by euroform, e.g. "[^E0001]"
_NOTE_MARK = re.compile(r"\s?\[\^([^\]]+)\]")

# Domain-specific keyword regex dictionary for fast title matching
AVIATION_KEYWORDS = {
    r"\baviation\b", r"\bairlift\b", r"\baircraft\b", r"\bairplane\b", r"\bairport\b", r"\bairports\b",
    r"\bair carrier\b", r"\bair carriers\b", r"\bairline\b", r"\bairlines\b", r"\bair line\b",
    r"\bair transport\b", r"\bair navigation\b", r"\bair traffic\b", r"\bairspace\b",
    r"\bflight\b", r"\bflights\b", r"\bflight data\b", r"\baeronautical\b", r"\baerodrome\b",
    r"\beasa\b", r"\beurocontrol\b", r"\bsesar\b", r"\bicao\b", r"\biata\b",
    r"\bsingle european sky\b", r"\bsky\b", r"\batm/ans\b", r"\bairworthiness\b",
    r"\bcabin\b", r"\bcabin crew\b", r"\bpilot\b", r"\bpilots\b", r"\bpassenger rights\b",
    r"\bdenied boarding\b", r"\bdrone\b", r"\bdrones\b", r"\bu-space\b", r"\buas\b", r"\brpas\b",
    r"\bcorsia\b", r"\bsaf\b", r"\bsustainable aviation\b", r"\bjet fuel\b", r"\bkerosene\b",
    r"\bslot allocation\b", r"\bslots\b",
}

# Pre-compile single combined regex pattern for high execution speed
AVIATION_PATTERN = re.compile("|".join(AVIATION_KEYWORDS), re.IGNORECASE)


# ═══════════════════════════════════════════════════════════════════════════
# Euroform → Legacy-Tree Adapter
# ═══════════════════════════════════════════════════════════════════════════

def _euroform_doc_to_tree(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a parsed euroform document dict into the legacy node-tree schema
    expected by :class:`FragmentBuilder`.

    The legacy schema uses::

        {"tag", "attributes", "number", "heading", "text", "references",
         "notes", "children"}
    """
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
        """Point intro sentence → the point's own text; children are sub-points."""
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
    """Build the flat metadata dict expected by :class:`FragmentBuilder` from
    the euroform document."""
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
    # Additive extra fields
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


# ═══════════════════════════════════════════════════════════════════════════
# CELEX Resolution
# ═══════════════════════════════════════════════════════════════════════════

def resolve_celex_id(file_path: str) -> Optional[str]:
    """Multi-pass CELEX ID extraction from XML content, file path, and OJ
    naming conventions."""
    # Pass 1: Structural XML search
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

    # Pass 2: Raw text header scan
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            header_text = f.read(2000)
            match = CELEX_PATTERN.search(header_text)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Pass 3: Directory / file path regex
    match = CELEX_PATTERN.search(file_path)
    if match:
        return match.group(1)

    # Pass 4: OJ filename heuristic
    oj_match = re.search(r"L_([12][0-9]{3})([0-9]{3})", os.path.basename(file_path))
    if oj_match:
        year, doc_num = oj_match.group(1), oj_match.group(2)
        return f"3{year}D{doc_num.zfill(4)}"

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Aviation-relevance filter & XML discovery
# ═══════════════════════════════════════════════════════════════════════════

def extract_title_text(file_path: Path) -> str:
    """Extracts raw text from title tags without building the full DOM tree."""
    title_parts: List[str] = []
    try:
        for event, elem in etree.iterparse(
            str(file_path),
            events=("end",),
            tag=("TITLE", "TITLE.FINAL", "TI", "STI", "PREAMBLE.INIT"),
        ):
            text = "".join(elem.itertext()).strip()
            if text:
                title_parts.append(text)
            elem.clear()
            if len(title_parts) >= 10:
                break
    except Exception as e:
        logger.debug(f"Fast title scan warning for {file_path.name}: {e}")
    return " ".join(title_parts)


def is_aviation_related(file_path: Path) -> bool:
    """Returns True if any aviation keywords are found in the document title/header."""
    title_text = extract_title_text(file_path)
    if not title_text:
        return False
    return bool(AVIATION_PATTERN.search(title_text))


def deduplicate_xml_paths(xml_paths: List[Path]) -> List[Path]:
    """Deduplicates Formex XML files per folder.
    If 'name.doc.xml' and 'name.xml' exist in the same folder, drops 'name.doc.xml'.
    """
    grouped_by_folder: Dict[Path, Set[Path]] = {}
    for p in xml_paths:
        grouped_by_folder.setdefault(p.parent, set()).add(p)

    canonical_paths: List[Path] = []
    for folder, paths in grouped_by_folder.items():
        file_map = {p.name.lower(): p for p in paths}
        for name_lower, file_path in file_map.items():
            if name_lower.endswith(".doc.xml"):
                base_name = name_lower[:-8] + ".xml"
                if base_name in file_map:
                    logger.debug(f"Skipping duplicate Formex file: {file_path.name} (using {base_name})")
                    continue
            canonical_paths.append(file_path)
    return sorted(canonical_paths)


def find_xml_files(input_dir: Path, extract_zips: bool = True) -> List[Path]:
    """Walk *input_dir*, extract ZIPs on the fly, return deduplicated XML paths."""
    raw_xml_paths: List[Path] = []

    for root, _, files in os.walk(input_dir):
        for file in files:
            file_path = Path(root) / file
            file_lower = file.lower()

            if extract_zips and file_lower.endswith(".zip"):
                extract_target = file_path.parent / f"_extracted_{file_path.stem}"
                if not extract_target.exists():
                    logger.info(f"Extracting ZIP: {file_path.name}")
                    try:
                        with zipfile.ZipFile(file_path, "r") as zip_ref:
                            zip_ref.extractall(extract_target)
                    except Exception as e:
                        logger.error(f"Failed to extract {file_path}: {e}")
                        continue

                for zroot, _, zfiles in os.walk(extract_target):
                    for zfile in zfiles:
                        if zfile.lower().endswith(".xml") and zfile.lower() not in IGNORED_XML_NAMES:
                            raw_xml_paths.append(Path(zroot) / zfile)

            elif file_lower.endswith(".xml"):
                if file_lower in IGNORED_XML_NAMES:
                    continue
                raw_xml_paths.append(file_path)

    return deduplicate_xml_paths(raw_xml_paths)


# ═══════════════════════════════════════════════════════════════════════════
# Regulations archive & environment helpers
# ═══════════════════════════════════════════════════════════════════════════

def resolve_regulations_dir(override: Optional[str] = None) -> Path:
    """Regulations archive location:
    --regulations-dir > settings.REGULATIONS_DIR > sibling of DB folder.
    """
    if override:
        return Path(override).resolve()
    configured = getattr(settings, "REGULATIONS_DIR", None)
    if configured:
        return Path(configured).resolve()
    db_path = Path(getattr(settings, "SQLITE_DB_PATH", Path("data/sqlite/regulatory_knowledge.db")))
    return db_path.resolve().parent.parent / "regulations"


class RegulationArchive:
    """Keeps, for every positively identified (aviation) regulation:
      * a copy of the source Formex XML
      * the parser's JSON (<name>.json) next to it
      * an entry in regulations_index.json
    """

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
            logger.warning(f"[Archive] Could not read existing index {self.index_path} ({e}); starting a new one.")

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
                    except Exception as err:
                        logger.warning(f"Failed to remove archived file {f}: {err}")
        if self.index_path.exists():
            self.index_path.unlink()
        self._entries.clear()
        self._owners.clear()
        logger.info(f"Cleared regulations archive: {self.directory}")


def reset_environment(regulations_dir: Optional[Path] = None):
    """Clears existing databases, vector stores, JSONL outputs, logs and the
    regulations archive to allow a fresh run."""
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
# Summary report
# ═══════════════════════════════════════════════════════════════════════════

def write_summary_report(
    output_file: Path,
    report_records: List[Dict[str, Any]],
    execution_time: str,
    total_scanned: int,
):
    """Generates a user-friendly plain text report of all processed regulations."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write("                          EU AVIATION REGULATIONS INGESTION REPORT\n")
        f.write(f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f" Total Formex Files Scanned: {total_scanned}\n")
        f.write(f" Aviation Acts Ingested    : {len(report_records)}\n")
        f.write(f" Total Ingestion Duration  : {execution_time}\n")
        f.write("=" * 100 + "\n\n")

        if not report_records:
            f.write("No aviation regulations were successfully ingested during this run.\n")
            return

        for idx, rec in enumerate(report_records, 1):
            f.write(f"[{idx}] {rec['celex']} | Year: {rec['year']} | File: {rec['file_name']}\n")
            f.write(f"    Title        : {rec['title']}\n")
            f.write(
                    f"    Records      : {rec.get('num_chunks', 0)} Chunks generated\n"
            )
            f.write("-" * 100 + "\n")

    logger.info(f"Ingestion summary report generated: {output_file.resolve()}")


# ═══════════════════════════════════════════════════════════════════════════
# Core parsing function  (euroform → tree → fragments)
# ═══════════════════════════════════════════════════════════════════════════

def parse_formex_file(file_path: Path) -> Dict[str, Any]:
    """Parse a single Formex XML file and return::

        {"metadata": {...}, "structure": {...}, "raw_doc": {...}}

    Uses the ``euroform`` library as the primary (and only) parser engine.
    """
    celex_id = resolve_celex_id(str(file_path))

    doc = parse_formex(str(file_path))

    if not (doc.get("body") or doc.get("preamble") or doc.get("final")):
        raise ValueError(
            f"euroform produced no body/preamble/final for '{file_path.name}' "
            f"(root <{doc.get('root')}>)"
        )

    structure = _euroform_doc_to_tree(doc)
    metadata = _metadata_from_euroform(doc, celex_id, str(file_path))

    logger.info(f"Parsed '{file_path.name}' with euroform (root <{doc.get('root')}>).")
    return {"metadata": metadata, "structure": structure, "raw_doc": doc}


# ═══════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(
    input_directory: str,
    limit: Optional[int] = None,
    reset: bool = False,
    defrag: bool = False,
    regulations_dir: Optional[str] = None,
):
    input_path = Path(input_directory)
    if not input_path.exists():
        logger.error(f"Input directory does not exist: {input_directory}")
        sys.exit(1)

    archive_dir = resolve_regulations_dir(regulations_dir)
    if reset:
        reset_environment(archive_dir)

    logger.info(f"Scanning directory tree: {input_directory}")
    xml_files = find_xml_files(input_path)

    if not xml_files:
        logger.error(f"No valid legal XML files found under: {input_directory}")
        return

    total_scanned_files = len(xml_files)
    logger.info(f"Discovered {total_scanned_files} unique FORMEX XML file(s) across subdirectories.")
    if limit is not None and limit > 0:
        logger.info(f"Aviation match target limit set to: {limit} act(s).")

    # --- Initialise pipeline components ---
    db_path = str(archive_dir / "sqlite" / "chunks.db")
    chunker_pipeline = ChunkerPipeline(db_path)
    archive = RegulationArchive(archive_dir)
    logger.info(f"Regulations archive: {archive_dir}")

    # Counters
    successful_docs = 0
    skipped_unchanged = 0
    filtered_out_docs = 0
    failed_docs = 0
    matched_aviation_count = 0

    report_records: List[Dict[str, Any]] = []
    pipeline_start_time = time.time()
    idx = 0

    for idx, file_path in enumerate(xml_files, 1):
        if limit is not None and limit > 0 and matched_aviation_count >= limit:
            logger.info(f"\nReached target limit of {limit} matched aviation regulation(s). Stopping pipeline scan.")
            break

        elapsed_seconds = time.time() - pipeline_start_time
        elapsed_str = str(timedelta(seconds=int(elapsed_seconds)))
        limit_str = f" / Target Limit: {limit}" if limit else ""

        logger.info(
            f"\n--- [Scanned: {idx}/{total_scanned_files} | Matched Aviation: {matched_aviation_count}{limit_str}] "
            f"Elapsed: {elapsed_str} ---"
        )
        logger.info(f"Checking: {file_path.name}")

        # --- STEP 0: Aviation Relevance Filter ---
        if not is_aviation_related(file_path):
            logger.info(f"Skipping non-aviation act: {file_path.name}")
            filtered_out_docs += 1
            continue

        matched_aviation_count += 1
        logger.info(
            f"MATCH [{matched_aviation_count}]: Aviation regulation identified in {file_path.name}. "
            f"Proceeding to ingestion."
        )

        # Archive source XML
        archive_name: Optional[str] = None
        try:
            archive_name = archive.store_source(file_path)
        except Exception as e:
            logger.warning(f"[Archive] Could not copy {file_path.name}: {e}")

        try:
            # 1. Parse Formex XML via euroform
            parsed = parse_formex_file(file_path)
            meta = parsed["metadata"]
            raw_doc = parsed["raw_doc"]

            act_id = meta["celex"] or f"ACT_{file_path.stem.upper()}"
            act_title = parsed["structure"].get("heading") or meta.get("celex") or file_path.stem

            # Archive JSON + index entry
            json_file_path = None
            if archive_name:
                try:
                    archive.store_json_and_index(
                        archive_name, file_path, raw_doc, act_id, act_title, 0
                    )
                    json_file_path = archive.directory / archive._json_name(archive_name)
                except Exception as e:
                    logger.warning(f"[Archive] Could not archive JSON/index for {file_path.name}: {e}")

            pub_year = (meta.get("publication_date") or "")[:4] or "N/A"
            chunks_len = 0

            # Process chunks
            if json_file_path and json_file_path.exists():
                chunks = chunker_pipeline.process_file(json_file_path)
                chunks_len = len(chunks)
                successful_docs += 1

            report_records.append({
                "celex": act_id,
                "year": pub_year,
                "title": act_title,
                "file_name": file_path.name,
                "num_chunks": chunks_len,
            })

            logger.info(f"Successfully processed {chunks_len} chunks from {file_path.name}")

        except Exception as e:
            failed_docs += 1
            logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
            continue

    # 8. Generate Embeddings for the processed chunks
    logger.info("Running embedding pipeline for new chunks...")
    run_embedding_pipeline()

    total_duration = str(timedelta(seconds=int(time.time() - pipeline_start_time)))

    # 9. Generate Text Summary File
    summary_txt_path = Path("ingested_regulations_summary.txt")
    write_summary_report(summary_txt_path, report_records, total_duration, idx)

    logger.info("=" * 60)
    logger.info("INGESTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Files Scanned  : {idx}")
    logger.info(f"Aviation Matched     : {matched_aviation_count}")
    logger.info(f"Filtered Out (Other) : {filtered_out_docs}")
    logger.info(f"Successfully Ingested: {successful_docs}")
    logger.info(f"Skipped (Unchanged)  : {skipped_unchanged}")
    logger.info(f"Failed / Errors      : {failed_docs}")
    logger.info(f"Total Execution Time : {total_duration}")
    logger.info(f"Summary Report File  : {summary_txt_path.resolve()}")
    logger.info(f"Regulations Archive  : {archive_dir} ({len(archive._entries)} indexed)")
    logger.info("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Ingest Formex XML regulations into SQLite and FAISS."
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
        help="Maximum number of aviation-matched XML files to process (useful for fast testing).",
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
        help="Where to copy matched XML files, their JSON and regulations_index.json "
             "(default: 'regulations' folder beside the DB folder).",
    )

    args = arg_parser.parse_args()
    run_pipeline(
        input_directory=args.input_directory,
        limit=args.limit,
        reset=args.reset,
        defrag=args.defrag,
        regulations_dir=args.regulations_dir,
    )
