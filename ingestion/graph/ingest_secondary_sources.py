"""
ingest_secondary_sources.py - Ingests non-EASA sources into the Kùzu Knowledge Graph.

Federated Sources:
1. FAA: Code of Federal Regulations Title 14 (Aeronautics & Space Parts 1-199)
2. EU: European Union Official Journal Regulations (EUR-Lex foundational acts)
3. EUROCAE: European Organisation for Civil Aviation Equipment Standards
4. SKYBRARY: Aviation Safety Bookshelf & Accident Investigation Studies
"""

import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import kuzu
from ingestion.core.config import settings

PROJECT_ROOT = settings.BASE_DIR.parent
FAA_DIR = settings.DATA_DIR / "FAA"
EU_DIR = settings.DATA_DIR / "regulations"
EUROCAE_CSV = settings.BASE_DIR / "EUROCAE" / "List_of_published_standards.csv"
SKYBRARY_DB = settings.BASE_DIR / "skybrary_bookshelf" / "skybrary.db"
STAGING_DIR = settings.GRAPH_CACHE_DIR / "staging_secondary"

# The 17 Core Aviation Concepts present in Kùzu DB
CONCEPT_TAXONOMY = {
    "CONCEPT_FUEL_PLANNING___ENERGY_SCHEMES": {
        "name": "Fuel Planning & Energy Schemes",
        "category": "Flight Operations",
        "keywords": [
            r"fuel scheme", r"fuel policy", r"contingency fuel", r"final reserve fuel",
            r"point of safe return", r"isolated aerodrome fuel", r"usable fuel",
            r"fuel reserve", r"minimum fuel", r"fuel planning", r"fuel consumption"
        ]
    },
    "CONCEPT_SAFETY_MANAGEMENT_SYSTEM__SMS": {
        "name": "Safety Management System (SMS)",
        "category": "Governance & Compliance",
        "keywords": [
            r"safety management system", r"safety policy", r"hazard identification",
            r"risk assessment", r"safety manager", r"compliance monitoring",
            r"safety risk management", r"safety assurance", r"safety performance"
        ]
    },
    "CONCEPT_EXTENDED_DIVERSION_TIME_OPERATIONS__EDTO_ETOPS": {
        "name": "Extended Diversion Time Operations (EDTO/ETOPS)",
        "category": "Operational Authorizations",
        "keywords": [
            r"extended diversion time", r"edto", r"etops", r"en-route alternate",
            r"threshold distance", r"adequate aerodrome", r"extended range operations",
            r"diversion time"
        ]
    },
    "CONCEPT_FLIGHT_TIME_LIMITATIONS___FATIGUE__FTL": {
        "name": "Flight Time Limitations & Fatigue (FTL)",
        "category": "Crew Licensing & Rest",
        "keywords": [
            r"flight time limitation", r"flight duty period", r"rest period",
            r"fatigue management", r"disruptive schedule", r"acclimatisation",
            r"crew fatigue", r"maximum flight duty", r"flight time limit", r"circadian"
        ]
    },
    "CONCEPT_ALL_WEATHER___LOW_VISIBILITY_OPERATIONS__LVO_AWO": {
        "name": "All-Weather & Low Visibility Operations (LVO/AWO)",
        "category": "All-Weather Operations",
        "keywords": [
            r"low visibility", r"category ii\b", r"category iii\b", r"all-weather operations",
            r"enhanced flight vision", r"efvs", r"hud", r"runway visual range",
            r"autoland", r"decision height", r"cat ii\b", r"cat iii\b"
        ]
    },
    "CONCEPT_STERILE_FLIGHT_DECK_PROCEDURE": {
        "name": "Sterile Flight Deck Procedure",
        "category": "Cockpit Procedures",
        "keywords": [
            r"sterile flight deck", r"sterile cockpit", r"critical phase of flight",
            r"non-essential activities", r"flight deck discipline"
        ]
    },
    "CONCEPT_DANGEROUS_GOODS__DG": {
        "name": "Dangerous Goods (DG)",
        "category": "Cargo & Special Loads",
        "keywords": [
            r"dangerous goods", r"hazardous materials", r"cargo compartment fire",
            r"dg training", r"technical instructions for the safe transport", r"hazmat",
            r"radioactive material", r"lithium battery transport"
        ]
    },
    "CONCEPT_ALTIMETER_SETTING___RVSM": {
        "name": "Altimeter Setting & RVSM",
        "category": "Navigation & Separation",
        "keywords": [
            r"altimeter setting", r"rvsm", r"reduced vertical separation",
            r"transition altitude", r"transition level", r"standard altimeter",
            r"flight level", r"qnh", r"altitude reporting"
        ]
    },
    "CONCEPT_RAMP_INSPECTIONS__SAFA_SACA": {
        "name": "Ramp Inspections (SAFA/SACA)",
        "category": "Safety Oversight",
        "keywords": [
            r"ramp inspection", r"safa", r"saca", r"foreign aircraft",
            r"ramp check", r"safety assessment of foreign aircraft", r"surveillance inspection"
        ]
    },
    "CONCEPT_MASS_AND_BALANCE__W_B": {
        "name": "Mass and Balance (W&B)",
        "category": "Aircraft Performance",
        "keywords": [
            r"mass and balance", r"weight and balance", r"center of gravity",
            r"centre of gravity", r"loading schedule", r"maximum takeoff mass",
            r"mtow", r"payload", r"takeoff weight"
        ]
    },
    "CONCEPT_CONTINUING_AIRWORTHINESS___MAINTENANCE": {
        "name": "Continuing Airworthiness & Maintenance",
        "category": "Airworthiness",
        "keywords": [
            r"continuing airworthiness", r"airworthiness directive", r"maintenance programme",
            r"maintenance program", r"camo", r"maintenance release", r"crs",
            r"part-145", r"repair station", r"airworthiness limitation",
            r"type certificate", r"airworthiness standards", r"maintenance record",
            r"mandatory continuing airworthiness", r"preventive maintenance"
        ]
    },
    "CONCEPT_AERODROME_DESIGN___RUNWAY_SAFETY": {
        "name": "Aerodrome Design & Runway Safety",
        "category": "Aerodromes & Ground",
        "keywords": [
            r"rescue and firefighting", r"rffs", r"aerodrome emergency plan",
            r"disabled aircraft removal", r"wildlife hazard", r"runway incursion",
            r"runway excursion", r"aerodrome certificate", r"taxiway",
            r"runway surface", r"runway safety area", r"pavement classification"
        ]
    },
    "CONCEPT_PILOT___CREW_LICENSING__PART_FCL___MED": {
        "name": "Pilot & Crew Licensing (Part-FCL / MED)",
        "category": "Personnel Licensing",
        "keywords": [
            r"pilot license", r"pilot licence", r"flight crew licensing",
            r"commercial pilot", r"airline transport pilot", r"type rating",
            r"medical certificate", r"class 1 medical", r"flight instructor",
            r"pilot school", r"part-fcl", r"airman certification", r"crew qualification"
        ]
    },
    "CONCEPT_AIR_TRAFFIC_MANAGEMENT___AIRSPACE__ATM_ANS_SERA": {
        "name": "Air Traffic Management & Airspace (ATM/ANS/SERA)",
        "category": "Air Traffic & Airspace",
        "keywords": [
            r"air traffic management", r"air traffic control", r"atc",
            r"airspace classification", r"separation minimum", r"rules of the air",
            r"flight plan", r"controlled airspace", r"ads-b", r"transponder",
            r"tcas", r"collision avoidance", r"air traffic controller"
        ]
    },
    "CONCEPT_UNMANNED_AIRCRAFT_SYSTEMS___U_SPACE": {
        "name": "Unmanned Aircraft Systems & U-space",
        "category": "UAS & Drones",
        "keywords": [
            r"unmanned aircraft", r"drone", r"u-space", r"geographical zone",
            r"remote pilot", r"specific category", r"certified category",
            r"open category", r"uas", r"uav", r"part 107", r"small unmanned"
        ]
    },
    "CONCEPT_INFORMATION_SECURITY___CYBERSECURITY__PART_IS": {
        "name": "Information Security & Cybersecurity (Part-IS)",
        "category": "Cybersecurity & Security",
        "keywords": [
            r"information security", r"cybersecurity", r"cyber threat",
            r"part-is", r"critical information system", r"ed-202", r"ed-203",
            r"network security", r"software integrity", r"security risk"
        ]
    },
    "CONCEPT_OCCURRENCE_REPORTING___JUST_CULTURE": {
        "name": "Occurrence Reporting & Just Culture",
        "category": "Safety Intelligence",
        "keywords": [
            r"occurrence reporting", r"just culture", r"mandatory occurrence",
            r"voluntary occurrence", r"incident reporting", r"safety report",
            r"accident investigation", r"aviation accident", r"aviation incident",
            r"incident report", r"accident report"
        ]
    }
}

