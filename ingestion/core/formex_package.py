"""
Core Formex Package grouping and legal classification engine.

Inspects Formex XML directories, classifies files according to EU legal nature
(Act, Annex, Decision, Corrigendum, Metadata Wrapper), groups annexes and wrappers
into unified packages, and tracks regulatory relationships (amends, repeals).
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from lxml import etree

# ---------------------------------------------------------------------------
# Constants & Aviation Patterns
# ---------------------------------------------------------------------------
IGNORED_FILES = {"manifest.xml", "mets.xml", "biblio.xml", "notice.xml"}

AVIATION_KEYWORDS = [
    r"\baviation\b", r"\bairlift\b", r"\baircraft\b", r"\bairplane\b",
    r"\bairport\b", r"\bairports\b", r"\bair carrier\b", r"\bair carriers\b",
    r"\bairline\b", r"\bairlines\b", r"\bair transport\b", r"\bair navigation\b",
    r"\bair traffic\b", r"\bairspace\b", r"\bflight\b", r"\bflights\b",
    r"\bflight data\b", r"\baeronautical\b", r"\baerodrome\b", r"\beasa\b",
    r"\beurocontrol\b", r"\bsesar\b", r"\bicao\b", r"\biata\b",
    r"\bsingle european sky\b", r"\bsky\b", r"\batm/ans\b", r"\bairworthiness\b",
    r"\bcabin crew\b", r"\bpilot\b", r"\bpilots\b", r"\bdenied boarding\b",
    r"\bpassenger rights\b", r"\bdrone\b", r"\bdrones\b", r"\bu-space\b",
    r"\buas\b", r"\brpas\b", r"\bcorsia\b", r"\bsaf\b",
    r"\bsustainable aviation\b", r"\bjet fuel\b", r"\bkerosene\b",
    r"\bslot allocation\b", r"\baviation safety\b", r"\baviation security\b",
]

AVIATION_PATTERN = re.compile("|".join(AVIATION_KEYWORDS), re.IGNORECASE)

REPEAL_PATTERNS = [
    re.compile(r"repealing\s+(?:Council\s+|Commission\s+)?(?:Regulation|Directive)\s+(?:\([A-Z]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", re.IGNORECASE),
    re.compile(r"repeals?\s+(?:Regulation|Directive)\s+(?:\([A-Z]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", re.IGNORECASE),
]

AMEND_PATTERNS = [
    re.compile(r"amending\s+(?:Council\s+|Commission\s+)?(?:Regulation|Directive)\s+(?:\([A-Z]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", re.IGNORECASE),
    re.compile(r"amends?\s+(?:Regulation|Directive)\s+(?:\([A-Z]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", re.IGNORECASE),
]

DECISION_SUPPORT_REGEX = re.compile(
    r"(?:pursuant to|in accordance with|application of|under Article\s+[\d\w\(\)\.]+\s+of)\s+"
    r"(?:Regulation|Directive)\s+(?:\([A-Z,\s]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)",
    re.IGNORECASE
)


class LegalClassification(str, Enum):
    CORE_REGULATION = "CORE_REGULATION"      # Direct KB Target: Regulations
    DIRECTIVE = "DIRECTIVE"                  # Direct KB Target: Directives
    QUALIFIER_DECISION = "QUALIFIER_DECISION"# Segregated Qualifiers DB: Decisions
    CORRIGENDUM = "CORRIGENDUM"              # Non-independent modification
    INTERNATIONAL_AGREEMENT = "AGREEMENT"    # Bilateral / multilateral aviation treaties
    RECOMMENDATION = "RECOMMENDATION"        # Recommendations & Guidance
    ANNEX = "ANNEX"                          # Attached technical annex
    METADATA_WRAPPER = "METADATA_WRAPPER"    # Master .doc/.toc wrappers
    OTHER = "OTHER"                          # Unclassified


@dataclass
class FormexFileMeta:
    path: Path
    filename: str
    root_tag: str
    doc_ref: Optional[str] = None
    seq_no: Optional[str] = None
    title: Optional[str] = None
    is_aviation: bool = False
    keywords: List[str] = field(default_factory=list)
    target_regulation: Optional[str] = None


@dataclass
class FormexPackage:
    folder_path: Path
    classification: LegalClassification
    primary_file: Optional[FormexFileMeta] = None
    annex_files: List[FormexFileMeta] = field(default_factory=list)
    wrapper_files: List[FormexFileMeta] = field(default_factory=list)
    corrigendum_files: List[FormexFileMeta] = field(default_factory=list)
    title: str = ""
    celex: Optional[str] = None
    doc_number: Optional[str] = None
    is_aviation: bool = False
    matched_keywords: List[str] = field(default_factory=list)
    amends_regs: List[str] = field(default_factory=list)
    repeals_regs: List[str] = field(default_factory=list)
    target_regulation: Optional[str] = None
    status: str = "IN FORCE"


def is_aviation_text(text: str) -> Tuple[bool, List[str]]:
    if not text:
        return False, []
    matches = set(m.group(0).lower() for m in AVIATION_PATTERN.finditer(text))
    return bool(matches), sorted(list(matches))


def extract_root_and_metadata(xml_path: Path) -> FormexFileMeta:
    """Stream-reads root tag, sequence numbers, document references, and titles."""
    root_tag = "UNKNOWN"
    doc_ref = None
    seq_no = None
    title_parts = []
    target_regulation = None

    try:
        context = etree.iterparse(
            str(xml_path),
            events=("start", "end"),
            tag=("ANNEX", "ACT", "CORR", "DOC", "PUBLICATION", "TOC",
                 "DOCUMENT.REF", "NO.SEQ", "TITLE", "TITLE.FINAL", "TI",
                 "DOC.CORR", "NO.DOC", "NO.CURRENT", "YEAR", "COM")
        )
        for event, elem in context:
            tag = elem.tag
            if event == "start":
                if root_tag == "UNKNOWN" and tag in ("ANNEX", "ACT", "CORR", "DOC", "PUBLICATION", "TOC"):
                    root_tag = tag
                if tag == "DOCUMENT.REF" and doc_ref is None:
                    doc_ref = elem.get("FILE")
            elif event == "end":
                if tag == "NO.SEQ" and seq_no is None:
                    seq_no = "".join(elem.itertext()).strip()
                elif tag in ("TITLE", "TITLE.FINAL", "TI") and len(title_parts) < 3:
                    txt = "".join(elem.itertext()).strip()
                    if txt:
                        title_parts.append(txt)
                elif tag == "DOC.CORR":
                    try:
                        no_curr = elem.find(".//NO.CURRENT")
                        year_el = elem.find(".//YEAR")
                        com_el = elem.find(".//COM")
                        if no_curr is not None and year_el is not None:
                            curr_text = "".join(no_curr.itertext()).strip()
                            yr_text = "".join(year_el.itertext()).strip()
                            com_text = "".join(com_el.itertext()).strip() if com_el is not None else ""
                            target_regulation = f"{curr_text}/{yr_text}" if not com_text else f"{curr_text}/{yr_text} ({com_text})"
                    except Exception:
                        pass
                
                # Free memory selectively
                if tag in ("TITLE", "TITLE.FINAL", "TI", "DOC.CORR", "DOCUMENT.REF"):
                    elem.clear()

            if root_tag != "UNKNOWN" and len(title_parts) >= 2 and tag == "ENACTING.TERMS":
                break
    except Exception:
        pass

    full_title = " ".join(title_parts).strip()
    is_av, kw = is_aviation_text(full_title)

    return FormexFileMeta(
        path=xml_path,
        filename=xml_path.name,
        root_tag=root_tag,
        doc_ref=doc_ref,
        seq_no=seq_no,
        title=full_title,
        is_aviation=is_av,
        keywords=kw,
        target_regulation=target_regulation
    )


def parse_eu_doc_number(title: str, default_year: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extracts document type, year, and sequential number from EU legal titles."""
    if not title:
        return None, None, None

    # Post-2015 pattern: (EU) 2018/1139
    match_post_2015 = re.search(r"\((?:EU|Euratom)\)\s+(\d{4})/(\d+)", title, re.IGNORECASE)
    if match_post_2015:
        year, num = match_post_2015.group(1), match_post_2015.group(2)
        doc_type = "R" if "regulation" in title.lower() else "D" if "decision" in title.lower() else "L"
        return doc_type, year, num

    # Pre-2015 pattern: (EC) No 965/2012 or (EEC) No 3922/91
    match_pre_2015 = re.search(r"\((?:EC|EEC|Euratom)\)\s+No\s+(\d+)/(\d{2,4})", title, re.IGNORECASE)
    if match_pre_2015:
        num, yr = match_pre_2015.group(1), match_pre_2015.group(2)
        year = f"19{yr}" if len(yr) == 2 and int(yr) > 50 else f"20{yr}" if len(yr) == 2 else yr
        doc_type = "R" if "regulation" in title.lower() else "D" if "decision" in title.lower() else "L"
        return doc_type, year, num

    # Directive pattern: 2014/30/EU
    match_dir = re.search(r"Directive\s+(\d{4})/(\d+)/(?:EU|EC)", title, re.IGNORECASE)
    if match_dir:
        return "L", match_dir.group(1), match_dir.group(2)

    # Decision pattern: Decision 2012/780/EU or (2004/636/EC)
    match_dec = re.search(r"Decision\s+(?:No\s+)?(\d{4})/(\d+)", title, re.IGNORECASE)
    if match_dec:
        return "D", match_dec.group(1), match_dec.group(2)

    return None, None, None


