#!/usr/bin/env python3
"""
Formex Regulation Pre-Processing Sanity Check
============================================
A standalone pre-ingestion diagnostic tool that scans EU Formex XML files,
identifies aviation-related legal acts, classifies them by legal nature,
and groups associated files (Acts, Annexes, Corrigenda, Metadata Wrappers)
so that annexes and corrections are never stored as orphan/isolated regulations.

Key Features:
  - High-speed targeted Formex XML parsing (using lxml with streaming event limits).
  - Aviation relevance filtering based on domain keywords and acronyms.
  - Formex document nature classification (Regulation, Directive, Decision, Corrigendum, Annex).
  - File packaging and hierarchical grouping (via NO.SEQ, DOCUMENT.REF, and folder scope).
  - Decision/Qualifier isolation and association back to supported regulations.
  - Corrigenda detection and association back to modified regulations.
  - Validity and lifecycle analysis (repeal cross-referencing and expiration date checks).
  - Formatted text report generation without modifying the underlying filesystem.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import lxml.etree as etree
    USE_LXML = True
except ImportError:
    import xml.etree.ElementTree as etree  # type: ignore
    USE_LXML = False


# ═══════════════════════════════════════════════════════════════════════════
# Aviation Relevance Filtering (Exact keywords from ingestion pipeline)
# ═══════════════════════════════════════════════════════════════════════════

AVIATION_KEYWORDS: Set[str] = {
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

AVIATION_PATTERN = re.compile("|".join(AVIATION_KEYWORDS), re.IGNORECASE)

# File names that are pure plumbing / packaging metadata
IGNORED_PLUMBING_NAMES = {"manifest.xml", "mets.xml", "biblio.xml", "notice.xml"}

# Regex for standard EU Regulation/Decision/Directive citation patterns
REG_CITATION_PATTERN = re.compile(
    r"(?:Regulation|Directive|Decision)\s*\((?:EU|EC|EEC)\)\s*(?:No\s*)?(\d+/\d+|\d+/\d+)",
    re.IGNORECASE,
)
DECISION_SUPPORT_PATTERN = re.compile(
    r"(?:pursuant to|in accordance with(?:\s+Article\s+[0-9a-zA-Z().]+)?(?:\s+of)?|under|laid down in)\s+(?:Commission\s+|Council\s+)?(?:Implementing\s+|Delegated\s+)?Regulation\s*\((?:EU|EC|EEC)\)\s*(?:No\s*)?(\d+/\d+|\d+/\d+)",
    re.IGNORECASE,
)
REPEAL_PATTERN = re.compile(
    r"repealing\s+(?:Regulations?|Directives?|Decisions?)\s*([^,;]+)",
    re.IGNORECASE,
)
REPEALED_DOC_NUMS = re.compile(
    r"(?:\((?:EU|EC|EEC)\)|(?:EEC|EC|EU))\s*(?:No\s*)?(\d+/\d+)",
    re.IGNORECASE,
)
EXPIRY_PATTERN = re.compile(
    r"(?:shall\s+expire\s+on|shall\s+apply\s+until|until)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)


def parse_eu_doc_number(doc_num_str: str) -> Tuple[str, str]:
    """Given '2025/24' or '965/2012' or '2256/2022', returns (year, number)."""
    parts = doc_num_str.split("/")
    if len(parts) == 2:
        p1, p2 = parts[0].strip(), parts[1].strip()
        # Case A: p1 is 4-digit year (1950-2035) and p2 is not
        if len(p1) == 4 and p1.isdigit() and 1950 <= int(p1) <= 2035 and not (len(p2) == 4 and p2.isdigit() and 1950 <= int(p2) <= 2035):
            return p1, p2
        # Case B: p2 is 4-digit year (1950-2035) and p1 is not
        elif len(p2) == 4 and p2.isdigit() and 1950 <= int(p2) <= 2035 and not (len(p1) == 4 and p1.isdigit() and 1950 <= int(p1) <= 2035):
            return p2, p1
        # Case C: Both are 4 digits (e.g. 2022/2256 or 2256/2022)
        elif len(p1) == 4 and p1.isdigit() and len(p2) == 4 and p2.isdigit():
            if int(p1) <= 2030 and int(p2) > 2030:
                return p1, p2
            elif int(p2) <= 2030 and int(p1) > 2030:
                return p2, p1
            return p1, p2
        # Case D: 2-digit year (e.g. 3922/91)
        elif len(p2) <= 2 and p2.isdigit():
            yr = ("19" if int(p2) > 50 else "20") + p2.zfill(2)
            return yr, p1
    return "0000", doc_num_str


# ═══════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FileMetadata:
    """Metadata extracted from a single Formex XML file."""
    file_path: Path
    file_name: str
    folder_id: str
    root_tag: str
    is_wrapper: bool = False             # e.g. .doc.xml or .toc.xml
    wrapper_type: Optional[str] = None   # 'DOC', 'TOC', 'MANIFEST'
    doc_ref_file: Optional[str] = None   # DOCUMENT.REF FILE="..."
    no_seq: Optional[str] = None         # BIB.INSTANCE / NO.SEQ (e.g. '0002', '0002.0001')
    doc_num_current: Optional[str] = None
    doc_num_year: Optional[str] = None
    doc_num_com: Optional[str] = None
    doc_type_tag: Optional[str] = None
    iso_date: Optional[str] = None
    title: str = ""
    durab_type: Optional[str] = None
    corr_target_doc: Optional[str] = None  # from DOC.CORR / NO.DOC
    corr_target_oj: Optional[str] = None   # from DOC.CORR / NO.OJ
    aviation_matched: bool = False
    matched_keywords: List[str] = field(default_factory=list)
    repeals_raw: List[str] = field(default_factory=list)
    expiry_raw: Optional[str] = None


@dataclass
class DocumentPackage:
    """A logically grouped EU legal act and all its associated components."""
    group_id: str                          # Canonical ID or Stem
    package_type: str                      # 'REGULATION', 'DIRECTIVE', 'DECISION', 'CORRIGENDUM', 'AGREEMENT', 'QUALIFIER_NOTE'
    canonical_title: str
    celex_id: Optional[str] = None
    doc_number: Optional[str] = None       # e.g. "2018/1139" or "965/2012"
    adoption_date: Optional[str] = None
    validity_status: str = "IN FORCE"      # 'IN FORCE', 'REPEALED', 'EXPIRED', 'TIME_LIMITED'
    repealed_by: Optional[str] = None
    expiry_date: Optional[str] = None
    
    primary_act_file: Optional[Path] = None
    annex_files: List[Tuple[Path, str]] = field(default_factory=list)      # (Path, subtitle)
    corrigenda_files: List[Tuple[Path, str]] = field(default_factory=list) # (Path, description)
    metadata_files: List[Path] = field(default_factory=list)               # .doc.xml, .toc.xml
    
    # Relationships
    supported_regulations: List[str] = field(default_factory=list)         # For Decisions/Qualifiers
    primary_supported_reg: Optional[str] = None                            # Specifically identified parent reg
    amended_regulations: List[str] = field(default_factory=list)           # Regs this act amends
    repealed_regulations: List[str] = field(default_factory=list)          # Regs this act repeals
    
    # Aviation metadata
    is_aviation: bool = False
    aviation_keywords: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Formex XML Inspector
# ═══════════════════════════════════════════════════════════════════════════

class FormexInspector:
    """Fast, memory-efficient streaming scanner for Formex XML files."""

    @staticmethod
    def inspect_file(file_path: Path) -> Optional[FileMetadata]:
        file_name = file_path.name
        file_lower = file_name.lower()

        is_doc_wrapper = file_lower.endswith((".doc.xml", ".doc.fmx.xml"))
        is_toc_wrapper = file_lower.endswith((".toc.xml", ".toc.fmx.xml"))
        is_plumbing = file_lower in IGNORED_PLUMBING_NAMES or is_doc_wrapper or is_toc_wrapper

        folder_id = file_path.parent.parent.name if file_path.parent.name == "fmx4" else file_path.parent.name

        try:
            root_tag = ""
            doc_ref_file = None
            no_seq = None
            doc_num_cur = None
            doc_num_yr = None
            doc_num_com = None
            doc_type_tag = None
            iso_date = None
            durab_type = None
            corr_target_doc = None
            corr_target_oj = None
            title_parts: List[str] = []
            preamble_parts: List[str] = []

            context = etree.iterparse(
                str(file_path),
                events=("start", "end"),
                recover=True if USE_LXML else False,
            )

            for event, elem in context:
                raw_tag = elem.tag
                tag = raw_tag.split("}")[-1] if "}" in raw_tag else raw_tag

                if event == "start":
                    if not root_tag:
                        root_tag = tag

                elif event == "end":
                    if tag in {"BIB.INSTANCE", "BIB.DOC"}:
                        doc_ref = elem.find(".//DOCUMENT.REF")
                        if doc_ref is not None:
                            doc_ref_file = doc_ref.attrib.get("FILE")
                        no_seq = elem.findtext(".//NO.SEQ")
                        date_el = elem.find(".//DATE")
                        if date_el is not None:
                            iso_date = date_el.attrib.get("ISO") or date_el.text
                        doc_type_el = elem.find(".//DOC.TYPE")
                        if doc_type_el is not None and doc_type_el.text:
                            doc_type_tag = doc_type_el.text.strip()
                        durab_el = elem.find(".//DURAB")
                        if durab_el is not None:
                            durab_type = durab_el.attrib.get("TYPE")
                        no_doc = elem.find(".//NO.DOC")
                        if no_doc is not None:
                            cur = no_doc.findtext("NO.CURRENT")
                            yr = no_doc.findtext("YEAR")
                            com = no_doc.findtext("COM")
                            if cur:
                                doc_num_cur = cur.strip()
                            if yr:
                                doc_num_yr = yr.strip()
                            if com:
                                doc_num_com = com.strip()
                        elem.clear()

                    elif tag == "DOC.CORR":
                        no_oj = elem.findtext(".//NO.OJ")
                        if no_oj:
                            corr_target_oj = no_oj.strip()
                        no_doc = elem.find(".//NO.DOC")
                        if no_doc is not None:
                            cur = no_doc.findtext("NO.CURRENT", "")
                            yr = no_doc.findtext("YEAR", "")
                            com = no_doc.findtext("COM", "")
                            corr_target_doc = f"{cur}/{yr}/{com}".strip("/")
                        elem.clear()

                    elif tag in {"TITLE", "TI", "TITLE.FINAL"}:
                        t_text = " ".join("".join(elem.itertext()).split())
                        if t_text:
                            title_parts.append(t_text)
                        elem.clear()

                    elif tag in {"PREAMBLE.INIT", "PREAMBLE"}:
                        p_text = " ".join("".join(elem.itertext()).split())
                        if p_text and len(preamble_parts) < 3:
                            preamble_parts.append(p_text[:500])
                        elem.clear()

                    elif tag in {"ENACTING.TERMS", "CONTENTS", "CONTENTS.CORR", "BODY"}:
                        break

            full_title = " ".join(title_parts)
            preamble_text = " ".join(preamble_parts)
            combined_header = f"{full_title} {preamble_text}"

            aviation_matched = False
            matched_keywords: List[str] = []
            if combined_header:
                matches = list(set(m.group(0).lower() for m in AVIATION_PATTERN.finditer(combined_header)))
                if matches:
                    aviation_matched = True
                    matched_keywords = sorted(matches)

            repeals: List[str] = []
            repeal_matches = REPEAL_PATTERN.findall(combined_header)
            for rm in repeal_matches:
                doc_nums = REPEALED_DOC_NUMS.findall(rm)
                for dn in doc_nums:
                    repeals.append(dn.strip())

            expiry_str = None
            exp_match = EXPIRY_PATTERN.search(combined_header)
            if exp_match:
                expiry_str = exp_match.group(1).strip()

            wrapper_type = None
            if is_doc_wrapper:
                wrapper_type = "DOC"
            elif is_toc_wrapper:
                wrapper_type = "TOC"
            elif file_lower in IGNORED_PLUMBING_NAMES:
                wrapper_type = "MANIFEST"

            return FileMetadata(
                file_path=file_path,
                file_name=file_name,
                folder_id=folder_id,
                root_tag=root_tag or "UNKNOWN",
                is_wrapper=is_plumbing,
                wrapper_type=wrapper_type,
                doc_ref_file=doc_ref_file,
                no_seq=no_seq,
                doc_num_current=doc_num_cur,
                doc_num_year=doc_num_yr,
                doc_num_com=doc_num_com,
                doc_type_tag=doc_type_tag,
                iso_date=iso_date,
                title=full_title,
                durab_type=durab_type,
                corr_target_doc=corr_target_doc,
                corr_target_oj=corr_target_oj,
                aviation_matched=aviation_matched,
                matched_keywords=matched_keywords,
                repeals_raw=repeals,
                expiry_raw=expiry_str,
            )

        except Exception as e:
            return FileMetadata(
                file_path=file_path,
                file_name=file_name,
                folder_id=folder_id,
                root_tag="CORRUPTED",
                is_wrapper=is_plumbing,
                title=f"Error reading XML: {e}",
            )


# ═══════════════════════════════════════════════════════════════════════════
# Legal Document Classifier & Grouping Engine
# ═══════════════════════════════════════════════════════════════════════════

class FormexClassifier:
    """Classifies Formex files and groups them into logical legal units."""

    @staticmethod
    def classify_act_type(meta: FileMetadata) -> str:
        """Determines the exact legal nature of an act file based on root tag and title."""
        if meta.is_wrapper or meta.root_tag in {"DOC", "PUBLICATION", "TOC"}:
            return "METADATA_WRAPPER"
        if meta.root_tag in {"CORR", "CORRIGENDUM"} or meta.title.lower().startswith("corrigendum"):
            return "CORRIGENDUM"
        if meta.root_tag == "ANNEX" or (meta.no_seq and "." in meta.no_seq):
            return "ANNEX"

        s = meta.title.strip()
        # High precision check: look at how the title formally begins
        if re.search(r"^(?:Corrigendum|Correction)\b", s, re.I):
            return "CORRIGENDUM"
        if re.search(r"^(?:(?:Commission|Council|European Parliament|Joint)\s+)?(?:Implementing\s+|Delegated\s+)?Decision\b", s, re.I):
            return "DECISION"
        if re.search(r"^(?:(?:Commission|Council|European Parliament|Joint)\s+)?(?:Implementing\s+|Delegated\s+)?Directive\b", s, re.I):
            return "DIRECTIVE"
        if re.search(r"^(?:(?:Commission|Council|European Parliament|Joint)\s+)?(?:Implementing\s+|Delegated\s+)?Regulation\b", s, re.I):
            return "REGULATION"
        if re.search(r"^(?:Protocol|Agreement|Convention)\b", s, re.I) or meta.root_tag == "AGR":
            return "AGREEMENT"
        if re.search(r"^(?:Recommendation|Opinion|Notice|Declaration|Guidelines)\b", s, re.I) or meta.root_tag in {"NOTICE", "GENERAL"}:
            return "QUALIFIER_NOTE"

        # Fallback to general keyword presence if no leading match
        title_lower = s.lower()
        if "regulation" in title_lower and not ("decision" in title_lower or "directive" in title_lower):
            return "REGULATION"
        elif "decision" in title_lower:
            return "DECISION"
        elif "directive" in title_lower:
            return "DIRECTIVE"

        # Check doc_type_tag or default to OTHER
        if meta.doc_type_tag:
            dtt = meta.doc_type_tag.upper()
            if "REG" in dtt:
                return "REGULATION"
            if "DIR" in dtt:
                return "DIRECTIVE"
            if "DEC" in dtt:
                return "DECISION"

        return "OTHER_ACT"

    @classmethod
    def construct_canonical_id(cls, meta: FileMetadata, package_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Constructs canonical readable ID (e.g. 'Regulation (EU) 2018/1139') and CELEX ID."""
        title = meta.title
        cur = meta.doc_num_current
        yr = meta.doc_num_year

        doc_num = None
        if cur and yr:
            raw_num = f"{yr}/{cur}" if (len(yr) == 4 and int(yr) >= 2015) else f"{cur}/{yr}"
            cyear, cnum = parse_eu_doc_number(raw_num)
            doc_num = f"{cyear}/{cnum}" if int(cyear) >= 2015 else f"{cnum}/{cyear}"
        else:
            # Match from title
            match = re.search(r"\((?:EU|EC|EEC)\)\s*(?:No\s*)?(\d+/\d+|\d+/\d+)", title, re.IGNORECASE)
            if match:
                raw_num = match.group(1).strip()
                cyear, cnum = parse_eu_doc_number(raw_num)
                doc_num = f"{cyear}/{cnum}" if int(cyear) >= 2015 else f"{cnum}/{cyear}"
            else:
                match2 = re.search(r"No\s*(\d+/\d+)", title, re.IGNORECASE)
                if match2:
                    raw_num = match2.group(1).strip()
                    cyear, cnum = parse_eu_doc_number(raw_num)
                    doc_num = f"{cyear}/{cnum}" if int(cyear) >= 2015 else f"{cnum}/{cyear}"
                else:
                    cyear, cnum = yr or "0000", cur or "0000"

        celex = None
        if doc_num:
            cyear, cnum = parse_eu_doc_number(doc_num)
            letter = "R"
            if package_type == "REGULATION":
                letter = "R"
            elif package_type == "DIRECTIVE":
                letter = "L"
            elif package_type == "DECISION":
                letter = "D"
            elif package_type == "CORRIGENDUM":
                letter = "R"
            elif package_type == "AGREEMENT":
                letter = "A"

            celex = f"3{cyear}{letter}{cnum.zfill(4)}"

        canonical_name = f"{package_type.capitalize()} {doc_num}" if doc_num else f"{package_type} ({meta.file_name})"
        if package_type == "REGULATION" and doc_num:
            canonical_name = f"Regulation (EU) {doc_num}"
        elif package_type == "DECISION" and doc_num:
            canonical_name = f"Decision (EU) {doc_num}"
        elif package_type == "DIRECTIVE" and doc_num:
            canonical_name = f"Directive (EU) {doc_num}"

        return canonical_name, doc_num, celex

    @classmethod
    def group_folder_files(cls, files_meta: List[FileMetadata]) -> List[DocumentPackage]:
        """Groups all files within a single publication folder (UUID/fmx4) into logical document packages."""
        packages: List[DocumentPackage] = []
        if not files_meta:
            return packages

        metadata_wrappers: List[FileMetadata] = []
        annexes: List[FileMetadata] = []
        corrigenda: List[FileMetadata] = []
        primary_acts: List[FileMetadata] = []
        decisions: List[FileMetadata] = []
        qualifiers: List[FileMetadata] = []

        for m in files_meta:
            act_type = cls.classify_act_type(m)
            if act_type == "METADATA_WRAPPER":
                metadata_wrappers.append(m)
            elif act_type == "ANNEX":
                annexes.append(m)
            elif act_type == "CORRIGENDUM":
                corrigenda.append(m)
            elif act_type in {"REGULATION", "DIRECTIVE"}:
                primary_acts.append(m)
            elif act_type == "DECISION":
                decisions.append(m)
            elif act_type in {"QUALIFIER_NOTE", "AGREEMENT", "OTHER_ACT"}:
                qualifiers.append(m)

        wrapper_paths = [w.file_path for w in metadata_wrappers]

        # Case 1: Core Regulations or Directives exist in folder
        if primary_acts:
            primary_acts.sort(key=lambda x: x.no_seq or "9999")
            main_act = primary_acts[0]
            pkg_type = cls.classify_act_type(main_act)
            canon_name, doc_num, celex = cls.construct_canonical_id(main_act, pkg_type)

            is_aviation = main_act.aviation_matched
            aviation_kws = list(main_act.matched_keywords)
            for a in annexes:
                if a.aviation_matched:
                    is_aviation = True
                    aviation_kws.extend(a.matched_keywords)
            aviation_kws = sorted(list(set(aviation_kws)))

            amended_refs = REG_CITATION_PATTERN.findall(main_act.title)

            pkg = DocumentPackage(
                group_id=main_act.file_name,
                package_type=pkg_type,
                canonical_title=main_act.title or canon_name,
                celex_id=celex,
                doc_number=doc_num,
                adoption_date=main_act.iso_date,
                primary_act_file=main_act.file_path,
                annex_files=[(a.file_path, a.title or "ANNEX") for a in annexes],
                corrigenda_files=[(c.file_path, c.title or "CORRIGENDUM") for c in corrigenda],
                metadata_files=wrapper_paths,
                amended_regulations=amended_refs,
                repealed_regulations=main_act.repeals_raw,
                expiry_date=main_act.expiry_raw,
                is_aviation=is_aviation,
                aviation_keywords=aviation_kws,
            )
            packages.append(pkg)

            # Secondary primary acts
            for secondary in primary_acts[1:]:
                stype = cls.classify_act_type(secondary)
                sname, snum, scelex = cls.construct_canonical_id(secondary, stype)
                packages.append(DocumentPackage(
                    group_id=secondary.file_name,
                    package_type=stype,
                    canonical_title=secondary.title or sname,
                    celex_id=scelex,
                    doc_number=snum,
                    adoption_date=secondary.iso_date,
                    primary_act_file=secondary.file_path,
                    is_aviation=secondary.aviation_matched,
                    aviation_keywords=secondary.matched_keywords,
                ))

            # Attached decisions in same folder
            for d in decisions:
                dname, dnum, dcelex = cls.construct_canonical_id(d, "DECISION")
                sup_match = DECISION_SUPPORT_PATTERN.search(d.title)
                primary_sup = sup_match.group(1).strip() if sup_match else (doc_num or None)
                all_sups_raw = REG_CITATION_PATTERN.findall(d.title)
                clean_sups = []
                for s_num in all_sups_raw:
                    if dnum and (s_num == dnum or ("/" in dnum and s_num == f"{dnum.split('/')[1]}/{dnum.split('/')[0]}")):
                        continue
                    if s_num not in clean_sups:
                        clean_sups.append(s_num)
                if not primary_sup and clean_sups:
                    primary_sup = clean_sups[0]

                packages.append(DocumentPackage(
                    group_id=d.file_name,
                    package_type="DECISION",
                    canonical_title=d.title or dname,
                    celex_id=dcelex,
                    doc_number=dnum,
                    adoption_date=d.iso_date,
                    primary_act_file=d.file_path,
                    primary_supported_reg=primary_sup,
                    supported_regulations=clean_sups,
                    is_aviation=d.aviation_matched or is_aviation,
                    aviation_keywords=d.matched_keywords,
                ))

            # Other qualifiers
            for q in qualifiers:
                qtype = cls.classify_act_type(q)
                qname, qnum, qcelex = cls.construct_canonical_id(q, qtype)
                packages.append(DocumentPackage(
                    group_id=q.file_name,
                    package_type=qtype,
                    canonical_title=q.title or qname,
                    celex_id=qcelex,
                    doc_number=qnum,
                    adoption_date=q.iso_date,
                    primary_act_file=q.file_path,
                    is_aviation=q.aviation_matched or is_aviation,
                    aviation_keywords=q.matched_keywords,
                ))

        # Case 2: Decisions only
        elif decisions:
            decisions.sort(key=lambda x: x.no_seq or "9999")
            main_d = decisions[0]
            dname, dnum, dcelex = cls.construct_canonical_id(main_d, "DECISION")

            is_aviation = main_d.aviation_matched
            aviation_kws = list(main_d.matched_keywords)
            for a in annexes:
                if a.aviation_matched:
                    is_aviation = True
                    aviation_kws.extend(a.matched_keywords)
            aviation_kws = sorted(list(set(aviation_kws)))

            sup_match = DECISION_SUPPORT_PATTERN.search(main_d.title)
            primary_sup = sup_match.group(1).strip() if sup_match else None
            all_sups_raw = REG_CITATION_PATTERN.findall(main_d.title)
            clean_sups = []
            for s_num in all_sups_raw:
                if dnum and (s_num == dnum or ("/" in dnum and s_num == f"{dnum.split('/')[1]}/{dnum.split('/')[0]}")):
                    continue
                if s_num not in clean_sups:
                    clean_sups.append(s_num)
            if not primary_sup and clean_sups:
                primary_sup = clean_sups[0]

            pkg = DocumentPackage(
                group_id=main_d.file_name,
                package_type="DECISION",
                canonical_title=main_d.title or dname,
                celex_id=dcelex,
                doc_number=dnum,
                adoption_date=main_d.iso_date,
                primary_act_file=main_d.file_path,
                annex_files=[(a.file_path, a.title or "ATTACHMENT") for a in annexes],
                corrigenda_files=[(c.file_path, c.title or "CORRIGENDUM") for c in corrigenda],
                metadata_files=wrapper_paths,
                primary_supported_reg=primary_sup,
                supported_regulations=clean_sups,
                repealed_regulations=main_d.repeals_raw,
                expiry_date=main_d.expiry_raw,
                is_aviation=is_aviation,
                aviation_keywords=aviation_kws,
            )
            packages.append(pkg)

            for sec_d in decisions[1:]:
                sname, snum, scelex = cls.construct_canonical_id(sec_d, "DECISION")
                s_sup = DECISION_SUPPORT_PATTERN.search(sec_d.title)
                p_sup = s_sup.group(1).strip() if s_sup else None
                s_sups_raw = REG_CITATION_PATTERN.findall(sec_d.title)
                c_sups = []
                for s_num in s_sups_raw:
                    if snum and (s_num == snum or ("/" in snum and s_num == f"{snum.split('/')[1]}/{snum.split('/')[0]}")):
                        continue
                    if s_num not in c_sups:
                        c_sups.append(s_num)
                if not p_sup and c_sups:
                    p_sup = c_sups[0]

                packages.append(DocumentPackage(
                    group_id=sec_d.file_name,
                    package_type="DECISION",
                    canonical_title=sec_d.title or sname,
                    celex_id=scelex,
                    doc_number=snum,
                    adoption_date=sec_d.iso_date,
                    primary_act_file=sec_d.file_path,
                    primary_supported_reg=p_sup,
                    supported_regulations=c_sups,
                    is_aviation=sec_d.aviation_matched,
                    aviation_keywords=sec_d.matched_keywords,
                ))

        # Case 3: Standalone Corrigendum
        elif corrigenda:
            for c in corrigenda:
                target_reg = c.corr_target_doc
                if not target_reg:
                    matches = REG_CITATION_PATTERN.findall(c.title)
                    if matches:
                        target_reg = matches[0]

                canon_name = f"Corrigendum to {target_reg}" if target_reg else f"Corrigendum ({c.file_name})"
                packages.append(DocumentPackage(
                    group_id=c.file_name,
                    package_type="CORRIGENDUM",
                    canonical_title=c.title or canon_name,
                    primary_act_file=c.file_path,
                    metadata_files=wrapper_paths,
                    primary_supported_reg=target_reg,
                    supported_regulations=[target_reg] if target_reg else [],
                    is_aviation=c.aviation_matched,
                    aviation_keywords=c.matched_keywords,
                ))

        # Case 4: Other agreements or qualifiers
        elif qualifiers:
            main_q = qualifiers[0]
            qtype = cls.classify_act_type(main_q)
            qname, qnum, qcelex = cls.construct_canonical_id(main_q, qtype)
            pkg = DocumentPackage(
                group_id=main_q.file_name,
                package_type=qtype,
                canonical_title=main_q.title or qname,
                celex_id=qcelex,
                doc_number=qnum,
                adoption_date=main_q.iso_date,
                primary_act_file=main_q.file_path,
                annex_files=[(a.file_path, a.title or "ATTACHMENT") for a in annexes],
                metadata_files=wrapper_paths,
                is_aviation=main_q.aviation_matched,
                aviation_keywords=main_q.matched_keywords,
            )
            packages.append(pkg)

        # Case 5: Only orphan annexes
        elif annexes:
            for a in annexes:
                packages.append(DocumentPackage(
                    group_id=a.file_name,
                    package_type="ORPHAN_ANNEX",
                    canonical_title=a.title or f"Orphan Annex ({a.file_name})",
                    primary_act_file=a.file_path,
                    metadata_files=wrapper_paths,
                    is_aviation=a.aviation_matched,
                    aviation_keywords=a.matched_keywords,
                ))

        return packages