COMPILED_CONCEPTS = {
    cid: {
        "name": info["name"],
        "patterns": [re.compile(kw, re.IGNORECASE) for kw in info["keywords"]]
    }
    for cid, info in CONCEPT_TAXONOMY.items()
}


def match_concepts(text: str, title: str = "") -> List[str]:
    """Matches text against the 17 core concepts."""
    content = f"{title} {text}".lower()
    matched = []
    for cid, cinfo in COMPILED_CONCEPTS.items():
        hit = False
        for p in cinfo["patterns"]:
            if p.search(content):
                hit = True
                break
        if hit:
            matched.append(cid)
    return matched


def parse_faa_source() -> Tuple[List[Dict], List[Dict], List[Dict], List[Tuple], List[Tuple], List[Tuple]]:
    """
    Parses FAA Title 14 CFR XML files.
    Groups sections into FAR Part RegulationDocuments, Subparts into Annexes,
    and sections into Provisions.
    """
    print("\n[FAA] Parsing Title 14 CFR XML files...")
    if not FAA_DIR.exists():
        print("[WARN] FAA dir does not exist.")
        return [], [], [], [], [], []

    # 1. Extract official Part titles from XMLs
    part_titles = {}
    for xml_file in sorted(FAA_DIR.glob("*.xml")):
        try:
            for event, elem in ET.iterparse(xml_file, events=("end",)):
                if elem.tag == "PART":
                    hd = elem.findtext("HD") or ""
                    m = re.search(r'PART\s+(\d+)\s*[\u2014\u2013\-\—]\s*(.*)', hd, re.IGNORECASE)
                    if m:
                        part_num = m.group(1)
                        part_titles[f"Part {part_num}"] = m.group(2).strip()
                    elem.clear()
        except Exception as e:
            print(f"[WARN] Error scanning part titles in {xml_file.name}: {e}")

    # 2. Extract sections and organize by Part
    parts_map: Dict[str, Dict[str, Any]] = {}
    sections_by_id: Dict[str, Dict[str, Any]] = {}

    for xml_file in sorted(FAA_DIR.glob("*.xml")):
        try:
            for event, elem in ET.iterparse(xml_file, events=("end",)):
                if elem.tag == "SECTION":
                    s_no = (elem.findtext("SECTNO") or "").strip()
                    s_sub = (elem.findtext("SUBJECT") or "").strip()
                    if s_no and s_sub:
                        s_no = re.sub(r'[\u2009\u00a0\xa0]', ' ', s_no).strip()
                        s_no_clean = re.sub(r'^[§\s]+', '', s_no).strip()

                        part_m = re.match(r'^(\d+)\.', s_no_clean)
                        part_no = part_m.group(1) if part_m else "FAR"
                        part_key = f"Part {part_no}"

                        p_texts = [p.text for p in elem.findall(".//P") if p.text]
                        text_snippet = " ".join(p_texts[:8]).strip()
                        if not text_snippet:
                            text_snippet = f"FAA Federal Aviation Regulation 14 CFR § {s_no_clean}: {s_sub}"

                        sec_id = f"FAA_14CFR_{s_no_clean}"

                        # Determine subpart code/title
                        subpart_code = "General"
                        subpart_name = f"14 CFR Part {part_no} Provisions"

                        # Check if section number has letters or ranges for grouping
                        if sec_id not in sections_by_id:
                            sec_obj = {
                                "id": sec_id,
                                "code": f"14 CFR § {s_no_clean}",
                                "base_code": f"§ {s_no_clean}",
                                "title": s_sub,
                                "content_type": "RULE",
                                "legal_force": "HARD_LAW",
                                "subject": f"FAA Title 14 CFR {part_key}",
                                "text": text_snippet,
                                "word_count": len(text_snippet.split()),
                                "part_key": part_key,
                                "part_no": part_no,
                                "subpart_code": subpart_code,
                                "subpart_name": subpart_name
                            }
                            sections_by_id[sec_id] = sec_obj

                            if part_key not in parts_map:
                                p_title = part_titles.get(part_key, f"Title 14 CFR {part_key}")
                                parts_map[part_key] = {
                                    "id": f"DOC_FAA_PART_{part_no}",
                                    "title": f"14 CFR Part {part_no}: {p_title.title()}",
                                    "part_no": part_no,
                                    "sections": []
                                }
                            parts_map[part_key]["sections"].append(sec_obj)
                        else:
                            # Append extra text if snippet was short
                            if len(sections_by_id[sec_id]["text"]) < 300 and len(text_snippet) > len(sections_by_id[sec_id]["text"]):
                                sections_by_id[sec_id]["text"] = text_snippet

                    elem.clear()
        except Exception as e:
            print(f"[WARN] Error parsing {xml_file.name}: {e}")

    # Build node lists and relationship tuples
    doc_nodes = []
    annex_nodes = []
    annex_seen = set()
    prov_nodes = list(sections_by_id.values())
    rel_contains_annex = []
    rel_belongs_to_annex = []
    rel_governs_concept = []

    for part_key, pdata in parts_map.items():
        doc_id = pdata["id"]
        total_topics = len(pdata["sections"])
        doc_nodes.append({
            "id": doc_id,
            "title": pdata["title"],
            "source": "FAA",
            "total_topics": total_topics
        })

        annex_id = f"ANNEX_FAA_PART_{pdata['part_no']}_MAIN"
        if annex_id not in annex_seen:
            annex_seen.add(annex_id)
            annex_nodes.append({
                "id": annex_id,
                "code": f"Part {pdata['part_no']}",
                "name": pdata["title"]
            })
            rel_contains_annex.append((doc_id, annex_id))

        for sec in pdata["sections"]:
            rel_belongs_to_annex.append((sec["id"], annex_id))

            # Match concepts
            concepts = match_concepts(sec["text"], sec["title"])
            for cid in concepts:
                rel_governs_concept.append((sec["id"], cid, "DIRECT"))

    print(f"  -> Extracted {len(doc_nodes)} FAA Part Documents, {len(annex_nodes)} Annexes, {len(prov_nodes)} Provisions, {len(rel_governs_concept)} Concept Links.")
    return doc_nodes, annex_nodes, prov_nodes, rel_contains_annex, rel_belongs_to_annex, rel_governs_concept


