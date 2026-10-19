"""
scratch/seed_aviation_concepts.py
Pre-indexes domain-reasoned Aviation Concepts into custom_concepts.json
using Kùzu graph engine to discover governing provisions across all EASA regulations.
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "c:/Projects/Regs"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ingestion.graph.traversal import get_engine
from ingestion.graph.custom_concepts import get_custom_concept_manager

CONCEPTS_TO_SEED = [
    {
        "name": "Minimum Equipment List (MEL/MMEL)",
        "category": "Continuing Airworthiness & Dispatch",
        "description": "Master minimum equipment list, inoperative instruments and equipment, rectification intervals, operational dispatch relief, and configuration deviation list (CDL)."
    },
    {
        "name": "Performance-Based Navigation (PBN & RNP)",
        "category": "Navigation & Avionics",
        "description": "Area navigation (RNAV), Required Navigation Performance (RNP), GNSS approach, SBAS/GBAS, baro-VNAV, and navigation specification approvals."
    },
    {
        "name": "Electronic Flight Bag (EFB)",
        "category": "Digital Cockpit Operations",
        "description": "Electronic flight bag hardware classifications, Type A and Type B software applications, digital charting, operational evaluation, and lithium battery risk management."
    },
    {
        "name": "Crew Resource Management (CRM & TEM)",
        "category": "Human Factors & Flight Crew",
        "description": "Crew resource management training, Threat and Error Management (TEM), situational awareness, communication, decision making, and startle effect mitigation."
    },
    {
        "name": "Rescue and Firefighting Services (RFFS)",
        "category": "Aerodromes & Infrastructure",
        "description": "Aerodrome fire protection categories, emergency response times, rescue and firefighting vehicles, extinguishing agents, and disabled aircraft removal."
    },
    {
        "name": "Airworthiness Directives & Mandatory Modifications (AD/SB)",
        "category": "Airworthiness & Safety Oversight",
        "description": "Airworthiness directives, mandatory continuing airworthiness information, service bulletins, emergency AD compliance tracking, and alternative means of compliance (AMOC)."
    },
    {
        "name": "System Safety Assessment & Fail-Safe Design (CS-25.1309)",
        "category": "Type Certification & Engineering",
        "description": "Functional hazard assessment (FHA), preliminary system safety assessment (PSSA), system safety assessment (SSA), single failure criterion, and catastrophic failure probability."
    },
    {
        "name": "Flight Data Monitoring (FDM/FOQA)",
        "category": "Safety Intelligence & Analytics",
        "description": "Operational flight data analysis, FDR recording parameters, non-punitive exceedance monitoring, de-identification protocols, and safety performance indicator integration."
    },
    {
        "name": "Aviation Security & Unlawful Interference (AVSEC)",
        "category": "Security & Resilience",
        "description": "Flight crew compartment door security, unauthorized access prevention, unruly passengers, security searches, bomb threats, and air cargo supply chain security."
    },
    {
        "name": "Helicopter Emergency Medical Services (HEMS & HHO)",
        "category": "Specialised Flight Operations",
        "description": "Part-SPA helicopter emergency medical operations, hoist operations (HHO), elevated hospital helidecks, visual meteorology limits, and specialized medical crew duties."
    },
    {
        "name": "Environmental Protection: Aircraft Noise & Emissions",
        "category": "Environmental Compliance",
        "description": "ICAO Annex 16 noise certification standards, engine emissions limits, carbon offsetting (CORSIA), noise abatement departure procedures (NADP), and curfews."
    },
    {
        "name": "De-icing, Anti-icing & Winter Operations",
        "category": "Ground and Winter Operations",
        "description": "Ground de-icing, anti-icing procedures, holdover times (HOT), clean aircraft concept, frost protection, and contaminated runway performance."
    },
    {
        "name": "Oceanic & High-Level Airspace Operations (NAT-HLA / RVSM)",
        "category": "Airspace & Long-Haul Navigation",
        "description": "North Atlantic High Level Airspace, Reduced Vertical Separation Minimum (RVSM), height keeping performance, oceanic clearances, and contingency drift-down."
    },
    {
        "name": "U-Space Services & Drone Traffic Management",
        "category": "Unmanned Aviation & Advanced Air Mobility",
        "description": "U-space airspace, common information service (CIS), network identification, geo-awareness, flight authorization services, and eVTOL urban vertiports."
    },
    {
        "name": "Certificate of Release to Service (CRS & Part-145)",
        "category": "Approved Maintenance & Line Operations",
        "description": "Certificate of release to service, certifying staff privileges, maintenance records, EASA Form 1 release, and maintenance handover procedures."
    },
    {
        "name": "Fatigue Risk Management System (FRMS)",
        "category": "Crew Licensing & Rest",
        "description": "Fatigue risk management principles, bio-mathematical fatigue modeling, sleep opportunity monitoring, disruptive schedules, and fatigue safety action groups."
    },
    {
        "name": "Runway Surface Condition & Incursion Prevention",
        "category": "Aerodromes & Runway Safety",
        "description": "Global reporting format (GRF), runway condition code (RWYCC), surface friction assessment, runway incursion prevention, and visual aids and markings."
    },
    {
        "name": "Aging Aircraft Structures & Corrosion Prevention (CPCP)",
        "category": "Continuing Airworthiness",
        "description": "Damage tolerance inspections, fatigue cracking, supplemental structural inspection programmes (SSIP), corrosion prevention and control programmes, and electrical wiring."
    },
    {
        "name": "Evidence-Based Training & Competency Assessment (EBT/CBTA)",
        "category": "Personnel Licensing & Training",
        "description": "Evidence-based training (EBT), competency-based training and assessment (CBTA), operator proficiency checks (OPC), flight simulation training devices (FSTD), and core competencies."
    },
    {
        "name": "Ground Handling & Ramp Safety Management",
        "category": "Ground Operations & Ramp Safety",
        "description": "Ground handling regulations, marshalling, pushback procedures, fueling safety, baggage and cargo loading, and ramp accident prevention."
    }
]

def main():
    print("Initializing Kùzu Engine and CustomConceptManager...")
    eng = get_engine()
    mgr = get_custom_concept_manager()

    print(f"\nSeeding {len(CONCEPTS_TO_SEED)} domain-reasoned concepts into custom_concepts.json...\n")
    success_count = 0
    total_provs = 0

    for item in CONCEPTS_TO_SEED:
        name = item["name"]
        cat = item["category"]
        desc = item["description"]
        print(f"-> Processing '{name}' ({cat})...", end="", flush=True)
        try:
            res = mgr.generate_concept(name=name, category=cat, description=desc, eng=eng)
            prov_count = res.get("total_governing_provisions", 0)
            annex_count = len(res.get("provisions_by_annex", {}))
            total_provs += prov_count
            success_count += 1
            print(f" [OK: {prov_count} rules across {annex_count} annexes]")
        except Exception as e:
            print(f" [FAILED: {e}]")

    print(f"\nSeeding completed: {success_count}/{len(CONCEPTS_TO_SEED)} concepts generated.")
    print(f"Total governing provision links discovered: {total_provs}")

if __name__ == "__main__":
    main()
