"""
builder.py - High-Performance Comprehensive EASA Regulatory Knowledge Graph Builder for Kùzu.

Ingests all 42 EASA Easy Access XML rulebooks and builds:
1. Document and Annex hierarchy across all aviation domains
2. Implementing Rules (Hard Law), AMCs/GMs (Soft Law), and CS (Certification Specs)
3. Legal satisfaction and explanation edges (AMC -> IR, GM -> IR/AMC)
4. Intra- and inter-regulatory cross-reference citations
5. Aviation Concept and Stakeholder mapping across the entire European regime
"""

import csv
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import kuzu
from ingestion.core.config import settings
from ingestion.parsers.convert_easa_to_json import parse_easa_xml
from .schema import init_schema


RE_PROVISION_CODE = re.compile(
    r'\b('
    r'CS(?:\s+[A-Z0-9-]+|\-[A-Z0-9-]+)?\s+\d+\.\d+[A-Z0-9]*|'
    r'AMC\s+\d+\.\d+[A-Z0-9]*|'
    r'SERA\.\d+[A-Z0-9]*|'
    r'[A-Z0-9]{1,6}(?:\.[A-Z0-9]{1,6})*\.\d+[A-Z0-9]*|'
    r'Article\s+\d+'
    r')\b',
    re.IGNORECASE
)

RE_SUBPARAGRAPH = re.compile(r'\([a-zA-Z0-9]+\)')

CONCEPT_TAXONOMY = {
    "Fuel Planning & Energy Schemes": {
        "category": "Flight Operations",
        "keywords": [r"fuel scheme", r"fuel policy", r"contingency fuel", r"final reserve fuel", r"point of safe return", r"isolated aerodrome fuel"]
    },
    "Safety Management System (SMS)": {
        "category": "Governance & Compliance",
        "keywords": [r"safety management system", r"safety policy", r"hazard identification", r"risk assessment", r"safety manager", r"compliance monitoring", r"safety risk management"]
    },
    "Extended Diversion Time Operations (EDTO/ETOPS)": {
        "category": "Operational Authorizations",
        "keywords": [r"extended diversion time", r"edto", r"etops", r"en-route alternate", r"threshold distance", r"adequate aerodrome"]
    },
    "Flight Time Limitations & Fatigue (FTL)": {
        "category": "Crew & Human Factors",
        "keywords": [r"flight time limitation", r"flight duty period", r"rest period", r"fatigue management", r"disruptive schedule", r"acclimatisation"]
    },
    "Low Visibility Operations (LVO/AWO)": {
        "category": "Flight Operations",
        "keywords": [r"low visibility", r"category ii", r"category iii", r"all-weather operations", r"enhanced flight vision", r"efvs", r"hud"]
    },
    "Dangerous Goods Transport (DG)": {
        "category": "Cargo & Security",
        "keywords": [r"dangerous goods", r"hazardous materials", r"cargo compartment fire", r"dg training", r"technical instructions"]
    },
    "Minimum Equipment List (MEL/MMEL)": {
        "category": "Continuing Airworthiness & Dispatch",
        "keywords": [r"minimum equipment list", r"master minimum equipment list", r"mel dispatch", r"inoperative equipment", r"rectification interval"]
    },
    "Performance-Based Navigation (PBN)": {
        "category": "Air Navigation & Avionics",
        "keywords": [r"performance-based navigation", r"pbn specification", r"rnp approach", r"rnaov", r"gnss landing", r"baro-vnav"]
    },
    "Electronic Flight Bag (EFB)": {
        "category": "Digital Operations",
        "keywords": [r"electronic flight bag", r"efb application", r"efb hosting", r"portable efb", r"installed efb"]
    },
    "Crew Resource Management (CRM)": {
        "category": "Crew & Human Factors",
        "keywords": [r"crew resource management", r"crm training", r"threat and error management", r"situational awareness", r"workload management"]
    },
    "Continuing Airworthiness & Maintenance (CAMO)": {
        "category": "Airworthiness",
        "keywords": [r"continuing airworthiness", r"airworthiness directive", r"maintenance programme", r"amp", r"camo", r"maintenance release", r"crs"]
    },
    "Aerodrome Emergency Planning & RFFS": {
        "category": "Aerodromes & Infrastructure",
        "keywords": [r"rescue and firefighting", r"rffs", r"aerodrome emergency plan", r"disabled aircraft removal", r"wildlife hazard"]
    },
    "Unmanned Aircraft Systems & U-Space (UAS)": {
        "category": "Unmanned Aviation",
        "keywords": [r"unmanned aircraft", r"drone", r"u-space", r"geographical zone", r"remote pilot", r"specific category", r"certified category"]
    },
    "Cybersecurity & Information Security": {
        "category": "Security & Resilience",
        "keywords": [r"information security", r"cybersecurity", r"cyber threat", r"part-is", r"critical information system"]
    }
}