def resolve_canonical_celex(doc_type: str, year: str, number: str) -> str:
    """Computes standard 3YYYYXNNNN CELEX identifier."""
    if not year or not number:
        return ""
    num_padded = number.zfill(4)
    letter = doc_type.upper() if doc_type else "R"
    return f"3{year}{letter}{num_padded}"


def extract_regulatory_relations(text: str) -> Tuple[List[str], List[str]]:
    """Extracts amending and repealing cross-references from titles and initial text."""
    if not text:
        return [], []
    amends = set()
    for pat in AMEND_PATTERNS:
        for m in pat.finditer(text):
            amends.add(m.group(1))

    repeals = set()
    for pat in REPEAL_PATTERNS:
        for m in pat.finditer(text):
            repeals.add(m.group(1))

    return sorted(list(amends)), sorted(list(repeals))


def extract_decision_target_regulation(title: str) -> Optional[str]:
    """Identifies the primary EU regulation that a Decision is implementing or qualifying."""
    if not title:
        return None
    match = DECISION_SUPPORT_REGEX.search(title)
    if match:
        return f"Regulation {match.group(1)}"
    match_fallback = re.search(r"Regulation\s+(?:\([A-Z,\s]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", title, re.IGNORECASE)
    if match_fallback:
        return f"Regulation {match_fallback.group(1)}"
    return None


