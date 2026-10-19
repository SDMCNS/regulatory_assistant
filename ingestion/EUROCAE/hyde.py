"""
HyDE (Hypothetical Document Embeddings) Generator for EUROCAE Standards.

Generates a synthetic technical summary and operational scope based on the
document title, interpreted acronyms, domain, and working group.
This summary is used STRICTLY for semantic vector embedding and retrieval matching,
and is not presented as authoritative standard body text.
"""

import requests
from typing import Optional
from ingestion.core.config import settings
from .models import EurocaeStandard


def generate_heuristic_hyde_summary(standard: EurocaeStandard) -> str:
    """
    Synthesizes a rich domain-specific technical scope passage for a standard
    without requiring an external LLM connection.
    Interprets acronyms, working group mandates, and technical domains to produce
    optimal embedding representation.
    """
    ref = standard.reference
    title = standard.title
    expanded_title = standard.expanded_title
    domain = standard.domain or "Aviation Engineering & Operations"
    wg = standard.working_group or "Specialist Technical Committee"
    wg_desc = standard.working_group_desc or ""
    org = standard.organization or "EUROCAE"
    status_str = f"status '{standard.status}'" + (f", target publication {standard.publication_date}" if standard.publication_date else "")

    parts = [
        f"This European aviation standard {ref} is issued by {org} under the technical domain of {domain}.",
        f"The official title is '{title}', which specifies: {expanded_title}."
    ]

    if wg_desc and wg_desc != wg:
        parts.append(f"It is developed and maintained by {wg} ({wg_desc}), currently having {status_str}.")
    elif wg:
        parts.append(f"It is developed and maintained by working group {wg}, currently having {status_str}.")

    # Domain and scope elaboration for dense embeddings
    scope_details = []
    lower_title = title.lower()

    if "mops" in lower_title or "minimum operational performance" in lower_title:
        scope_details.append(
            "As a Minimum Operational Performance Standard (MOPS), this document specifies equipment-level design, "
            "environmental qualification, bench testing, software and hardware requirements, and flight test procedures "
            "to assure compliant and safe airborne or ground avionics operations."
        )
    elif "masps" in lower_title or "masp" in lower_title or "minimum aviation system" in lower_title:
        scope_details.append(
            "As a Minimum Aviation System Performance Standard (MASPS), this document establishes end-to-end "
            "system-level operational requirements, performance allocations, communications and surveillance criteria, "
            "and airspace integration specifications."
        )
    elif "interoperability" in lower_title or "interop" in lower_title or "data exchange" in lower_title:
        scope_details.append(
            "This document establishes technical interoperability criteria, interface specifications, protocol profiles, "
            "and data formatting standards enabling seamless multi-stakeholder and cross-border system exchange."
        )
    elif "guidance" in lower_title or "guide" in lower_title or "guidelines" in lower_title:
        scope_details.append(
            "This document provides industry guidance, best practices, engineering analysis methodologies, "
            "and recommended compliance techniques supporting certification and safety verification."
        )

    # Technology specific elaborations
    if any(k in lower_title for k in ["acas", "tcas", "collision avoidance"]):
        scope_details.append("Covers surveillance algorithms, traffic alerting, resolution advisories (RA), collision risk assessment, and airspace separation.")
    if any(k in lower_title for k in ["ads-b", "tis-b", "surveillance", "squitter", "mlat"]):
        scope_details.append("Covers aircraft position broadcasting, transponder messages, ground receiver performance, latency, and surveillance integrity.")
    if any(k in lower_title for k in ["vtol", "uas", "rpas", "drone", "sora", "sail"]):
        scope_details.append("Covers uncrewed and innovative aerial systems, specific operations risk assessment (SORA), airworthiness criteria, and ground/air risk mitigations.")
    if any(k in lower_title for k in ["hirf", "lightning", "emc", "high voltage"]):
        scope_details.append("Covers electromagnetic environmental effects, high-intensity radiated fields, lightning zoning, electrical insulation, and physical shielding.")
    if any(k in lower_title for k in ["voip", "vdl", "atn", "communications", "radio"]):
        scope_details.append("Covers digital voice and data communications, ground-ground and air-ground network protocols, audio quality, and latency limits.")
    if any(k in lower_title for k in ["a-smgcs", "aerodrome", "runway", "surface movement", "airport"]):
        scope_details.append("Covers aerodrome surface guidance, runway incursion prevention, surface movement radar integration, and vehicle tracking.")

    # Acronym definitions summary
    if standard.recognized_acronyms:
        acronym_list = ", ".join([f"{k}: {v.split('—')[0].strip()}" for k, v in list(standard.recognized_acronyms.items())[:5]])
        scope_details.append(f"Key technical acronyms and concepts defined in this standard include: {acronym_list}.")

    if standard.easa_reference:
        scope_details.append(f"Direct European regulatory linkage: {standard.easa_reference}.")

    if scope_details:
        parts.append(" ".join(scope_details))

    return "\n\n".join(parts)


def generate_llm_hyde_summary(standard: EurocaeStandard, timeout: int = 15) -> Optional[str]:
    """
    Calls the local LLM (or LM Studio) to generate a hypothetical technical scope
    for the standard. Falls back cleanly to None on timeout or error.
    """
    prompt = (
        f"You are an expert on European civil aviation industry standards (EUROCAE, RTCA, EASA, EUROCONTROL).\n"
        f"Standard Reference: {standard.reference}\n"
        f"Official Title: {standard.title}\n"
        f"Interpreted Title: {standard.expanded_title}\n"
        f"Working Group: {standard.working_group} ({standard.working_group_desc or ''})\n"
        f"Technical Domain: {standard.domain or ''}\n"
        f"Status: {standard.status} ({standard.publication_date or ''})\n\n"
        f"Please write a concise 1-2 paragraph hypothetical technical scope and operational overview of what this "
        f"standard specifies, its equipment/system test criteria, and its safety role in civil aviation. "
        f"This text will be used exclusively for semantic vector embeddings. Do not include conversational preambles."
    )

    payload = {
        "model": getattr(settings, "LLM_MODEL_NAME", "local-model"),
        "messages": [
            {"role": "system", "content": "You are a technical aviation standards summarizer. Produce factual, high-density technical scope passages for embedding generation."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 300
    }

    try:
        url = f"{settings.LM_STUDIO_BASE_URL}/chat/completions"
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content and len(content) > 50:
                return content
    except Exception:
        # LLM not running or timed out; silent fallback
        pass

    return None


def generate_hyde_embedding_text(standard: EurocaeStandard, use_llm: bool = False) -> str:
    """
    Generates the HyDE embedding summary for a EUROCAE standard.
    Uses LLM if requested and accessible, otherwise uses the domain heuristic generator.
    """
    if use_llm:
        llm_summary = generate_llm_hyde_summary(standard)
        if llm_summary:
            return llm_summary

    return generate_heuristic_hyde_summary(standard)