def parse_eu_source() -> Tuple[List[Dict], List[Dict], List[Dict], List[Tuple], List[Tuple], List[Tuple]]:
    """
    Parses EU EUR-Lex regulations from ingestion/data/regulations/*.json.
    Each regulation becomes a RegulationDocument with source='EU'.
    Articles become Provisions.
    """
    print("\n[EU] Parsing EUR-Lex Regulation JSON files...")
    if not EU_DIR.exists():
        print("[WARN] EU dir does not exist.")
        return [], [], [], [], [], []

    doc_nodes = []
    annex_nodes = []
    prov_nodes = []
    rel_contains_annex = []
    rel_belongs_to_annex = []
    rel_governs_concept = []

    json_files = [f for f in sorted(EU_DIR.glob("*.json")) if not f.name.endswith(".chunks.json")]

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                d = json.load(f)

            if isinstance(d, list):
                continue  # skip note / test files

            meta = d.get("metadata", {})
            full_title = meta.get("title") or d.get("title") or jf.stem
            doc_id = f"DOC_EU_{jf.stem}"
            celex = meta.get("celex", "")

            # Extract clean regulation reference
            reg_ref_m = re.search(r'(Regulation\s*\((?:EU|EC|EEC)\)[^\,\;\(\)]+)', full_title, re.IGNORECASE)
            reg_ref = reg_ref_m.group(1).strip() if reg_ref_m else (celex or jf.stem)

            # Clean readable title
            clean_title = full_title
            if len(clean_title) > 200:
                clean_title = clean_title[:197] + "..."

            body = d.get("body", [])
            articles = []
            if isinstance(body, list):
                for item in body:
                    if isinstance(item, dict) and item.get("type") == "article":
                        articles.append(item)

            annex_id = f"ANNEX_EU_{jf.stem}_ARTICLES"
            annex_nodes.append({
                "id": annex_id,
                "code": "Articles",
                "name": f"Articles of {reg_ref}"
            })
            rel_contains_annex.append((doc_id, annex_id))

            if articles:
                for art in articles:
                    art_num = art.get("number") or f"Article {art.get('identifier', '')}"
                    art_subtitle = art.get("subtitle") or art_num

                    # Extract paragraphs text
                    p_texts = []
                    content = art.get("content", [])
                    if isinstance(content, list):
                        for p in content:
                            if isinstance(p, dict):
                                if p.get("text"):
                                    p_texts.append(p.get("text"))
                                sub_content = p.get("content", [])
                                if isinstance(sub_content, list):
                                    for sub_p in sub_content:
                                        if isinstance(sub_p, dict) and sub_p.get("text"):
                                            p_texts.append(sub_p.get("text"))
                    elif isinstance(art.get("text"), str):
                        p_texts.append(art.get("text"))

                    art_text = " ".join(p_texts).strip() or f"Provisions of {art_num}: {art_subtitle}"
                    art_id = f"EU_{jf.stem}_{re.sub(r'[^A-Za-z0-9]', '_', art_num)}"

                    p_obj = {
                        "id": art_id,
                        "code": f"{reg_ref[:22]}: {art_num}",
                        "base_code": art_num,
                        "title": art_subtitle[:140],
                        "content_type": "REGULATION_ARTICLE",
                        "legal_force": "HARD_LAW",
                        "subject": f"EUR-Lex {reg_ref}",
                        "text": art_text,
                        "word_count": len(art_text.split())
                    }
                    prov_nodes.append(p_obj)
                    rel_belongs_to_annex.append((art_id, annex_id))

                    concepts = match_concepts(art_text, art_subtitle)
                    for cid in concepts:
                        rel_governs_concept.append((art_id, cid, "DIRECT"))
            else:
                # Default provision for regulations without discrete article objects
                art_id = f"EU_{jf.stem}_ENACTMENT"
                art_text = full_title
                p_obj = {
                    "id": art_id,
                    "code": f"{reg_ref[:22]} General",
                    "base_code": "General",
                    "title": clean_title[:140],
                    "content_type": "REGULATION_ACT",
                    "legal_force": "HARD_LAW",
                    "subject": f"EUR-Lex {reg_ref}",
                    "text": art_text,
                    "word_count": len(art_text.split())
                }
                prov_nodes.append(p_obj)
                rel_belongs_to_annex.append((art_id, annex_id))

                concepts = match_concepts(art_text, clean_title)
                for cid in concepts:
                    rel_governs_concept.append((art_id, cid, "SUPPORTING"))

            doc_nodes.append({
                "id": doc_id,
                "title": clean_title,
                "source": "EU",
                "total_topics": len(articles) or 1
            })

        except Exception as e:
            pass

    print(f"  -> Extracted {len(doc_nodes)} EU Regulation Documents, {len(annex_nodes)} Annexes, {len(prov_nodes)} Provisions, {len(rel_governs_concept)} Concept Links.")
    return doc_nodes, annex_nodes, prov_nodes, rel_contains_annex, rel_belongs_to_annex, rel_governs_concept


