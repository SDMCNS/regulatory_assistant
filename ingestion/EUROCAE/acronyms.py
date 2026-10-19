"""
EUROCAE and Aviation Industry Standards Acronym Dictionary and Expansion Engine.

Accurately interprets industry acronyms found in EUROCAE, RTCA, EUROCONTROL,
and EASA documentation (e.g., MASPS, MOPS, SPR, INTEROP, OSED, SORA).
"""

import re
from typing import Dict, List, Tuple

# Authoritative dictionary of aviation standards and regulatory acronyms
AVIATION_ACRONYMS: Dict[str, Dict[str, str]] = {
    # Standards Types & Engineering Documents
    "MASPS": {
        "full_name": "Minimum Aviation System Performance Standards",
        "description": "System-level performance requirements and operational criteria for total end-to-end aviation capabilities.",
        "category": "Standard Type"
    },
    "MASP": {
        "full_name": "Minimum Aviation System Performance Standards",
        "description": "System-level performance requirements and operational criteria for total end-to-end aviation capabilities.",
        "category": "Standard Type"
    },
    "MOPS": {
        "full_name": "Minimum Operational Performance Standards",
        "description": "Equipment-level performance specifications and bench/flight test procedures for avionics and ground equipment.",
        "category": "Standard Type"
    },
    "MOPR": {
        "full_name": "Minimum Operational Performance Requirements",
        "description": "Operational requirements defining minimum performance thresholds for system operations.",
        "category": "Standard Type"
    },
    "MPS": {
        "full_name": "Minimum Performance Specification",
        "description": "Baseline technical specification defining mandatory performance boundaries.",
        "category": "Standard Type"
    },
    "SPR": {
        "full_name": "Safety and Performance Requirements",
        "description": "Allocated safety and operational performance requirements derived from operational hazards.",
        "category": "Safety / Requirements"
    },
    "INTEROP": {
        "full_name": "Interoperability Requirements",
        "description": "Technical and interface requirements ensuring multi-vendor, cross-border system compatibility.",
        "category": "Interoperability"
    },
    "OSED": {
        "full_name": "Operational Services and Environment Definition",
        "description": "Description of the operational services, operating environment, and operational scenarios.",
        "category": "Operations"
    },
    "CONOPS": {
        "full_name": "Concept of Operations",
        "description": "High-level concept detailing how system capabilities will be deployed and operated.",
        "category": "Operations"
    },
    "DLASD": {
        "full_name": "Data Link Application Source Definition",
        "description": "Standardized application baseline definition for air-ground data communications.",
        "category": "Datalink"
    },

    # Surveillance & Collision Avoidance
    "ACAS": {
        "full_name": "Airborne Collision Avoidance System",
        "description": "Aircraft system based on transponder signals providing traffic alerts and resolution advisories.",
        "category": "Surveillance / Safety"
    },
    "TCAS": {
        "full_name": "Traffic Alert and Collision Avoidance System",
        "description": "Airborne collision avoidance equipment (e.g., TCAS II Version 7.1).",
        "category": "Surveillance / Safety"
    },
    "ADS-B": {
        "full_name": "Automatic Dependent Surveillance-Broadcast",
        "description": "Surveillance technology where aircraft determine position via GNSS and periodically broadcast it.",
        "category": "Surveillance"
    },
    "TIS-B": {
        "full_name": "Traffic Information Service-Broadcast",
        "description": "Ground broadcast service providing surveillance data to aircraft not equipped with ADS-B In.",
        "category": "Surveillance"
    },
    "A-SMGCS": {
        "full_name": "Advanced Surface Movement Guidance and Control System",
        "description": "Aerodrome system providing routing, guidance, and surveillance to aircraft and vehicles on the ground.",
        "category": "Aerodrome / Surveillance"
    },
    "SMAS": {
        "full_name": "Surface Movement Awareness System",
        "description": "Airport surface awareness and safety alerting capability for ground operations.",
        "category": "Aerodrome / Surveillance"
    },
    "SMR": {
        "full_name": "Surface Movement Radar",
        "description": "Primary radar dedicated to monitoring runway and taxiway movements.",
        "category": "Aerodrome / Surveillance"
    },
    "MLAT": {
        "full_name": "Multilateration",
        "description": "Surveillance technique based on time difference of arrival (TDOA) of transponder signals.",
        "category": "Surveillance"
    },
    "WAM": {
        "full_name": "Wide Area Multilateration",
        "description": "Multilateration network configured for terminal area and en-route surveillance.",
        "category": "Surveillance"
    },
    "GEN-SUR": {
        "full_name": "General Surveillance",
        "description": "Baseline surveillance criteria across radar, ADS-B, and multilateration.",
        "category": "Surveillance"
    },

    # Uncrewed & Advanced Air Mobility (UAS / RPAS / VTOL / AAM)
    "UAS": {
        "full_name": "Unmanned Aircraft System",
        "description": "Uncrewed aircraft and its associated remote pilot station, command and control links.",
        "category": "Uncrewed Aviation"
    },
    "RPAS": {
        "full_name": "Remotely Piloted Aircraft System",
        "description": "Remotely piloted aircraft, control station, command and control links.",
        "category": "Uncrewed Aviation"
    },
    "VTOL": {
        "full_name": "Vertical Take-Off and Landing",
        "description": "Heavier-than-air aircraft capable of vertical takeoff, vertical landing, and low-speed flight.",
        "category": "Advanced Air Mobility"
    },
    "AAM": {
        "full_name": "Advanced Air Mobility",
        "description": "Air transportation system utilizing highly automated aircraft for passengers and cargo.",
        "category": "Advanced Air Mobility"
    },
    "IAS": {
        "full_name": "Innovative Aerial Services",
        "description": "Advanced UAS and VTOL commercial operations domain including air taxis and delivery.",
        "category": "Innovative Aerial Services"
    },
    "SORA": {
        "full_name": "Specific Operations Risk Assessment",
        "description": "Risk assessment methodology for UAS operations in the specific category under EU regulations.",
        "category": "Risk Assessment"
    },
    "SAIL": {
        "full_name": "Specific Assurance and Integrity Level",
        "description": "Level of rigor (SAIL I through VI) assigned to UAS operations derived from the SORA process.",
        "category": "Safety / Risk"
    },
    "DAA": {
        "full_name": "Detect and Avoid",
        "description": "Capability to see, sense, or detect conflicting traffic or other hazards and take appropriate action.",
        "category": "Uncrewed Aviation / Safety"
    },

    # Air Traffic Management & Communications
    "ATM": {
        "full_name": "Air Traffic Management",
        "description": "Dynamic, integrated management of air traffic and airspace.",
        "category": "Air Traffic Management"
    },
    "ANS": {
        "full_name": "Air Navigation Services",
        "description": "Services provided to air traffic during all phases of operations (ATM, CNS, MET, AIS, SAR).",
        "category": "Air Traffic Management"
    },
    "ATS": {
        "full_name": "Air Traffic Services",
        "description": "Flight information service, alerting service, air traffic advisory service, and air traffic control service.",
        "category": "Air Traffic Management"
    },
    "ATC": {
        "full_name": "Air Traffic Control",
        "description": "Service provided for the purpose of preventing collisions and expediting orderly air traffic.",
        "category": "Air Traffic Management"
    },
    "CNS": {
        "full_name": "Communications, Navigation, and Surveillance",
        "description": "Core technological infrastructure supporting air traffic management.",
        "category": "CNS"
    },
    "CNS/ATM": {
        "full_name": "Communications, Navigation, and Surveillance / Air Traffic Management",
        "description": "Integrated CNS systems supporting modern global air traffic management concepts.",
        "category": "CNS"
    },
    "SWIM": {
        "full_name": "System-Wide Information Management",
        "description": "Standards, infrastructure, and governance enabling seamless ATM information exchange.",
        "category": "Information Management"
    },
    "AMAN": {
        "full_name": "Arrival Manager",
        "description": "ATM decision support tool optimizing the arrival sequence and metering into terminal airspaces.",
        "category": "Air Traffic Management"
    },
    "VOIP": {
        "full_name": "Voice over Internet Protocol",
        "description": "Digital voice transmission technology applied to ground-ground and ground-air ATM communications.",
        "category": "Communications"
    },
    "ATN": {
        "full_name": "Aeronautical Telecommunication Network",
        "description": "Internetwork architecture allowing ground, air-ground, and avionic data communications.",
        "category": "Communications"
    },
    "VDL": {
        "full_name": "VHF Digital Link",
        "description": "Air-ground data link operating in the VHF aeronautical mobile band (e.g., VDL Mode 2).",
        "category": "Communications"
    },
    "VHF": {
        "full_name": "Very High Frequency",
        "description": "Radio frequency spectrum (118 - 137 MHz) utilized for civil aviation voice and data communications.",
        "category": "Communications"
    },
    "AMS(R)S": {
        "full_name": "Aeronautical Mobile Satellite (Route) Service",
        "description": "Satellite communication service reserved for safety and regularity of flights along civil air routes.",
        "category": "Communications"
    },
    "NGSS": {
        "full_name": "Next Generation Satellite Systems",
        "description": "Modern multi-constellation satellite communications supporting oceanic and remote ATM.",
        "category": "Communications"
    },
    "RCP": {
        "full_name": "Required Communication Performance",
        "description": "Specification of performance parameters (transaction time, continuity, availability, integrity) for communications.",
        "category": "Communications"
    },
    "RSP": {
        "full_name": "Required Surveillance Performance",
        "description": "Specification of performance criteria for surveillance data delivery.",
        "category": "Surveillance"
    },
    "RNP": {
        "full_name": "Required Navigation Performance",
        "description": "Statement of the navigation performance necessary for operation within a defined airspace, including on-board monitoring.",
        "category": "Navigation"
    },
    "PBN": {
        "full_name": "Performance-Based Navigation",
        "description": "Area navigation based on performance requirements for aircraft operating along an ATS route.",
        "category": "Navigation"
    },
    "GNSS": {
        "full_name": "Global Navigation Satellite System",
        "description": "Satellite constellations providing geospatial positioning (GPS, Galileo, GLONASS, BeiDou).",
        "category": "Navigation"
    },
    "DME": {
        "full_name": "Distance Measuring Equipment",
        "description": "Radionavigation technology measuring slant range distance between aircraft and ground beacons.",
        "category": "Navigation"
    },
    "MLS": {
        "full_name": "Microwave Landing System",
        "description": "Precision radionavigation approach and landing guidance system.",
        "category": "Navigation"
    },

    # Aeronautical Information & Data Exchange
    "AIXM": {
        "full_name": "Aeronautical Information Exchange Model",
        "description": "XML/GML standard enabling digital management and exchange of aeronautical data sets.",
        "category": "Aeronautical Information"
    },
    "AIS": {
        "full_name": "Aeronautical Information Service",
        "description": "Service providing aeronautical data and information necessary for the safety of air navigation.",
        "category": "Aeronautical Information"
    },
    "NOTAM": {
        "full_name": "Notice to Airmen",
        "description": "Notice containing information essential to personnel concerned with flight operations.",
        "category": "Aeronautical Information"
    },
    "D-NOTAM": {
        "full_name": "Digital Notice to Airmen",
        "description": "Structured digital format for NOTAM distribution conforming to AIXM.",
        "category": "Aeronautical Information"
    },
    "CDM": {
        "full_name": "Collaborative Decision Making",
        "description": "Operational philosophy allowing all ATM partners to optimize decisions through timely information sharing.",
        "category": "Operations"
    },
    "FANS": {
        "full_name": "Future Air Navigation System",
        "description": "Avionics suite providing direct datalink communication between pilot and air traffic controller.",
        "category": "Avionics / ATM"
    },

    # Safety Assessment & Environmental Testing
    "FHA": {
        "full_name": "Functional Hazard Assessment",
        "description": "Systematic, comprehensive examination of aircraft/system functions to identify failure conditions.",
        "category": "Safety Assessment"
    },
    "AFHA": {
        "full_name": "Aircraft Functional Hazard Assessment",
        "description": "Top-level safety assessment performed at the overall aircraft architecture level.",
        "category": "Safety Assessment"
    },
    "PASA": {
        "full_name": "Preliminary Aircraft Safety Assessment",
        "description": "Initial safety evaluation establishing safety requirements for aircraft architecture.",
        "category": "Safety Assessment"
    },
    "PSSA": {
        "full_name": "Preliminary System Safety Assessment",
        "description": "System-level safety assessment allocating requirements to hardware and software items.",
        "category": "Safety Assessment"
    },
    "SSA": {
        "full_name": "System Safety Assessment",
        "description": "Comprehensive evaluation verifying that the implemented system satisfies all allocated safety requirements.",
        "category": "Safety Assessment"
    },
    "IHA": {
        "full_name": "Installation Hazard Assessment",
        "description": "Assessment of hazards introduced by system physical installation and environmental factors.",
        "category": "Safety Assessment"
    },
    "HIRF": {
        "full_name": "High-Intensity Radiated Fields",
        "description": "High-power electromagnetic fields generated by transmitters (radar, broadcast) requiring aircraft shielding.",
        "category": "Electromagnetic Environment"
    },
    "HLSA": {
        "full_name": "HIRF and Lightning Safety Assessment",
        "description": "Safety evaluation verifying aircraft resilience against high-intensity radiated fields and lightning strikes.",
        "category": "Safety Assessment"
    },
    "EMC": {
        "full_name": "Electromagnetic Compatibility",
        "description": "Ability of electrical equipment to function properly without generating or suffering electromagnetic interference.",
        "category": "Environmental Testing"
    },
    "HTAWS": {
        "full_name": "Helicopter Terrain Awareness and Warning System",
        "description": "Terrain alerting and terrain display system tailored to rotary-wing operations.",
        "category": "Terrain Warning / Safety"
    },
    "PED": {
        "full_name": "Portable Electronic Devices",
        "description": "Passenger or crew portable electronic devices evaluated for radio frequency interference in cabin.",
        "category": "Avionics / Cabins"
    },
    "ISMS": {
        "full_name": "Information Security Management System",
        "description": "Systematic approach for managing cybersecurity risks and protecting sensitive aviation digital assets.",
        "category": "Cybersecurity"
    },
    "AISS": {
        "full_name": "Aeronautical Information System Security",
        "description": "Security engineering framework protecting airborne and ground aviation systems from digital threats.",
        "category": "Cybersecurity"
    }
}