STAKEHOLDER_ROLES = {
    "Commercial Air Transport Operator": {
        "role_type": "Operator",
        "keywords": [r"the operator shall", r"air transport operator", r"commercial operator"]
    },
    "Pilot-in-Command (PIC)": {
        "role_type": "Flight Crew",
        "keywords": [r"pilot-in-command shall", r"the commander shall", r"pilot-in-command is responsible"]
    },
    "Continuing Airworthiness Management Organisation (CAMO)": {
        "role_type": "Maintenance & CAMO",
        "keywords": [r"the camo shall", r"continuing airworthiness management organisation", r"part-camo"]
    },
    "Approved Maintenance Organisation (Part-145)": {
        "role_type": "Maintenance & CAMO",
        "keywords": [r"part-145 organisation", r"approved maintenance organisation", r"certifying staff"]
    },
    "Competent Authority / Civil Aviation Authority (CAA)": {
        "role_type": "Regulator",
        "keywords": [r"competent authority shall", r"authority shall verify", r"agency shall", r"oversight"]
    },
    "Aerodrome Operator": {
        "role_type": "Aerodrome",
        "keywords": [r"aerodrome operator shall", r"airport operator", r"runway safety team"]
    },
    "Air Traffic Services / ANSP": {
        "role_type": "ATM / ANS",
        "keywords": [r"air traffic service", r"ansp shall", r"air traffic controller", r"atco"]
    },
    "Flight Crew Member": {
        "role_type": "Flight Crew",
        "keywords": [r"flight crew member shall", r"co-pilot", r"flight engineer"]
    },
    "Cabin Crew Member": {
        "role_type": "Cabin Crew",
        "keywords": [r"cabin crew member shall", r"senior cabin crew", r"cabin crew training"]
    }
}

