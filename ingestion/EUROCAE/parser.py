"""
Parser and normalizer for EUROCAE and European Aviation Industry Standards.

Parses:
1. List of Published Standards (List_of_published_standards.csv)
2. European ATM Architecture and Deployment Roadmap Upcoming Publications Tracker
   (ARDP_upcomming_publicationsw tracker.csv / xlsx)
"""

import csv
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from .acronyms import (
    expand_acronyms,
    get_acronym_definitions,
    get_working_group_description
)
from .models import EurocaeStandard


def clean_text(text: Optional[str]) -> str:
    """Cleans up text, normalizes unicode, removes non-breaking spaces, and strips whitespace."""
    if not text:
        return ""
    # Normalize unicode (NFKC turns \xa0 into standard space)
    s = unicodedata.normalize("NFKC", str(text))
    # Replace any leftover non-breaking spaces or replacement chars
    s = s.replace("\xa0", " ").replace("\ufeff", "").replace("\ufffd", " ").replace("\u200b", "")
    # Collapse duplicate spaces
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def normalize_status(status_raw: Optional[str]) -> str:
    """Normalizes status strings to canonical title casing."""
    if not status_raw:
        return "Ongoing"
    s = status_raw.strip().lower()
    if "publish" in s:
        return "Published"
    if "ongoing" in s:
        return "Ongoing"
    if "plan" in s:
        return "Planned"
    if "consult" in s:
        return "Under Consultation"
    return status_raw.strip().title()


def extract_easa_reference(comment: str) -> Optional[str]:
    """
    Extracts EASA regulatory references, AMC, or Decision citations from tracker comments.
    E.g.: 'ED-129B is referenced by EASA "DS-GE.CER/DEC - Issue 1" (AMC1 for GE.DEC.ADSB.310...)'
    """
    if not comment:
        return None

    patterns = [
        r'(?:referenced by\s+)?(EASA\s+"[^"]+")',
        r'(EASA\s+CS-[A-Za-z0-9\-]+)',
        r'(AMC\d*\s+for\s+[A-Za-z0-9\.\_\-]+)',
        r'(GM\d*\s+for\s+[A-Za-z0-9\.\_\-]+)',
        r'(EASA\s+ED\s+Decision\s+[0-9\/]+)',
    ]
    found = []
    for pat in patterns:
        matches = re.findall(pat, comment, flags=re.IGNORECASE)
        for m in matches:
            if m and m not in found:
                found.append(m.strip())

    if found:
        return "; ".join(found)
    return None