# Working Groups mapping
EUROCAE_WORKING_GROUPS: Dict[str, str] = {
    "WG-31": "Lightning and High Intensity Radiated Fields (HIRF)",
    "WG-32": "Microwave Landing System (MLS) Ground Equipment",
    "WG-41": "Advanced Surface Movement Guidance and Control Systems (A-SMGCS)",
    "WG-44": "Aeronautical Databases (Terrain, Obstacle, Aerodrome Mapping)",
    "WG-51": "Automatic Dependent Surveillance-Broadcast (ADS-B)",
    "WG-59": "Flight Object Interoperability",
    "WG-63": "Complex Aircraft System Engineering and Safety Assessment",
    "WG-67": "Voice over Internet Protocol (VoIP) for Air Traffic Management",
    "WG-72": "Aviation Cybersecurity and Information Security",
    "WG-75": "Traffic Alert & Collision Avoidance (TCAS / ACAS)",
    "WG-76": "Crash Survivability and Flight Data Recorders",
    "WG-82": "Satellite Communications and Next Generation Satellite Systems (NGSS)",
    "WG-85": "Navigation and Area Navigation Performance (RNP/RNAV)",
    "WG-104": "Air Traffic Management Arrival Management (AMAN) SWIM Services",
    "WG-105": "Unmanned Aircraft Systems (UAS / RPAS) and SORA Compliance",
    "WG-107": "Distance Measuring Equipment (DME)",
    "WG-109": "Runway Weather Information Systems (RWIS)",
    "WG-112": "Vertical Take-Off and Landing (VTOL) and Innovative Aerial Services",
    "WG-115": "Airborne Weather Radar",
    "WG-116": "Sustainability and High Voltage Aircraft Electrical Systems",
    "WG-118": "Advanced Air Mobility (AAM) Aircraft Recording Systems",
    "WG-122": "Virtual Centres and ATM Data Services Interoperability",
    "WG-130": "Attestation of Conformity of ATM/ANS Equipment"
}