ANNEX_DESCRIPTIONS = {
    "Annex I": "Annex I: Common Definitions and Core Requirements",
    "Annex II": "Annex II: Authority Requirements (Part-ARO / Part-ARA)",
    "Annex III": "Annex III: Organisation Requirements (Part-ORO / Part-ORA)",
    "Annex IV": "Annex IV: Commercial Air Transport (Part-CAT)",
    "Annex V": "Annex V: Specific Approvals (Part-SPA: PBN, MNPS, RVSM, LVO, ETOPS, DG, NVIS, HHO, HEMS)",
    "Annex VI": "Annex VI: Non-Commercial Complex Motor-Powered Aircraft (Part-NCC)",
    "Annex VII": "Annex VII: Non-Commercial Other than Complex (Part-NCO)",
    "Annex VIII": "Annex VIII: Specialised Operations (Part-SPO: Aerial Work)",
    "Part-CAT": "Annex IV: Commercial Air Transport Operations",
    "Part-SPA": "Annex V: Specific Approvals",
    "Part-ORO": "Annex III: Organisation Requirements for Air Operations",
    "Part-NCC": "Annex VI: Non-Commercial Complex Motor-Powered Aircraft",
    "Part-NCO": "Annex VII: Non-Commercial Other than Complex",
    "Part-SPO": "Annex VIII: Specialised Operations (Aerial Work)",
    "Part-ARO": "Annex II: Authority Requirements for Air Operations",
    "Part-IAM": "Annex X: Initial Airworthiness Management",
    "Part-DEFINITIONS": "Annex I: Common Definitions for Air Operations",
    "Part-FCL": "Annex I: Flight Crew Licensing",
    "Part-MED": "Annex IV: Medical Requirements for Aircrew",
    "Part-CC": "Annex V: Cabin Crew Requirements",
    "Part-ARA": "Annex VI: Authority Requirements for Aircrew",
    "Part-ORA": "Annex VII: Organisation Requirements for Aircrew",
    "Part-DTO": "Annex VIII: Declared Training Organisations",
    "Part-M": "Annex I: Continuing Airworthiness Requirements",
    "Part-145": "Annex II: Maintenance Organisation Approvals",
    "Part-66": "Annex III: Certifying Staff Maintenance Licences",
    "Part-147": "Annex IV: Maintenance Training Organisations",
    "Part-T": "Annex Va: Continuing Airworthiness for Third Country Aircraft",
    "Part-ML": "Annex Vb: Light Aircraft Continuing Airworthiness",
    "Part-CAMO": "Annex Vc: Continuing Airworthiness Management Organisations",
    "Part-CAO": "Annex Vd: Combined Airworthiness Organisations",
    "Part-ADR.OR": "Annex III: Aerodrome Organisation Requirements",
    "Part-ADR.OPS": "Annex IV: Aerodrome Operations Requirements",
    "Part-ADR.AR": "Annex II: Authority Requirements for Aerodromes",
    "Book 1": "Book 1: Certification Specifications (Airworthiness Code)",
    "Book 2": "Book 2: Acceptable Means of Compliance (AMC)",
    "SERA": "Standardised European Rules of the Air",
    "Basic Regulation": "Regulation (EU) 2018/1139 Foundational Mandate"
}


def sanitize_text(text: str) -> str:
    """Cleans text for CSV export."""
    if not text:
        return ""
    return text.replace('\x00', '').strip()


def extract_base_code(code: str, title: str) -> str:
    """Extracts the canonical base code for an IR rule (e.g. 'CAT.OP.MPA.180', 'CS 25.1309')."""
    m = RE_PROVISION_CODE.search(code) or RE_PROVISION_CODE.search(title)
    if m:
        raw = m.group(1)
        base = RE_SUBPARAGRAPH.sub('', raw).strip()
        base = re.sub(r'^(?:AMC\d*|GM\d*)\s+', '', base).strip()
        return base
    return code.split()[0] if code else "GENERAL"