def extract_corrigendum_target(xml_path: Path, title: str) -> Optional[str]:
    """Resolves target regulation number from Corrigendum header."""
    if title:
        match = re.search(r"Corrigendum to\s+.*?(?:Regulation|Directive)\s+(?:\([A-Z,\s]+\)\s+)?(?:No\s+)?(\d+/\d+|\d+)", title, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def classify_package(files: List[FormexFileMeta], folder: Path) -> Optional[FormexPackage]:
    """Groups folder XMLs and assigns legal classification and package metadata."""
    if not files:
        return None

    primary_file: Optional[FormexFileMeta] = None
    annex_files: List[FormexFileMeta] = []
    wrapper_files: List[FormexFileMeta] = []
    corrigendum_files: List[FormexFileMeta] = []

    for f in files:
        fn_lower = f.filename.lower()
        if fn_lower.endswith(".doc.xml") or fn_lower.endswith(".doc.fmx.xml") or fn_lower.endswith(".toc.xml") or fn_lower.endswith(".toc.fmx.xml") or f.root_tag in ("DOC", "PUBLICATION", "TOC"):
            wrapper_files.append(f)
        elif f.root_tag == "ANNEX" or ".010045" in f.filename or ".0004" in f.filename or "annex" in fn_lower:
            annex_files.append(f)
        elif f.root_tag == "CORR" or "corrigendum" in (f.title or "").lower():
            corrigendum_files.append(f)
        elif f.root_tag == "ACT":
            if primary_file is None:
                primary_file = f
            else:
                annex_files.append(f)
        else:
            if primary_file is None:
                primary_file = f
            else:
                wrapper_files.append(f)

    # Determine aviation relevance across entire package
    all_titles = " ".join(filter(None, [f.title for f in files]))
    is_av, matched_kw = is_aviation_text(all_titles)

    main_title = primary_file.title if primary_file and primary_file.title else (files[0].title or "")
    if not main_title and wrapper_files and wrapper_files[0].title:
        main_title = wrapper_files[0].title

    # Determine legal classification
    classification = LegalClassification.OTHER
    t_lower = main_title.lower()

    if primary_file and primary_file.root_tag == "CORR":
        classification = LegalClassification.CORRIGENDUM
    elif corrigendum_files and not primary_file:
        classification = LegalClassification.CORRIGENDUM
        primary_file = corrigendum_files[0]
    elif re.search(r"^\s*(?:Commission\s+|Council\s+)?(?:Implementing\s+|Delegated\s+)?Decision\b", main_title, re.IGNORECASE):
        classification = LegalClassification.QUALIFIER_DECISION
    elif "decision" in t_lower and not re.search(r"^\s*(?:Commission\s+|Council\s+)?(?:Implementing\s+|Delegated\s+)?Regulation\b", main_title, re.IGNORECASE):
        classification = LegalClassification.QUALIFIER_DECISION
    elif "directive" in t_lower:
        classification = LegalClassification.DIRECTIVE
    elif "regulation" in t_lower:
        classification = LegalClassification.CORE_REGULATION
    elif "agreement" in t_lower or "protocol" in t_lower:
        classification = LegalClassification.INTERNATIONAL_AGREEMENT
    elif "recommendation" in t_lower:
        classification = LegalClassification.RECOMMENDATION
    elif primary_file and primary_file.root_tag == "ACT":
        classification = LegalClassification.CORE_REGULATION

    # Extract numbering & relationships
    doc_type, year, num = parse_eu_doc_number(main_title)
    celex = resolve_canonical_celex(doc_type or "R", year or "", num or "") if year and num else None
    doc_number = f"{num}/{year}" if year and num and int(year) < 2015 else f"{year}/{num}" if year and num else None

    amends_regs, repeals_regs = extract_regulatory_relations(all_titles)

    target_reg = None
    if classification == LegalClassification.QUALIFIER_DECISION:
        target_reg = extract_decision_target_regulation(main_title)
    elif classification == LegalClassification.CORRIGENDUM:
        if primary_file and primary_file.target_regulation:
            target_reg = primary_file.target_regulation
        else:
            target_reg = extract_corrigendum_target(primary_file.path if primary_file else folder, main_title)

    return FormexPackage(
        folder_path=folder,
        classification=classification,
        primary_file=primary_file,
        annex_files=annex_files,
        wrapper_files=wrapper_files,
        corrigendum_files=corrigendum_files,
        title=main_title,
        celex=celex,
        doc_number=doc_number,
        is_aviation=is_av,
        matched_keywords=matched_kw,
        amends_regs=amends_regs,
        repeals_regs=repeals_regs,
        target_regulation=target_reg,
        status="IN FORCE"
    )


def iter_formex_packages(input_dir: Path, extract_zips: bool = True):
    """Walks directory and yields FormexPackage objects lazily."""
    for root, dirs, files in os.walk(input_dir):
        if extract_zips:
            for f in files:
                if f.lower().endswith(".zip"):
                    zip_path = Path(root) / f
                    target_dir = zip_path.parent / f"_extracted_{zip_path.stem}"
                    if not target_dir.exists():
                        try:
                            with zipfile.ZipFile(zip_path, "r") as zr:
                                zr.extractall(target_dir)
                        except Exception:
                            pass

        xml_files = [f for f in files if f.lower().endswith(".xml") and f.lower() not in IGNORED_FILES]
        if not xml_files:
            continue

        folder = Path(root)
        folder_files: List[FormexFileMeta] = []
        for fn in xml_files:
            meta = extract_root_and_metadata(folder / fn)
            folder_files.append(meta)

        pkg = classify_package(folder_files, folder)
        if pkg:
            yield pkg


def discover_formex_packages(input_dir: Path, limit_dirs: Optional[int] = None) -> List[FormexPackage]:
    """Scans Formex publications and constructs unified packages."""
    packages: List[FormexPackage] = []
    for pkg in iter_formex_packages(input_dir):
        packages.append(pkg)
        if limit_dirs and len(packages) >= limit_dirs:
            break
    return packages