def expand_acronyms(text: str) -> str:
    """
    Expands acronyms in a text string to their full definitions.
    For example: 'MOPS for ACAS Xu' -> 'Minimum Operational Performance Standards (MOPS) for Airborne Collision Avoidance System (ACAS) Xu'.
    """
    if not text:
        return ""

    expanded = text

    # Sort acronyms by length descending to avoid partial replacements (e.g. MASPS before MASP, ACAS before CAS)
    sorted_acronyms = sorted(AVIATION_ACRONYMS.keys(), key=len, reverse=True)

    for acronym in sorted_acronyms:
        # Match whole word
        pattern = r'\b' + re.escape(acronym) + r'\b'
        data = AVIATION_ACRONYMS[acronym]
        full_name = data["full_name"]

        # Only replace if the full name isn't already directly adjacent
        if re.search(pattern, expanded) and full_name.lower() not in expanded.lower():
            # Replace first instance or all instances with full name (ACRONYM)
            def replace_func(m):
                return f"{full_name} ({acronym})"
            expanded = re.sub(pattern, replace_func, expanded)

    return expanded


def get_acronym_definitions(text: str) -> Dict[str, str]:
    """
    Finds all recognized acronyms in a given text and returns their definitions.
    """
    if not text:
        return {}

    found: Dict[str, str] = {}
    tokens = set(re.findall(r'\b[A-Za-z0-9\-\/]{2,10}\b', text))

    for token in tokens:
        upper_token = token.upper()
        if upper_token in AVIATION_ACRONYMS:
            data = AVIATION_ACRONYMS[upper_token]
            found[upper_token] = f"{data['full_name']} — {data['description']}"

    return found


def get_working_group_description(wg: str) -> str:
    """
    Returns the descriptive name of a EUROCAE working group.
    """
    if not wg:
        return ""
    clean_wg = wg.strip().upper()
    return EUROCAE_WORKING_GROUPS.get(clean_wg, clean_wg)