def build_all_easa_graphs(
    xml_dir: Path = None,
    db_path: Path = None,
    staging_dir: Path = None,
    limit_files: int = None
) -> Dict[str, Any]:
    """
    Ingests all EASA Easy Access XML rulebooks from xml_dir into a single unified Kùzu graph.
    """
    start_time = time.time()
    xml_dir = Path(xml_dir or settings.DATA_DIR / "easaxml")
    db_path = Path(db_path or settings.KUZU_DB_PATH)
    if not xml_dir.exists():
        raise FileNotFoundError(f"XML directory not found: {xml_dir}")

    xml_files = sorted([f for f in xml_dir.glob("*.xml") if f.is_file()], key=lambda x: x.stat().st_size, reverse=True)
    if limit_files:
        xml_files = xml_files[:limit_files]

    total_files = len(xml_files)
    print(f"==================================================")
    print(f" Comprehensive EASA Regulatory Knowledge Graph Builder")
    print(f" Discovered {total_files} official EASA XML rulebooks")
    print(f" Destination Database: {db_path}")
    print(f"==================================================")

    staging_dir = Path(staging_dir or settings.GRAPH_DIR / "staging_csv")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    documents_rows: List[List[Any]] = []
    annex_nodes: Dict[str, Dict[str, Any]] = {}
    provision_nodes: Dict[str, Dict[str, Any]] = {}
    concept_nodes: Dict[str, Dict[str, Any]] = {}
    stakeholder_nodes: Dict[str, Dict[str, Any]] = {}

    rel_contains_annex: List[Tuple[str, str]] = []
    rel_belongs_to_annex: List[Tuple[str, str]] = []
    rel_satisfies: List[Tuple[str, str]] = []
    rel_explains: List[Tuple[str, str]] = []
    rel_cross_references: Set[Tuple[str, str]] = set()
    rel_governs_concept: List[Tuple[str, str, str]] = []
    rel_applies_to: List[Tuple[str, str, str]] = []

    compiled_concepts = {
        name: {
            "category": info["category"],
            "patterns": [re.compile(p, re.IGNORECASE) for p in info["keywords"]]
        }
        for name, info in CONCEPT_TAXONOMY.items()
    }

    compiled_stakeholders = {
        name: {
            "role_type": info["role_type"],
            "patterns": [re.compile(p, re.IGNORECASE) for p in info["keywords"]]
        }
        for name, info in STAKEHOLDER_ROLES.items()
    }

    for name, info in CONCEPT_TAXONOMY.items():
        c_id = f"CONCEPT_{name.replace(' ', '_').replace('/', '_')}"
        concept_nodes[c_id] = {"id": c_id, "name": name, "category": info["category"]}

    for name, info in STAKEHOLDER_ROLES.items():
        s_id = f"STAKEHOLDER_{name.replace(' ', '_').replace('/', '_')}"
        stakeholder_nodes[s_id] = {"id": s_id, "name": name, "role_type": info["role_type"]}

    print("\n[Phase 1/4] Parsing all EASA XML files into in-memory ontology...")
    file_count = 0
    total_parsed_topics = 0

    for xf in xml_files:
        file_count += 1
        doc_id = f"DOC_{xf.stem.upper().replace(' ', '_').replace('-', '_')}"
        doc_title = f"Easy Access Rules: {xf.stem.replace('_', ' ').title()}"

        try:
            parsed_data = parse_easa_xml(str(xf))
        except Exception as e:
            print(f"  [!] Error parsing {xf.name}: {e}. Skipping.")
            continue

        raw_topics = parsed_data.get("topics", [])
        total_parsed_topics += len(raw_topics)
        documents_rows.append([doc_id, doc_title, "EASA Easy Access Rules", len(raw_topics)])
        print(f"  [{file_count:02d}/{total_files:02d}] {xf.name[:45]:<45} -> {len(raw_topics):5d} topics")

        doc_prefix = doc_id.replace("DOC_", "")

        for t in raw_topics:
            code = sanitize_text(t.get("code") or "")
            title = sanitize_text(t.get("title") or "")
            c_type = sanitize_text(t.get("content_type") or "IR").upper()
            text = sanitize_text(t.get("text") or "")
            subject = sanitize_text(t.get("subject") or "General")

            if not code and not title:
                continue

            base_code = extract_base_code(code, title)
            prov_code = code if code else base_code
            raw_id = f"{doc_prefix}_{prov_code}_{c_type}".replace(' ', '_')
            prov_id = f"P_{raw_id}"

            if prov_id in provision_nodes:
                prov_id = f"{prov_id}_{len(provision_nodes)}"

            annex_name = subject
            for k, v in ANNEX_DESCRIPTIONS.items():
                if k.lower() in subject.lower() or k.lower() in code.lower():
                    annex_name = v
                    break

            annex_id = f"ANNEX_{doc_prefix}_{subject.replace(' ', '_').replace('/', '_')}"
            if annex_id not in annex_nodes:
                annex_nodes[annex_id] = {
                    "id": annex_id,
                    "code": subject,
                    "name": annex_name
                }
                rel_contains_annex.append((doc_id, annex_id))

            rel_belongs_to_annex.append((prov_id, annex_id))

            legal_force = "Implementing Rule"
            if c_type == "AMC":
                legal_force = "Acceptable Means of Compliance (Soft Law)"
            elif c_type == "GM":
                legal_force = "Guidance Material (Explanatory)"
            elif c_type == "CS":
                legal_force = "Certification Specification"

            word_count = len(text.split())

            provision_nodes[prov_id] = {
                "id": prov_id,
                "code": prov_code,
                "base_code": base_code,
                "title": title,
                "content_type": c_type,
                "legal_force": legal_force,
                "subject": subject,
                "text": text,
                "word_count": word_count,
                "doc_id": doc_id
            }

            full_content = f"{prov_code} {title} {text}"
            for c_name, c_info in compiled_concepts.items():
                for pat in c_info["patterns"]:
                    if pat.search(full_content):
                        c_id = f"CONCEPT_{c_name.replace(' ', '_').replace('/', '_')}"
                        rel_governs_concept.append((prov_id, c_id, "Direct Governing Mandate"))
                        break

            for s_name, s_info in compiled_stakeholders.items():
                for pat in s_info["patterns"]:
                    if pat.search(full_content):
                        s_id = f"STAKEHOLDER_{s_name.replace(' ', '_').replace('/', '_')}"
                        rel_applies_to.append((prov_id, s_id, "Operational Obligation"))
                        break

    print(f"\n[Phase 2/4] Linking intra- and inter-regulatory legal satisfaction and citations...")

    base_code_to_ir: Dict[str, str] = {}
    for pid, p in provision_nodes.items():
        if p["content_type"] in ("IR", "CS"):
            b = p["base_code"]
            if b not in base_code_to_ir:
                base_code_to_ir[b] = pid

    amc_satisfies_count = 0
    gm_explains_count = 0

    for pid, p in provision_nodes.items():
        c_type = p["content_type"]
        base = p["base_code"]

        if c_type == "AMC" and base in base_code_to_ir:
            ir_id = base_code_to_ir[base]
            rel_satisfies.append((pid, ir_id))
            amc_satisfies_count += 1
        elif c_type == "GM" and base in base_code_to_ir:
            ir_id = base_code_to_ir[base]
            rel_explains.append((pid, ir_id))
            gm_explains_count += 1

        matches = RE_PROVISION_CODE.findall(p["text"])
        for cited_raw in matches:
            cited_base = RE_SUBPARAGRAPH.sub('', cited_raw).strip()
            cited_base = re.sub(r'^(?:AMC\d*|GM\d*)\s+', '', cited_base).strip()
            if cited_base and cited_base in base_code_to_ir:
                target_pid = base_code_to_ir[cited_base]
                if target_pid != pid:
                    rel_cross_references.add((pid, target_pid))

    print(f"  -> Connected {amc_satisfies_count} AMC -> IR (SATISFIES) edges")
    print(f"  -> Connected {gm_explains_count} GM -> IR (EXPLAINS) edges")
    print(f"  -> Discovered {len(rel_cross_references)} CROSS_REFERENCES citation edges")

    print(f"\n[Phase 3/4] Exporting staging CSVs to {staging_dir}...")

    doc_csv = staging_dir / "nodes_document.csv"
    with open(doc_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "source", "total_topics"])
        w.writerows(documents_rows)

    annex_csv = staging_dir / "nodes_annex.csv"
    with open(annex_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "code", "name"])
        for a in annex_nodes.values():
            w.writerow([a["id"], a["code"], a["name"]])

    prov_csv = staging_dir / "nodes_provision.csv"
    with open(prov_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "code", "base_code", "title", "content_type", "legal_force", "subject", "text", "word_count"])
        for p in provision_nodes.values():
            w.writerow([p["id"], p["code"], p["base_code"], p["title"], p["content_type"], p["legal_force"], p["subject"], p["text"], p["word_count"]])

    concept_csv = staging_dir / "nodes_concept.csv"
    with open(concept_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "category"])
        for c in concept_nodes.values():
            w.writerow([c["id"], c["name"], c["category"]])

    stakeholder_csv = staging_dir / "nodes_stakeholder.csv"
    with open(stakeholder_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "role_type"])
        for s in stakeholder_nodes.values():
            w.writerow([s["id"], s["name"], s["role_type"]])

    def write_rel_csv(path: Path, rows: Any, header: List[str]):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write_rel_csv(staging_dir / "rel_contains_annex.csv", rel_contains_annex, ["from", "to"])
    write_rel_csv(staging_dir / "rel_belongs_to_annex.csv", rel_belongs_to_annex, ["from", "to"])
    write_rel_csv(staging_dir / "rel_satisfies.csv", rel_satisfies, ["from", "to"])
    write_rel_csv(staging_dir / "rel_explains.csv", rel_explains, ["from", "to"])
    write_rel_csv(staging_dir / "rel_cross_references.csv", rel_cross_references, ["from", "to"])
    write_rel_csv(staging_dir / "rel_governs_concept.csv", rel_governs_concept, ["from", "to", "relevance"])
    write_rel_csv(staging_dir / "rel_applies_to.csv", rel_applies_to, ["from", "to", "obligation"])

    print(f"\n[Phase 4/4] Bulk copying CSVs into Kùzu database at {db_path}...")
    if db_path.exists():
        if db_path.is_file():
            db_path.unlink()
        else:
            shutil.rmtree(db_path)

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    init_schema(conn)

    print("  -> Loading Node tables...")
    conn.execute(f"COPY RegulationDocument FROM '{doc_csv.as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY Annex FROM '{annex_csv.as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY Provision FROM '{prov_csv.as_posix()}' (HEADER=TRUE, PARALLEL=FALSE);")
    conn.execute(f"COPY Concept FROM '{concept_csv.as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY Stakeholder FROM '{stakeholder_csv.as_posix()}' (HEADER=TRUE);")

    print("  -> Loading Relationship tables...")
    conn.execute(f"COPY CONTAINS_ANNEX FROM '{(staging_dir / 'rel_contains_annex.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY BELONGS_TO_ANNEX FROM '{(staging_dir / 'rel_belongs_to_annex.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY SATISFIES FROM '{(staging_dir / 'rel_satisfies.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY EXPLAINS FROM '{(staging_dir / 'rel_explains.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY CROSS_REFERENCES FROM '{(staging_dir / 'rel_cross_references.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY GOVERNS_CONCEPT FROM '{(staging_dir / 'rel_governs_concept.csv').as_posix()}' (HEADER=TRUE);")
    conn.execute(f"COPY APPLIES_TO FROM '{(staging_dir / 'rel_applies_to.csv').as_posix()}' (HEADER=TRUE);")
    del conn
    del db

    # Bulk-ingest secondary sources (FAA, EU, EUROCAE, SKYBRARY) into Kuzu
    try:
        from .ingest_secondary_sources import ingest_secondary_sources
        ingest_secondary_sources(db_path)
    except Exception as e:
        print(f"[WARN] Failed to ingest secondary sources: {e}")

    total_elapsed = round(time.time() - start_time, 2)
    print(f"\n==================================================")
    print(f" [+] Full Multi-Source Aviation Knowledge Graph Successfully Built!")
    print(f" [+] Total Elapsed Time: {total_elapsed}s")
    print(f" [+] Database Stored At: {db_path}")
    print(f"==================================================")

    return {
        "status": "success",
        "elapsed_seconds": total_elapsed,
        "nodes": {
            "documents": len(documents_rows),
            "annexes": len(annex_nodes),
            "provisions": len(provision_nodes),
            "concepts": len(concept_nodes),
            "stakeholders": len(stakeholder_nodes)
        },
        "edges": {
            "contains_annex": len(rel_contains_annex),
            "belongs_to_annex": len(rel_belongs_to_annex),
            "satisfies": len(rel_satisfies),
            "explains": len(rel_explains),
            "cross_references": len(rel_cross_references),
            "governs_concept": len(rel_governs_concept),
            "applies_to": len(rel_applies_to)
        }
    }
