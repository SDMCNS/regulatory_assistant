"""
Skybrary Recency and Provenance Weighting Module.

Implements domain-specific weighting rules for Skybrary documents:
1. No publication year: downweighted by 75% (multiplier 0.25).
2. With publication year: downweighted by 5% per year difference to current year, up to 60% max downweight.
3. Accident investigations or reports: exempt from downweighting (multiplier 1.0).
"""

import re
import datetime
from typing import Dict, Any, Optional, Tuple


def is_skybrary_accident_or_report(meta: Dict[str, Any], title: str = "", doc_id: str = "") -> bool:
    """
    Identifies whether a Skybrary document represents an accident investigation,
    incident investigation, or official safety occurrence report.
    These are preserved at full weight (0% downweight).
    """
    category = str(meta.get("category") or "").strip().lower()
    t = str(title or meta.get("title") or "").strip().lower()
    
    # 1. Official Skybrary categories
    if "accident" in category or "investigation" in category:
        return True
    if "report" in category and ("incident" in category or "safety" in category):
        return True
        
    # 2. Multilingual keywords for accident & incident investigations and final reports
    report_keywords = [
        "accident report", "incident report", "investigation report", 
        "final report", "preliminary report", "safety investigation",
        "accident investigation", "incident investigation", "serious incident",
        "aircraft accident", "air accident",
        # Multilingual titles common in international safety investigations
        "rapport d'enquête", "rapport final", "incident grave",
        "informe final", "informe preliminar", "accidente",
        "abschlussbericht", "untersuchungsbericht", "unfallbericht"
    ]
    if any(kw in t for kw in report_keywords):
        return True
        
    return False


def extract_skybrary_publication_year(meta: Dict[str, Any], title: str = "") -> Optional[int]:
    """
    Extracts the publication year from Skybrary metadata or document title.
    """
    # 1. Date field (e.g. '10.Sep.2013', '2020-04-16', '12 May 2022')
    date_val = str(meta.get("date") or "").strip()
    if date_val:
        m = re.search(r'\b(19\d\d|20\d\d)\b', date_val)
        if m:
            return int(m.group(1))

    # 2. Check year field if present
    if meta.get("year"):
        try:
            return int(meta.get("year"))
        except (ValueError, TypeError):
            pass

    # 3. Check publication_year / pub_date / publication_date
    for k in ["publication_year", "publication_date", "pub_year"]:
        if meta.get(k):
            m = re.search(r'\b(19\d\d|20\d\d)\b', str(meta.get(k)))
            if m:
                return int(m.group(1))

    # 4. Check nested metadata dictionary if present
    nested = meta.get("metadata")
    if isinstance(nested, dict):
        for k in ["year", "date", "publication_year"]:
            if nested.get(k):
                m = re.search(r'\b(19\d\d|20\d\d)\b', str(nested.get(k)))
                if m:
                    return int(m.group(1))

    # 5. Fallback: check 4-digit year in title if present
    if title:
        m = re.search(r'\b(19\d\d|20\d\d)\b', str(title))
        if m:
            return int(m.group(1))

    return None


def calculate_skybrary_weight(
    meta: Dict[str, Any], 
    title: str = "", 
    doc_id: str = "",
    current_year: Optional[int] = None
) -> Tuple[float, str]:
    """
    Calculates the score multiplier (0.0 to 1.0) for Skybrary records according to:
      1. Accident investigations or reports: 0% downweight (multiplier 1.0).
      2. No publication year: 75% downweight (multiplier 0.25).
      3. With publication year: 5% downweight per year difference to current year, up to 60% downweight.
      
    Returns:
      (multiplier: float, explanation: str)
    """
    if current_year is None:
        current_year = datetime.datetime.now().year

    # Check if accident investigation or report
    if is_skybrary_accident_or_report(meta, title, doc_id):
        return (1.0, "Accident Investigation/Report (Exempt from downweighting)")

    pub_year = extract_skybrary_publication_year(meta, title)
    if pub_year is None:
        # Downweight by 75% (multiplier = 0.25)
        return (0.25, "Undated Skybrary Record (-75% downweight)")

    # With associated date / publication year:
    # 5% for each year difference up to 60%
    year_diff = max(0, current_year - pub_year)
    downweight_fraction = min(0.60, year_diff * 0.05)
    multiplier = round(1.0 - downweight_fraction, 4)
    pct_str = int(round(downweight_fraction * 100))
    
    return (multiplier, f"Skybrary {pub_year} ({year_diff}y diff: -{pct_str}% downweight)")