# ═══════════════════════════════════════════════════════════════════════════
# Validity & Repeal Cross-Referencing Engine
# ═══════════════════════════════════════════════════════════════════════════

class ValidityEngine:
    """Detects repealed, expired, and time-limited legislation."""

    def __init__(self, current_year: int = 2026):
        self.current_year = current_year
        self.repeal_catalog: Dict[str, Tuple[str, str]] = {}

    def register_repeals(self, package: DocumentPackage) -> None:
        """Records any acts repealed by this package."""
        if not package.repealed_regulations:
            return
        repealer_id = package.celex_id or package.doc_number or package.canonical_title
        for rep in package.repealed_regulations:
            norm_key = self.normalize_number(rep)
            if norm_key:
                self.repeal_catalog[norm_key] = (repealer_id, package.canonical_title)

    @staticmethod
    def normalize_number(num_str: str) -> Optional[str]:
        """Normalizes numbers like '549/2004' or '2018/1139' into canonical 'num/year'."""
        cleaned = re.sub(r"[^\d/]", "", num_str).strip("/")
        parts = cleaned.split("/")
        if len(parts) == 2:
            p1, p2 = parts[0], parts[1]
            cyear, cnum = parse_eu_doc_number(f"{p1}/{p2}")
            return f"{cnum.lstrip('0')}/{cyear}"
        return cleaned or None

    def evaluate_package_validity(self, package: DocumentPackage) -> None:
        """Evaluates whether the package is active, repealed, or expired."""
        if package.doc_number:
            norm = self.normalize_number(package.doc_number)
            if norm and norm in self.repeal_catalog:
                repealer_id, repealer_title = self.repeal_catalog[norm]
                package.validity_status = f"REPEALED (by {repealer_id})"
                package.repealed_by = repealer_id
                return

        if package.expiry_date:
            try:
                exp_year_match = re.search(r"\b(19\d{2}|20\d{2})\b", package.expiry_date)
                if exp_year_match:
                    exp_year = int(exp_year_match.group(1))
                    if exp_year < self.current_year:
                        package.validity_status = f"EXPIRED ({package.expiry_date})"
                        return
                    else:
                        package.validity_status = f"TIME-LIMITED (expires {package.expiry_date})"
                        return
            except Exception:
                pass

        package.validity_status = "IN FORCE"