def parse_published_standards(csv_path: Path) -> List[EurocaeStandard]:
    """
    Parses List_of_published_standards.csv.
    Columns: Reference, Title, Working Group, Domain, Publication Date
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Published standards file not found: {csv_path}")

    standards: List[EurocaeStandard] = []

    # Read with utf-8-sig to automatically strip BOM if present
    rows: List[Dict[str, str]] = []
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except UnicodeDecodeError:
        with open(csv_path, mode="r", encoding="latin-1") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    for r in rows:
        # Extract reference
        ref_raw = r.get("Reference") or r.get("\ufeffReference") or ""
        reference = clean_text(ref_raw)
        if not reference:
            continue

        title = clean_text(r.get("Title", ""))
        wg = clean_text(r.get("Working Group", ""))
        domain = clean_text(r.get("Domain", ""))
        pub_date = clean_text(r.get("Publication Date", ""))

        # Canonical standard ID: e.g. "ED-342"
        # Sanitize spaces in ID if present (e.g. "ED-102B Corrigendum 1" -> "ED-102B_CORR_1")
        clean_id = re.sub(r'[^A-Za-z0-9\-_]', '_', reference.upper())
        clean_id = re.sub(r'_+', '_', clean_id).strip('_')

        # Acronym expansions
        expanded_title = expand_acronyms(title)
        acronyms = get_acronym_definitions(title)
        wg_desc = get_working_group_description(wg)

        org = "EUROCONTROL" if reference.upper().startswith("EUROCONTROL") else "EUROCAE"

        std = EurocaeStandard(
            standard_id=clean_id,
            reference=reference,
            title=title,
            expanded_title=expanded_title,
            status="Published",
            organization=org,
            working_group=wg if wg else None,
            working_group_desc=wg_desc if wg_desc else None,
            domain=domain if domain else None,
            publication_date=pub_date if pub_date else None,
            recognized_acronyms=acronyms
        )
        standards.append(std)

    return standards


def parse_upcoming_tracker(csv_path: Path) -> List[EurocaeStandard]:
    """
    Parses ARDP_upcomming_publicationsw tracker.csv.
    Columns: Domains, SDO Reference Number, Title, Organisation, Working Arrangements, Status,
             Date of publication, Master Plan Reference, CPs AF, SDM Deployment Plan Families,
             Comment, Creation Date, Last Update Date, Unique A-RDP Identifier
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Upcoming tracker file not found: {csv_path}")

    standards: List[EurocaeStandard] = []

    rows: List[Dict[str, str]] = []
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except UnicodeDecodeError:
        with open(csv_path, mode="r", encoding="latin-1") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    for r in rows:
        ref_raw = clean_text(r.get("SDO Reference Number", ""))
        title = clean_text(r.get("Title", ""))
        unique_id = clean_text(r.get("Unique A-RDP Identifier", ""))

        if not title and not ref_raw:
            continue

        reference = ref_raw if ref_raw else "ED-XXX"
        domain = clean_text(r.get("Domains", ""))
        org_raw = clean_text(r.get("Organisation", ""))
        wg = clean_text(r.get("Working Arrangements", ""))
        status = normalize_status(clean_text(r.get("Status", "Ongoing")))
        pub_date = clean_text(r.get("Date of publication", ""))
        master_plan = clean_text(r.get("Master Plan Reference", ""))
        cps_af = clean_text(r.get("CPs AF", ""))
        sdm_fam = clean_text(r.get("SDM Deployment Plan Families", ""))
        comment = clean_text(r.get("Comment", ""))

        # Organization resolution
        if org_raw:
            org = org_raw
        elif reference.upper().startswith("EUROCONTROL"):
            org = "EUROCONTROL"
        else:
            org = "EUROCAE"

        # Unique ID assignment
        if "XXX" in reference.upper() or not ref_raw:
            clean_id = f"{reference}_{unique_id}".replace(" ", "_") if unique_id else f"STD_{abs(hash(title)) % 1000000}"
        else:
            clean_id = re.sub(r'[^A-Za-z0-9\-_]', '_', reference.upper())
            clean_id = re.sub(r'_+', '_', clean_id).strip('_')
            # If multiple upcoming entries share the same reference, append unique_id to disambiguate
            if unique_id:
                clean_id = f"{clean_id}_{unique_id}"

        # Clean title acronyms
        expanded_title = expand_acronyms(title)
        acronyms = get_acronym_definitions(title)
        wg_desc = get_working_group_description(wg)
        easa_ref = extract_easa_reference(comment)

        std = EurocaeStandard(
            standard_id=clean_id,
            reference=reference,
            title=title,
            expanded_title=expanded_title,
            status=status if status else "Ongoing",
            organization=org,
            working_group=wg if wg else None,
            working_group_desc=wg_desc if wg_desc else None,
            domain=domain if domain else None,
            publication_date=pub_date if pub_date else None,
            master_plan_ref=master_plan if master_plan else None,
            cps_af=cps_af if cps_af else None,
            sdm_families=sdm_fam if sdm_fam else None,
            easa_reference=easa_ref,
            comment=comment if comment else None,
            unique_ardp_id=unique_id if unique_id else None,
            recognized_acronyms=acronyms
        )
        standards.append(std)

    return standards


def harmonize_standards(
    published: List[EurocaeStandard], 
    upcoming: List[EurocaeStandard]
) -> List[EurocaeStandard]:
    """
    Harmonizes published standards and upcoming tracker into an integrated,
    deduplicated standards catalog with status, upcoming revisions, and regulatory linkages.
    """
    harmonized: Dict[str, EurocaeStandard] = {}

    # 1. Add published standards first
    for p in published:
        harmonized[p.standard_id] = p

    # 2. Integrate upcoming standards
    for u in upcoming:
        # Check if there is an exact published match (e.g. ED-254A)
        base_ref = re.sub(r'_[A-Za-z0-9\-]+$', '', u.standard_id)
        
        # If published already exists and this upcoming item has the exact same reference
        if u.reference in harmonized or base_ref in harmonized:
            target_key = u.reference if u.reference in harmonized else base_ref
            existing = harmonized[target_key]
            
            # If the upcoming tracker lists it as Published, keep Published
            # but enrich with Master Plan, CPs AF, comments, and EASA reference
            if existing.status == "Published":
                if u.master_plan_ref and not existing.master_plan_ref:
                    existing.master_plan_ref = u.master_plan_ref
                if u.cps_af and not existing.cps_af:
                    existing.cps_af = u.cps_af
                if u.sdm_families and not existing.sdm_families:
                    existing.sdm_families = u.sdm_families
                if u.comment and not existing.comment:
                    existing.comment = u.comment
                if u.easa_reference and not existing.easa_reference:
                    existing.easa_reference = u.easa_reference
                if u.unique_ardp_id and not existing.unique_ardp_id:
                    existing.unique_ardp_id = u.unique_ardp_id
            else:
                # If existing wasn't published, update with upcoming
                harmonized[u.standard_id] = u
        else:
            # New ongoing or planned standard
            harmonized[u.standard_id] = u

    # Sort logically: Published first (by reference), then Ongoing/Planned
    result = list(harmonized.values())
    result.sort(key=lambda s: (0 if s.status.lower() == "published" else 1, s.reference))
    return result