def parse_eurocae_source() -> Tuple[List[Dict], List[Dict], List[Dict], List[Tuple], List[Tuple], List[Tuple]]:
    """
    Parses EUROCAE published standards CSV.
    Organizes by Domain as RegulationDocuments, Working Groups as Annexes,
    and Standards as Provisions.
    """
    print("\n[EUROCAE] Parsing published standards CSV...")
    if not EUROCAE_CSV.exists():
        print("[WARN] EUROCAE CSV does not exist.")
        return [], [], [], [], [], []

    domains: Dict[str, Dict[str, Any]] = {}

    try:
        with open(EUROCAE_CSV, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ref = (r.get("Reference") or r.get("\ufeffReference") or "").strip()
                title = (r.get("Title") or "").strip()
                domain = (r.get("Domain") or "General").strip() or "General"
                wg = (r.get("Working Group") or "WG-General").strip() or "WG-General"
                pub_date = (r.get("Publication Date") or "").strip()

                if not ref or not title:
                    continue

                if domain not in domains:
                    domains[domain] = {
                        "id": f"DOC_EUROCAE_{re.sub(r'[^A-Za-z0-9]', '_', domain).upper()}",
                        "title": f"EUROCAE Technical Standards: {domain}",
                        "working_groups": {}
                    }

                if wg not in domains[domain]["working_groups"]:
                    domains[domain]["working_groups"][wg] = []

                domains[domain]["working_groups"][wg].append({
                    "ref": ref,
                    "title": title,
                    "domain": domain,
                    "wg": wg,
                    "pub_date": pub_date
                })
    except Exception as e:
        print(f"[WARN] Error reading EUROCAE CSV: {e}")

    doc_nodes = []
    annex_nodes = []
    prov_nodes = []
    rel_contains_annex = []
    rel_belongs_to_annex = []
    rel_governs_concept = []

    for dom_name, ddata in domains.items():
        doc_id = ddata["id"]
        total_stds = sum(len(stds) for stds in ddata["working_groups"].values())
        doc_nodes.append({
            "id": doc_id,
            "title": ddata["title"],
            "source": "EUROCAE",
            "total_topics": total_stds
        })

        for wg_name, stds in ddata["working_groups"].items():
            annex_id = f"ANNEX_EUROCAE_{re.sub(r'[^A-Za-z0-9]', '_', dom_name).upper()}_{re.sub(r'[^A-Za-z0-9]', '_', wg_name).upper()}"
            annex_nodes.append({
                "id": annex_id,
                "code": wg_name,
                "name": f"EUROCAE {wg_name} ({dom_name})"
            })
            rel_contains_annex.append((doc_id, annex_id))

            for s in stds:
                ref = s["ref"]
                title = s["title"]
                prov_id = f"EUROCAE_{re.sub(r'[^A-Za-z0-9]', '_', ref)}"
                text = f"EUROCAE Industry Specification {ref}: {title}. Domain: {s['domain']}, Working Group: {s['wg']}, Published: {s['pub_date']}."

                prov_nodes.append({
                    "id": prov_id,
                    "code": ref,
                    "base_code": ref,
                    "title": title,
                    "content_type": "INDUSTRY_STANDARD",
                    "legal_force": "SOFT_LAW",
                    "subject": f"EUROCAE {dom_name} ({s['wg']})",
                    "text": text,
                    "word_count": len(text.split())
                })
                rel_belongs_to_annex.append((prov_id, annex_id))

                concepts = match_concepts(text, title)
                for cid in concepts:
                    rel_governs_concept.append((prov_id, cid, "DIRECT"))

    print(f"  -> Extracted {len(doc_nodes)} EUROCAE Domain Documents, {len(annex_nodes)} Annexes, {len(prov_nodes)} Provisions, {len(rel_governs_concept)} Concept Links.")
    return doc_nodes, annex_nodes, prov_nodes, rel_contains_annex, rel_belongs_to_annex, rel_governs_concept


def parse_skybrary_source() -> Tuple[List[Dict], List[Dict], List[Dict], List[Tuple], List[Tuple], List[Tuple]]:
    """
    Parses SKYBRARY SQLite safety publications.
    Organizes top categories as RegulationDocuments, sub-categories as Annexes,
    and publications as Provisions.
    """
    print("\n[SKYBRARY] Parsing SQLite safety bookshelf...")
    if not SKYBRARY_DB.exists():
        print("[WARN] SKYBRARY database does not exist.")
        return [], [], [], [], [], []

    doc_nodes = []
    annex_nodes = []
    prov_nodes = []
    rel_contains_annex = []
    rel_belongs_to_annex = []
    rel_governs_concept = []

    try:
        conn = sqlite3.connect(str(SKYBRARY_DB))
        c = conn.cursor()

        # Group publications by category
        rows = c.execute("""
            SELECT id, title, category, author, publication_date, summary_url
            FROM publications
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category, id ASC;
        """).fetchall()

        conn.close()

        cat_groups: Dict[str, List[Any]] = {}
        for r in rows:
            cat = r[2].strip()
            if cat not in cat_groups:
                cat_groups[cat] = []
            cat_groups[cat].append(r)

        for cat_name, pubs in cat_groups.items():
            cat_slug = re.sub(r'[^A-Za-z0-9]', '_', cat_name).upper()
            doc_id = f"DOC_SKYBRARY_{cat_slug}"

            doc_nodes.append({
                "id": doc_id,
                "title": f"SKYbrary Aviation Safety: {cat_name}",
                "source": "SKYBRARY",
                "total_topics": len(pubs)
            })

            annex_id = f"ANNEX_SKYBRARY_{cat_slug}_COLLECTION"
            annex_nodes.append({
                "id": annex_id,
                "code": "Safety Library",
                "name": f"SKYbrary {cat_name} Publications"
            })
            rel_contains_annex.append((doc_id, annex_id))

            for p in pubs:
                p_id, p_title, p_cat, p_auth, p_date, p_url = p
                prov_id = f"SKYBRARY_{p_id}"
                snippet = f"SKYbrary Safety Publication: {p_title}. Category: {p_cat}. Author: {p_auth or 'SKYbrary'}. Date: {p_date or 'N/A'}. Reference: {p_url or ''}."

                prov_nodes.append({
                    "id": prov_id,
                    "code": f"SKYBRARY #{p_id}",
                    "base_code": f"#{p_id}",
                    "title": p_title[:140],
                    "content_type": "SAFETY_STUDY",
                    "legal_force": "INFORMATIONAL",
                    "subject": f"SKYbrary {p_cat}",
                    "text": snippet,
                    "word_count": len(snippet.split())
                })
                rel_belongs_to_annex.append((prov_id, annex_id))

                concepts = match_concepts(snippet, p_title)
                for cid in concepts:
                    rel_governs_concept.append((prov_id, cid, "SUPPORTING"))

    except Exception as e:
        print(f"[WARN] Error parsing SKYBRARY SQLite: {e}")

    print(f"  -> Extracted {len(doc_nodes)} SKYbrary Category Documents, {len(annex_nodes)} Annexes, {len(prov_nodes)} Provisions, {len(rel_governs_concept)} Concept Links.")
    return doc_nodes, annex_nodes, prov_nodes, rel_contains_annex, rel_belongs_to_annex, rel_governs_concept


def write_csv(path: Path, rows: List[List[Any]], header: List[str]):
    """Writes rows to CSV file with UTF-8 encoding."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def ingest_secondary_sources(db_path: Path = None):
    """
    Parses FAA, EU, EUROCAE, and SKYBRARY and bulk-ingests them into Kùzu.
    """
    start_time = time.time()
    db_path = db_path or settings.KUZU_DB_PATH
    print(f"==================================================")
    print(f"Starting Multi-Source Regulatory Ingestion for Kùzu")
    print(f"Database Target: {db_path}")
    print(f"==================================================")

    # 1. Parse all 4 secondary sources
    faa_doc, faa_annex, faa_prov, faa_ca, faa_ba, faa_gc = parse_faa_source()
    eu_doc, eu_annex, eu_prov, eu_ca, eu_ba, eu_gc = parse_eu_source()
    ec_doc, ec_annex, ec_prov, ec_ca, ec_ba, ec_gc = parse_eurocae_source()
    sb_doc, sb_annex, sb_prov, sb_ca, sb_ba, sb_gc = parse_skybrary_source()

    # Aggregate & Deduplicate
    all_docs = {}
    for d in faa_doc + eu_doc + ec_doc + sb_doc:
        all_docs[d["id"]] = d

    all_annexes = {}
    for a in faa_annex + eu_annex + ec_annex + sb_annex:
        all_annexes[a["id"]] = a

    all_provisions = {}
    for p in faa_prov + eu_prov + ec_prov + sb_prov:
        all_provisions[p["id"]] = p

    all_contains_annex = list(set(faa_ca + eu_ca + ec_ca + sb_ca))
    all_belongs_to_annex = list(set(faa_ba + eu_ba + ec_ba + sb_ba))
    all_governs_concept = list(set(faa_gc + eu_gc + ec_gc + sb_gc))

    print(f"\n[Summary] Total Secondary Nodes & Edges to Ingest:")
    print(f"  - Regulation Documents: {len(all_docs)}")
    print(f"  - Annexes:              {len(all_annexes)}")
    print(f"  - Provisions:           {len(all_provisions)}")
    print(f"  - CONTAINS_ANNEX:       {len(all_contains_annex)}")
    print(f"  - BELONGS_TO_ANNEX:     {len(all_belongs_to_annex)}")
    print(f"  - GOVERNS_CONCEPT:      {len(all_governs_concept)}")

    # 2. Write CSVs in staging folder
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    doc_csv = STAGING_DIR / "nodes_doc.csv"
    write_csv(
        doc_csv,
        [[d["id"], d["title"], d["source"], d["total_topics"]] for d in all_docs.values()],
        ["id", "title", "source", "total_topics"]
    )

    annex_csv = STAGING_DIR / "nodes_annex.csv"
    write_csv(
        annex_csv,
        [[a["id"], a["code"], a["name"]] for a in all_annexes.values()],
        ["id", "code", "name"]
    )

    prov_csv = STAGING_DIR / "nodes_provision.csv"
    write_csv(
        prov_csv,
        [[p["id"], p["code"], p["base_code"], p["title"], p["content_type"], p["legal_force"], p["subject"], p["text"], p["word_count"]] for p in all_provisions.values()],
        ["id", "code", "base_code", "title", "content_type", "legal_force", "subject", "text", "word_count"]
    )

    ca_csv = STAGING_DIR / "rel_contains_annex.csv"
    write_csv(ca_csv, all_contains_annex, ["from", "to"])

    ba_csv = STAGING_DIR / "rel_belongs_to_annex.csv"
    write_csv(ba_csv, all_belongs_to_annex, ["from", "to"])

    gc_csv = STAGING_DIR / "rel_governs_concept.csv"
    write_csv(gc_csv, all_governs_concept, ["from", "to", "relevance"])

    # 3. Connect to Kùzu and Bulk COPY
    print(f"\n[Kùzu] Bulk Loading secondary sources into {db_path}...")
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)

    print("  -> Loading RegulationDocument nodes...")
    conn.execute(f"COPY RegulationDocument FROM '{doc_csv.as_posix()}' (HEADER=TRUE);")

    print("  -> Loading Annex nodes...")
    conn.execute(f"COPY Annex FROM '{annex_csv.as_posix()}' (HEADER=TRUE);")

    print("  -> Loading Provision nodes...")
    conn.execute(f"COPY Provision FROM '{prov_csv.as_posix()}' (HEADER=TRUE, PARALLEL=FALSE);")

    print("  -> Loading CONTAINS_ANNEX relationships...")
    conn.execute(f"COPY CONTAINS_ANNEX FROM '{ca_csv.as_posix()}' (HEADER=TRUE);")

    print("  -> Loading BELONGS_TO_ANNEX relationships...")
    conn.execute(f"COPY BELONGS_TO_ANNEX FROM '{ba_csv.as_posix()}' (HEADER=TRUE);")

    print("  -> Loading GOVERNS_CONCEPT relationships...")
    conn.execute(f"COPY GOVERNS_CONCEPT FROM '{gc_csv.as_posix()}' (HEADER=TRUE);")

    # Verify counts in DB
    res_docs = conn.execute("MATCH (d:RegulationDocument) RETURN d.source, count(*);")
    print("\n[DB Verification] Total Documents by Source:")
    total_docs = 0
    while res_docs.has_next():
        src, cnt = res_docs.get_next()
        total_docs += cnt
        print(f"  • {src or 'UNKNOWN'}: {cnt} documents")
    print(f"  Total Regulation Documents in Kùzu: {total_docs}")

    res_provs = conn.execute("MATCH (p:Provision) RETURN count(*);")
    print(f"  Total Provisions in Kùzu: {res_provs.get_next()[0]}")

    res_gc = conn.execute("MATCH ()-[e:GOVERNS_CONCEPT]->() RETURN count(*);")
    print(f"  Total GOVERNS_CONCEPT edges in Kùzu: {res_gc.get_next()[0]}")

    del conn
    del db

    elapsed = round(time.time() - start_time, 2)
    print(f"\nMulti-source ingestion successfully completed in {elapsed}s!")


if __name__ == "__main__":
    ingest_secondary_sources()