# ═══════════════════════════════════════════════════════════════════════════
# Sanity Check Runner
# ═══════════════════════════════════════════════════════════════════════════

class FormexSanityChecker:
    """Orchestrates scanning, classification, grouping, and report output."""

    def __init__(
        self,
        input_dir: Path,
        output_file: Path,
        limit_dirs: int = 0,
        limit_aviation: int = 0,
        verbose: bool = True,
    ):
        self.input_dir = Path(input_dir)
        self.output_file = Path(output_file)
        self.limit_dirs = limit_dirs
        self.limit_aviation = limit_aviation
        self.verbose = verbose

        self.inspector = FormexInspector()
        self.classifier = FormexClassifier()
        self.validity_engine = ValidityEngine()

    def run(self) -> None:
        start_time = time.time()
        print("=" * 80)
        print("            EU FORMEX REGULATIONS SANITY CHECK RUNNER")
        print("=" * 80)
        print(f" Source Directory    : {self.input_dir}")
        print(f" Report Destination  : {self.output_file}")
        print(f" Directory Scan Limit: {self.limit_dirs if self.limit_dirs > 0 else 'All'}")
        print(f" Aviation Act Target : {self.limit_aviation if self.limit_aviation > 0 else 'All'}")
        print(f" Parser Engine       : {'lxml (high-speed)' if USE_LXML else 'xml.etree (standard)'}")
        print("=" * 80)

        if not self.input_dir.exists():
            print(f"ERROR: Input directory does not exist: {self.input_dir}")
            sys.exit(1)

        folders: List[Path] = []
        if (self.input_dir / "fmx4").is_dir():
            folders = [self.input_dir / "fmx4"]
        else:
            subdirs = [d for d in self.input_dir.iterdir() if d.is_dir()]
            for d in subdirs:
                fmx = d / "fmx4" if (d / "fmx4").is_dir() else d
                folders.append(fmx)

        total_available_folders = len(folders)
        if self.limit_dirs > 0:
            folders = folders[: self.limit_dirs]

        print(f"Found {total_available_folders} publication folders. Scanning {len(folders)} folders...")

        scanned_folders = 0
        scanned_files = 0
        all_packages: List[DocumentPackage] = []
        aviation_packages: List[DocumentPackage] = []

        # Step 1: Scan and group folders
        for idx, folder in enumerate(folders, 1):
            xml_files = [f for f in folder.glob("*.xml") if f.is_file()]
            if not xml_files:
                continue

            folder_meta: List[FileMetadata] = []
            for xml_file in xml_files:
                meta = self.inspector.inspect_file(xml_file)
                if meta:
                    folder_meta.append(meta)
                    scanned_files += 1

            packages = self.classifier.group_folder_files(folder_meta)
            scanned_folders += 1

            for pkg in packages:
                all_packages.append(pkg)
                self.validity_engine.register_repeals(pkg)
                if pkg.is_aviation:
                    aviation_packages.append(pkg)

            if self.verbose and (idx % 250 == 0 or idx == len(folders)):
                elapsed = time.time() - start_time
                print(
                    f"Progress: [{idx}/{len(folders)}] folders | "
                    f"{scanned_files} XMLs | "
                    f"Aviation Packages: {len(aviation_packages)} | "
                    f"Time: {elapsed:.1f}s"
                )

            if self.limit_aviation > 0 and len(aviation_packages) >= self.limit_aviation:
                print(f"Reached target limit of {self.limit_aviation} aviation packages. Stopping scan.")
                break

        # Step 2: Cross-reference validity across all packages
        for pkg in all_packages:
            self.validity_engine.evaluate_package_validity(pkg)

        # Step 3: Generate report
        self.generate_report(
            all_packages=all_packages,
            aviation_packages=aviation_packages,
            scanned_folders=scanned_folders,
            total_available_folders=total_available_folders,
            scanned_files=scanned_files,
            duration=time.time() - start_time,
        )

        print("\n" + "=" * 80)
        print(f" Sanity Check Complete in {time.time() - start_time:.2f}s")
        print(f" Report successfully generated at: {self.output_file}")
        print("=" * 80)

    def generate_report(
        self,
        all_packages: List[DocumentPackage],
        aviation_packages: List[DocumentPackage],
        scanned_folders: int,
        total_available_folders: int,
        scanned_files: int,
        duration: float,
    ) -> None:
        """Formats and saves the full sanity check report."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        regulations = [p for p in aviation_packages if p.package_type == "REGULATION"]
        directives = [p for p in aviation_packages if p.package_type == "DIRECTIVE"]
        decisions = [p for p in aviation_packages if p.package_type == "DECISION"]
        corrigenda = [p for p in aviation_packages if p.package_type == "CORRIGENDUM"]
        agreements = [p for p in aviation_packages if p.package_type == "AGREEMENT"]
        qualifiers_notes = [p for p in aviation_packages if p.package_type == "QUALIFIER_NOTE"]
        other_packages = [p for p in aviation_packages if p.package_type not in {
            "REGULATION", "DIRECTIVE", "DECISION", "CORRIGENDUM", "AGREEMENT", "QUALIFIER_NOTE"
        }]

        in_force_count = sum(1 for p in aviation_packages if p.validity_status == "IN FORCE")
        repealed_count = sum(1 for p in aviation_packages if "REPEALED" in p.validity_status)
        expired_count = sum(1 for p in aviation_packages if "EXPIRED" in p.validity_status or "TIME-LIMITED" in p.validity_status)

        total_annexes_grouped = sum(len(p.annex_files) for p in aviation_packages)
        total_corrigenda_grouped = sum(len(p.corrigenda_files) for p in aviation_packages)
        total_wrappers_grouped = sum(len(p.metadata_files) for p in aviation_packages)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write("=" * 100 + "\n")
            f.write("                FORMEX REGULATIONS PRE-INGESTION SANITY CHECK REPORT\n")
            f.write("=" * 100 + "\n")
            f.write(f" Generated At             : {now_str}\n")
            f.write(f" Input Directory          : {self.input_dir}\n")
            f.write(f" Total Folders Scanned    : {scanned_folders} (out of {total_available_folders} available)\n")
            f.write(f" Total XML Files Examined : {scanned_files}\n")
            f.write(f" Execution Duration       : {duration:.2f} seconds\n")
            f.write("-" * 100 + "\n")
            f.write(" EXECUTIVE CLASSIFICATION BREAKDOWN (Aviation Relevant):\n")
            f.write(f"   Core Regulations (KB Target)   : {len(regulations):>5}\n")
            f.write(f"   Directives                     : {len(directives):>5}\n")
            f.write(f"   Decisions (Qualifiers DB)      : {len(decisions):>5}\n")
            f.write(f"   Corrigenda (Modifications)     : {len(corrigenda):>5}\n")
            f.write(f"   International Agreements       : {len(agreements):>5}\n")
            f.write(f"   Recommendations & Notes        : {len(qualifiers_notes):>5}\n")
            f.write(f"   Other / Unclassified           : {len(other_packages):>5}\n")
            f.write(f"   TOTAL AVIATION PACKAGES        : {len(aviation_packages):>5}\n")
            f.write("-" * 100 + "\n")
            f.write(" GROUPING & CONSOLIDATION GAINS (What is prevented from becoming orphan regulations):\n")
            f.write(f"   Attached Annexes Safely Grouped  : {total_annexes_grouped:>5} (Consolidated into main regulation)\n")
            f.write(f"   Attached Corrigenda Linked       : {total_corrigenda_grouped:>5} (Recognized as non-independent corrections)\n")
            f.write(f"   Metadata Wrappers (.doc/.toc)    : {total_wrappers_grouped:>5} (Treated as metadata, NOT separate regulations)\n")
            f.write("-" * 100 + "\n")
            f.write(" LIFECYCLE & VALIDITY STATUS (Aviation Relevant):\n")
            f.write(f"   Active / In Force              : {in_force_count:>5}\n")
            f.write(f"   Repealed (Superseded)          : {repealed_count:>5}\n")
            f.write(f"   Expired / Time-Limited         : {expired_count:>5}\n")
            f.write("=" * 100 + "\n\n")

            # ─────────────────────────────────────────────────────────────
            # Section 1: Core Aviation Regulations
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 1: CORE AVIATION REGULATIONS (TARGET FOR KNOWLEDGE BASE)\n")
            f.write(" Each regulation contains its attached Annexes, linked Corrigenda, and metadata wrappers.\n")
            f.write("#" * 100 + "\n\n")

            if not regulations:
                f.write("  No core aviation regulations matched in this scan slice.\n\n")
            else:
                for idx, reg in enumerate(regulations, 1):
                    f.write(f"[{idx}] {reg.celex_id or 'NO-CELEX'} | {reg.doc_number or 'NO-NUMBER'} | Status: {reg.validity_status}\n")
                    f.write(f"    Title          : {reg.canonical_title}\n")
                    f.write(f"    Primary File   : {reg.primary_act_file.name if reg.primary_act_file else 'N/A'}\n")
                    f.write(f"    Keywords       : {', '.join(reg.aviation_keywords[:8])}\n")

                    if reg.annex_files:
                        f.write(f"    Attached Annexes ({len(reg.annex_files)}):\n")
                        for apath, atitle in reg.annex_files:
                            f.write(f"       * {apath.name} -> {atitle[:90]}\n")
                    else:
                        f.write("    Attached Annexes: None\n")

                    if reg.corrigenda_files:
                        f.write(f"    Linked Corrigenda ({len(reg.corrigenda_files)}):\n")
                        for cpath, cdesc in reg.corrigenda_files:
                            f.write(f"       * {cpath.name} -> {cdesc[:90]}\n")

                    if reg.metadata_files:
                        f.write(f"    Metadata Wrappers : {', '.join(m.name for m in reg.metadata_files)}\n")

                    if reg.amended_regulations:
                        f.write(f"    Amends Regs    : {', '.join(reg.amended_regulations[:5])}\n")
                    if reg.repealed_regulations:
                        f.write(f"    Repeals Regs   : {', '.join(reg.repealed_regulations[:5])}\n")

                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 2: Aviation Directives
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 2: AVIATION DIRECTIVES\n")
            f.write("#" * 100 + "\n\n")

            if not directives:
                f.write("  No aviation directives found in this scan slice.\n\n")
            else:
                for idx, dir_pkg in enumerate(directives, 1):
                    f.write(f"[{idx}] {dir_pkg.celex_id or 'NO-CELEX'} | {dir_pkg.doc_number or 'NO-NUMBER'} | Status: {dir_pkg.validity_status}\n")
                    f.write(f"    Title        : {dir_pkg.canonical_title}\n")
                    f.write(f"    Primary File : {dir_pkg.primary_act_file.name if dir_pkg.primary_act_file else 'N/A'}\n")
                    if dir_pkg.annex_files:
                        f.write(f"    Annexes      : {len(dir_pkg.annex_files)} attached\n")
                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 3: Decisions & Supporting Qualifiers
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 3: DECISIONS & SUPPORTING QUALIFIERS (SEPARATE DATABASE)\n")
            f.write(" Not primary regulations, but qualifiers linked back to the regulations they support.\n")
            f.write("#" * 100 + "\n\n")

            if not decisions:
                f.write("  No aviation decisions found in this scan slice.\n\n")
            else:
                for idx, dec in enumerate(decisions, 1):
                    sup_label = f"Regulation {dec.primary_supported_reg}" if dec.primary_supported_reg else (
                        f"Regulation(s) {', '.join(dec.supported_regulations[:3])}" if dec.supported_regulations else "[Autonomous / Direct Implementation]"
                    )
                    f.write(f"[{idx}] {dec.celex_id or 'NO-CELEX'} | Decision {dec.doc_number or dec.group_id} | Status: {dec.validity_status}\n")
                    f.write(f"    Title               : {dec.canonical_title}\n")
                    f.write(f"    Primary File        : {dec.primary_act_file.name if dec.primary_act_file else 'N/A'}\n")
                    f.write(f"    Supports Regulation : {sup_label}\n")
                    if dec.annex_files:
                        f.write(f"    Attached Documents  : {len(dec.annex_files)} ({', '.join(a[0].name for a in dec.annex_files)})\n")
                    if dec.metadata_files:
                        f.write(f"    Metadata Wrappers   : {', '.join(m.name for m in dec.metadata_files)}\n")
                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 4: Corrigenda
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 4: CORRIGENDA (CORRECTIONS MODIFYING EXISTING REGULATIONS)\n")
            f.write("#" * 100 + "\n\n")

            if not corrigenda:
                f.write("  No standalone aviation corrigenda found in this scan slice.\n\n")
            else:
                for idx, corr in enumerate(corrigenda, 1):
                    target_label = corr.primary_supported_reg or "Regulation referenced in text"
                    f.write(f"[{idx}] File: {corr.primary_act_file.name if corr.primary_act_file else 'N/A'}\n")
                    f.write(f"    Description        : {corr.canonical_title}\n")
                    f.write(f"    Modifies Regulation: {target_label}\n")
                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 5: International Agreements & Declarations
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 5: INTERNATIONAL AGREEMENTS & PROTOCOLS\n")
            f.write("#" * 100 + "\n\n")

            if not agreements and not qualifiers_notes:
                f.write("  No agreements or declarations found in this scan slice.\n\n")
            else:
                for idx, ag in enumerate(agreements + qualifiers_notes, 1):
                    f.write(f"[{idx}] {ag.celex_id or 'NO-CELEX'} | {ag.package_type} | {ag.doc_number or ag.group_id}\n")
                    f.write(f"    Title        : {ag.canonical_title}\n")
                    f.write(f"    Primary File : {ag.primary_act_file.name if ag.primary_act_file else 'N/A'}\n")
                    if ag.annex_files:
                        f.write(f"    Attachments  : {len(ag.annex_files)} ({', '.join(a[0].name for a in ag.annex_files)})\n")
                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 6: Lifecycle Flags
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 6: LIFECYCLE FLAGS (NO LONGER IN USE / EXPIRED / REPEALED)\n")
            f.write("#" * 100 + "\n\n")

            inactive_packages = [p for p in aviation_packages if p.validity_status != "IN FORCE"]
            if not inactive_packages:
                f.write("  All aviation packages detected in this scan slice are currently marked IN FORCE.\n\n")
            else:
                for idx, inact in enumerate(inactive_packages, 1):
                    f.write(f"[{idx}] {inact.doc_number or inact.group_id} | Status: {inact.validity_status}\n")
                    f.write(f"    Title  : {inact.canonical_title}\n")
                    f.write(f"    Action : Recommend marking 'is_active = FALSE' in DB or filtering from primary query retrieval.\n")
                    f.write("-" * 100 + "\n")

            # ─────────────────────────────────────────────────────────────
            # Section 7: Actionable Ingestion Recommendations
            # ─────────────────────────────────────────────────────────────
            f.write("\n" + "#" * 100 + "\n")
            f.write(" SECTION 7: INGESTION PIPELINE RECOMMENDATIONS\n")
            f.write("#" * 100 + "\n")
            f.write("""
 1. PACKAGING OVER SINGLE-FILE INGESTION:
    Process Formex XML at the folder/package level rather than file-by-file.
    Always ingest the primary <ACT> together with all its attached <ANNEX> files into
    the same regulation record or table, preserving article and annex hierarchy.

 2. EXCLUDE METADATA WRAPPERS FROM CHUNKING:
    Drop *.doc.xml and *.toc.xml from the chunking / vector database. They are Formex
    cataloging wrappers and contain duplicative chunks that pollute search results.

 3. SEPARATE CORE REGULATIONS FROM QUALIFIERS:
    Decisions (Commission Decision, Council Decision, Implementing Decision) should be
    routed to a dedicated `qualifiers` table with a foreign key `target_regulation_id`,
    rather than being indexed as primary regulations in the knowledge base.

 4. CORRIGENDA ROUTING:
    Corrigenda (<CORR>) should apply patches or be linked as child errata to their
    target regulation rather than generating independent regulation chunks.

 5. REPEAL & EXPIRATION FILTERING:
    Use the detected repeal mapping to flag superseded legislation with `is_active = 0`
    in SQLite so the chatbot/retriever prioritizes current law.
""")
            f.write("=" * 100 + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Formex Regulations Pre-Processing Sanity Check & Grouping Analyzer"
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=str,
        default="ingestion/data/regulation_xml",
        help="Path to folder containing Formex XML subfolders (default: ingestion/data/regulation_xml)",
    )
    parser.add_argument(
        "--output-file",
        "-o",
        type=str,
        default="formex_sanity_check_report.txt",
        help="Path to output text report file (default: formex_sanity_check_report.txt)",
    )
    parser.add_argument(
        "--limit-dirs",
        "-l",
        type=int,
        default=0,
        help="Maximum number of publication folders to scan (0 = scan all folders).",
    )
    parser.add_argument(
        "--limit-aviation",
        "-a",
        type=int,
        default=0,
        help="Stop after finding N aviation-related packages (0 = scan until limit-dirs).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress real-time scan progress output to console.",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    input_path = Path(args.input_dir)
    if not input_path.is_absolute():
        input_path = project_root / input_path

    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    checker = FormexSanityChecker(
        input_dir=input_path,
        output_file=output_path,
        limit_dirs=args.limit_dirs,
        limit_aviation=args.limit_aviation,
        verbose=not args.quiet,
    )
    checker.run()


if __name__ == "__main__":
    main()
