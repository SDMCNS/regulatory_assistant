"""
analyzer.py - Consultation Feedback Analytics Engine.

Implements:
1. Common Themes Identification (Multi-label thematic clustering).
2. Sentiment & Regulatory Stance Analysis.
3. Comment Validity & Actionability Assessment.
4. Consulted Document Section Alignment & Matching.
5. Aggregated Consultation Metrics & Stakeholder Cross-Tabulations.

IMPORTANT: Strictly assists human regulatory reviewers. Does NOT resolve comments.
"""

from __future__ import annotations

import json
import math
import re
from typing import Dict, Any, List, Optional, Tuple


THEME_DEFINITIONS = {
    "Implementation Timeline & Phasing": [
        "transition", "timeline", "deadline", "implementation", "grace period",
        "entry into force", "effective date", "phase", "phased", "lead time",
        "delay", "postpone", "months", "years", "unachievable schedule"
    ],
    "Economic & Compliance Costs": [
        "cost", "financial", "burden", "economic", "expense", "budget", "commercial",
        "investment", "fee", "disproportionate cost", "charge", "hardware cost", "pricing"
    ],
    "Definitions & Terminology Clarity": [
        "definition", "clarify", "ambiguous", "unclear", "define", "terminology",
        "meaning", "interpretation", "shall vs should", "vague", "wording", "scope definition"
    ],
    "Safety Risk & Oversight Gaps": [
        "safety", "risk", "hazard", "oversight", "incident", "accident", "mitigation",
        "human factors", "workload", "fatigue", "safety management", "sms", "gap", "vulnerability"
    ],
    "Technical & Operational Feasibility": [
        "technical", "feasible", "impractical", "unworkable", "operational",
        "cockpit", "avionics", "software", "infrastructure", "fleet", "retrofit", "legacy"
    ],
    "Proportionality for Small Operators": [
        "proportional", "proportionality", "small operator", "sme", "general aviation",
        "aeroclub", "one size fits all", "excessive requirement", "non-complex"
    ],
    "International Harmonization & ICAO": [
        "icao", "faa", "annex", "harmonization", "harmonisation", "bilateral", "basad",
        "divergence", "international standard", "global alignment", "easa-faa"
    ],
    "Data Protection & Cyber Security": [
        "cyber", "cybersecurity", "part-is", "security", "data", "confidentiality",
        "gdpr", "information security", "sensitive", "threat", "disclosure"
    ],
    "Legal Competence & Mandate Scope": [
        "competence", "mandate", "basic regulation", "delegated", "implementing",
        "legal basis", "ultra vires", "national authority", "sovereignty", "article"
    ],
    "Editorial & Cross-References": [
        "typo", "editorial", "grammar", "spelling", "reference", "cross-reference",
        "numbering", "renumber", "punctuation", "paragraph numbering"
    ]
}


def analyze_comment_themes(text: str, proposed_text: str = "", rationale: str = "") -> List[str]:
    """Identifies common themes present in the feedback comment."""
    combined = f"{text} {proposed_text} {rationale}".lower()
    scores: List[Tuple[str, int]] = []

    for theme_name, keywords in THEME_DEFINITIONS.items():
        count = sum(1 for kw in keywords if kw in combined)
        if count > 0:
            scores.append((theme_name, count))

    # Sort themes by match count descending
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        return ["General Policy & Regulatory Approach"]

    # Take top matched themes (up to 3)
    return [theme for theme, _ in scores[:3]]


def analyze_comment_sentiment(text: str, rationale: str = "") -> Tuple[str, float]:
    """
    Analyzes regulatory stance and tone:
    - Strongly Critical / Objection (-0.8 to -1.0)
    - Concerned / Support with Amendments (-0.3 to -0.5)
    - Neutral / Inquiring / Clarification (0.0)
    - Supportive / Endorsement (+0.5 to +1.0)
    """
    combined = f"{text} {rationale}".lower()

    # Strong critical indicators
    critical_markers = [
        "strongly object", "strongly oppose", "unacceptable", "unworkable", "untenable",
        "unrealistic", "completely unrealistic", "completely inadequate", "inadequate",
        "reject", "must be deleted", "delete this", "disastrous", "impossible to comply",
        "flawed", "completely disagree", "grave concern", "severely impact", "unjustified",
        "disproportionate burden", "excessive burden", "unviable"
    ]
    # Concerned / conditional support markers
    concerned_markers = [
        "support the objective but", "support in principle but", "concerned", "undue burden",
        "request an amendment", "urge the agency to amend", "needlessly strict",
        "should be revised", "recommend modifying", "too restrictive", "caution", "difficult",
        "extend", "extension", "delay", "too short", "challenging"
    ]
    # Supportive markers
    supportive_markers = [
        "fully support", "strongly support", "welcome", "fully agree", "commend",
        "appropriate", "well-balanced", "valuable improvement", "endorse", "concur"
    ]
    # Inquiring / neutral markers
    inquiring_markers = [
        "please clarify", "clarification needed", "unclear whether", "does this apply",
        "seek guidance", "how should", "request definition", "interpretation"
    ]

    crit_count = sum(1 for m in critical_markers if m in combined)
    conc_count = sum(1 for m in concerned_markers if m in combined)
    supp_count = sum(1 for m in supportive_markers if m in combined)
    inq_count = sum(1 for m in inquiring_markers if m in combined)

    if crit_count > 0 and crit_count >= supp_count:
        return "Strongly Critical", -0.85
    elif supp_count > 0 and supp_count > conc_count and supp_count > crit_count:
        return "Supportive", 0.75
    elif conc_count > 0 or (crit_count > 0 and supp_count > 0):
        return "Concerned", -0.35
    elif inq_count > 0:
        return "Neutral / Inquiring", 0.05
    else:
        # Default sentiment heuristic based on polarity words
        neg_words = sum(1 for w in ["problem", "issue", "failure", "burden", "risk", "gap", "lack"] if w in combined)
        pos_words = sum(1 for w in ["good", "clear", "positive", "helpful", "benefit", "robust"] if w in combined)
        if neg_words > pos_words:
            return "Concerned", -0.25
        elif pos_words > neg_words:
            return "Supportive", 0.5
        return "Neutral / Inquiring", 0.0


def assess_comment_validity(
    text: str,
    proposed_text: str = "",
    rationale: str = "",
    target_section: str = ""
) -> Tuple[str, str]:
    """
    Evaluates validity and actionability of comment:
    1. Actionable Proposal: Concrete alternative text or specific empirical data provided.
    2. Substantive Technical Concern: Details operational/safety/compliance problem with sound reasoning.
    3. Clarification Request: Identifies language ambiguity or cross-reference clash.
    4. Editorial / Minor: Grammar, spelling, formatting fix.
    5. General Opinion / Policy Grievance: Broad opinion without actionable regulatory remedy.
    """
    combined = f"{text} {rationale}".lower()
    has_proposed_text = bool(proposed_text and len(proposed_text.strip()) > 5)

    # 1. Editorial / Minor
    if any(k in combined for k in ["typo", "spelling", "grammar", "renumber", "cross-reference", "punctuation"]) and len(text) < 150:
        return "Editorial / Minor", "Focuses on text correction, grammar, or internal numbering."

    # 2. Actionable Proposal
    if has_proposed_text or any(k in combined for k in ["propose the following wording", "suggest to amend as follows", "replace with:", "insert:"]):
        return (
            "Actionable Proposal",
            "Provides explicit alternative drafting text or concrete revision parameters that can be directly evaluated by the drafter."
        )

    # 3. Clarification Request
    if any(k in combined for k in ["clarify", "clarification", "unclear", "define", "what is meant by", "does this mean"]):
        return (
            "Clarification Request",
            "Identifies ambiguous regulatory terminology or asks for official guidance on application scope."
        )

    # 4. Substantive Technical Concern
    if any(k in combined for k in ["safety risk", "technical", "unfeasible", "supply chain", "conflict with", "icao", "operational impact", "workload", "compliance cost"]):
        return (
            "Substantive Technical Concern",
            "Articulates a specific technical, operational, or legal impediment with substantive justification."
        )

    # 5. Length & structure check
    if len(text.strip().split()) > 25 and target_section and target_section.lower() != "general":
        return (
            "Substantive Technical Concern",
            "Addresses a specific provision with reasoned observations."
        )

    # Fallback: General Opinion
    return (
        "General Opinion / Policy Grievance",
        "Expresses a general stance or sentiment without specific regulatory text changes or detailed technical proof."
    )


def extract_document_sections(raw_text: str) -> List[Dict[str, str]]:
    """
    Splits consultation document into structured sections/articles for side-by-side display.
    """
    sections: List[Dict[str, str]] = []
    lines = raw_text.splitlines()

    current_title = "Preamble / General"
    current_lines: List[str] = []

    # Patterns matching Articles, Sections, Chapters, AMC/GM
    sec_pattern = re.compile(
        r"^(?:#{1,3}\s+)?((?:Article\s+\d+|AMC\d*\s+[A-Z0-9\.\-]+|GM\d*\s+[A-Z0-9\.\-]+|Section\s+\d+(?:\.\d+)*|Part\-[A-Z0-9]+|Chapter\s+[0-9IVX]+|Annex\s+[0-9IVX]+)(?::|\s+[-–—]|\s+[A-Z]).*)$",
        re.IGNORECASE
    )

    for line in lines:
        m = sec_pattern.match(line.strip())
        if m:
            if current_lines:
                sections.append({
                    "title": current_title.strip("# ").strip(),
                    "content": "\n".join(current_lines).strip()
                })
                current_lines = []
            current_title = m.group(1).strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "title": current_title.strip("# ").strip(),
            "content": "\n".join(current_lines).strip()
        })

    # If no structured headings were found, break into large chunks of ~800 words
    if len(sections) <= 1 and len(raw_text.split()) > 800:
        words = raw_text.split()
        chunk_size = 600
        sections = []
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i : i + chunk_size]
            sections.append({
                "title": f"Section Part {len(sections) + 1}",
                "content": " ".join(chunk_words)
            })

    return sections


def match_comment_to_document_section(
    target_section: str,
    comment_text: str,
    sections: List[Dict[str, str]]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Finds best matching section title and text snippet from the consultation document.
    """
    if not sections:
        return None, None

    clean = (target_section or "").lower().strip()

    # 1. Exact article / section / clause number match (e.g. "article 4", "art 4(2)", "section 7")
    art_match = re.search(r"(?:article|art\.?|section|sec\.?)\s*(\d+)", clean)
    if art_match:
        num = art_match.group(1)
        for s in sections:
            if re.search(rf"\b(?:article|art\.?|section|sec\.?)\s*{num}\b", s["title"].lower()):
                return s["title"], s["content"][:2500]

    # 2. Check Annex / Chapter / Part / AMC / GM matches
    spec_match = re.search(r"(?:annex|chapter|part|amc\d*|gm\d*)\s*([a-z0-9ivx\-]+)", clean)
    if spec_match:
        ident = spec_match.group(1)
        for s in sections:
            if re.search(rf"\b{re.escape(ident)}\b", s["title"].lower()):
                return s["title"], s["content"][:2500]

    # 3. Match significant tokens against section titles
    tokens = [t for t in re.findall(r"\w+", clean) if t not in ["the", "and", "for", "with", "general", "whole", "doc", "document"]]
    if tokens:
        best_s = None
        best_score = 0
        for s in sections:
            st_lower = s["title"].lower()
            score = sum(3 if re.search(rf"\b{re.escape(t)}\b", st_lower) else (1 if t in st_lower else 0) for t in tokens)
            if score > best_score:
                best_score = score
                best_s = s
        if best_s and best_score >= 2:
            return best_s["title"], best_s["content"][:2500]

    # 4. Keyword search within section contents
    comment_tokens = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", comment_text) if w.lower() not in ["shall", "should", "operator", "regulation", "draft"]]
    if comment_tokens:
        best_sec = None
        best_count = 0
        for sec in sections:
            content_lower = sec["content"].lower()
            matched = sum(1 for w in comment_tokens[:15] if w in content_lower)
            if matched > best_count:
                best_count = matched
                best_sec = sec

        if best_sec and best_count >= 3:
            return best_sec["title"], best_sec["content"][:2500]

    # 5. Fallback
    if sections:
        return sections[0]["title"], sections[0]["content"][:2500]

    return None, None


def compute_text_similarity(t1: str, t2: str) -> float:
    """Computes token Jaccard-overlap similarity between two text snippets."""
    words1 = set(re.findall(r"\b[a-zA-Z]{3,}\b", (t1 or "").lower()))
    words2 = set(re.findall(r"\b[a-zA-Z]{3,}\b", (t2 or "").lower()))
    if not words1 or not words2:
        return 0.0
    inter = words1.intersection(words2)
    return len(inter) / math.sqrt(len(words1) * len(words2))


def extract_direction_of_travel(text: str, rationale: str = "", proposed_text: str = "") -> str:
    """Extracts the strategic policy direction / vector the stakeholder is pushing towards."""
    combined = f"{text} {rationale} {proposed_text}".lower()

    if any(k in combined for k in ["transition", "timeline", "deadline", "grace period", "months", "years", "delay", "postpone", "phased"]):
        return "Timeline Extension & Transitional Phasing"
    elif any(k in combined for k in ["proportional", "small operator", "sme", "general aviation", "glider", "exclude", "exemption", "non-complex"]):
        return "Proportionality Relief & Scope Exemptions for Non-Complex Entities"
    elif any(k in combined for k in ["cyber", "part-is", "pseudonym", "anonym", "confidential", "reporter identity", "just culture", "disclosure"]):
        return "Strengthening Reporter Confidentiality & Just Culture Protections"
    elif any(k in combined for k in ["icao", "faa", "harmonization", "harmonisation", "annex 13", "bilateral"]):
        return "International Standardization & ICAO Harmonization"
    elif any(k in combined for k in ["single window", "single portal", "unified", "standardized form", "fragmented"]):
        return "Operational Simplicity & Single-Window Harmonization"
    elif any(k in combined for k in ["amc", "gm", "guidance material", "acceptable means", "criteria", "clarify", "guidance"]):
        return "Flexibility via Non-Binding Guidance (AMC/GM) rather than Hard Rules"
    elif any(k in combined for k in ["cost", "budget", "procurement", "fee", "financial burden"]):
        return "Mitigation of Compliance Costs & Resourcing Burdens"
    elif any(k in combined for k in ["safety", "hazard", "risk", "mitigation", "sms"]):
        return "Enhancement of Risk Mitigation & Operational Safety Margins"
    else:
        return "Operational Refinement & Regulatory Clarification"


def evaluate_comment_dual_context(
    text: str,
    proposed_text: str = "",
    rationale: str = "",
    target_section: str = "",
    importance: str = "Medium",
    comment_type: str = "Observation",
    section_content: str = "",
    whole_doc_overview: str = ""
) -> Tuple[float, float, float, str, str]:
    """
    Evaluates a comment using dual-context weighting:
    - Specific Section Evaluation (75% weighting):
      Direct technical impact on the specific provision, timeline, wording, or standard.
    - Whole Document Evaluation (25% weighting):
      High-level alignment with the document's general scope, statutory objectives, and proportionality.
    Returns:
    (section_score, document_score, weighted_score, direction_of_travel, dual_eval_summary)
    """
    sentiment_label, base_sentiment_score = analyze_comment_sentiment(text, rationale)
    combined = f"{text} {rationale}".lower()

    # Section-level evaluation (75% weight)
    section_score = base_sentiment_score
    if proposed_text and sentiment_label in ["Strongly Critical", "Concerned"]:
        section_score = max(-0.95, min(-0.4, base_sentiment_score))
    elif sentiment_label == "Supportive":
        section_score = max(0.6, base_sentiment_score)
    elif sentiment_label == "Neutral / Inquiring":
        section_score = 0.05

    # Document-level evaluation (25% weight)
    if any(k in combined for k in ["support the objective", "support in principle", "welcome the initiative", "commend the agency", "aligns with icao"]):
        document_score = 0.45
    elif any(k in combined for k in ["categorically excluded", "disproportionate burden on the entire", "reject the regulation", "unviable for all", "ultra vires"]):
        document_score = -0.85
    elif sentiment_label == "Supportive":
        document_score = 0.80
    elif sentiment_label == "Strongly Critical":
        document_score = -0.40
    elif sentiment_label == "Concerned":
        document_score = -0.15
    else:
        document_score = 0.10

    # 75% local section, 25% whole document weighting
    weighted_score = round((section_score * 0.75) + (document_score * 0.25), 3)

    direction = extract_direction_of_travel(text, rationale, proposed_text)

    if weighted_score < -0.3:
        summary = (
            f"Section Impact (75%): {sentiment_label} ({section_score:+0.2f}) on '{target_section}'. "
            f"Document Impact (25%): {document_score:+0.2f}. Net Weighted: {weighted_score:+0.2f} - "
            f"Challenges provision while pushing for {direction.lower()}."
        )
    elif weighted_score > 0.3:
        summary = (
            f"Section Impact (75%): Supportive ({section_score:+0.2f}) on '{target_section}'. "
            f"Document Impact (25%): {document_score:+0.2f}. Net Weighted: {weighted_score:+0.2f} - "
            f"Confirms regulatory alignment and operational feasibility."
        )
    else:
        summary = (
            f"Section Impact (75%): Balanced inquiry ({section_score:+0.2f}) on '{target_section}'. "
            f"Document Impact (25%): {document_score:+0.2f}. Net Weighted: {weighted_score:+0.2f} - "
            f"Constructive technical engagement."
        )

    return section_score, document_score, weighted_score, direction, summary


def analyze_critical_comment_support_and_silence(
    comment: Dict[str, Any],
    all_comments: List[Dict[str, Any]],
    all_organisations: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Evaluates support from other stakeholders and quantifies the silent majority:
    - Active Co-objectors (organisations supporting or sharing the critical concern)
    - Active Opponents (organisations defending the draft provision)
    - Silent Stakeholders (organisations participating in the consultation that voiced NO objection)
    """
    current_org = (comment.get("organisation_name") or comment.get("stakeholder_name") or "Submitter").strip()
    target_sec = (comment.get("chapter_section") or comment.get("target_section") or "").strip()
    c_text = comment.get("comment_text", "")

    if not all_organisations:
        all_organisations = sorted(list(set(
            (c.get("organisation_name") or c.get("stakeholder_name") or "").strip()
            for c in all_comments
            if (c.get("organisation_name") or c.get("stakeholder_name"))
        )))

    total_orgs = max(len(all_organisations), 1)

    co_objectors = set()
    defenders = set()

    for other_c in all_comments:
        other_org = (other_c.get("organisation_name") or other_c.get("stakeholder_name") or "").strip()
        if not other_org:
            continue

        other_sec = (other_c.get("chapter_section") or other_c.get("target_section") or "").strip()
        other_sent = other_c.get("sentiment", "")

        is_same_section = (
            target_sec.lower() in other_sec.lower() or
            other_sec.lower() in target_sec.lower() or
            (target_sec and re.search(r"\b" + re.escape(target_sec.split()[0]) + r"\b", other_sec, re.IGNORECASE))
        )

        sim = compute_text_similarity(c_text, other_c.get("comment_text", ""))

        if is_same_section or sim >= 0.40:
            if other_org != current_org:
                if other_sent in ["Strongly Critical", "Concerned"]:
                    co_objectors.add(other_org)
                elif other_sent == "Supportive":
                    defenders.add(other_org)

    silent_orgs = [o for o in all_organisations if o not in co_objectors and o not in defenders and o != current_org]

    support_count = len(co_objectors) + (1 if current_org in all_organisations else 0)
    defense_count = len(defenders)
    silence_count = len(silent_orgs)

    support_rate_pct = round((support_count / total_orgs) * 100, 1)
    defense_rate_pct = round((defense_count / total_orgs) * 100, 1)
    silence_rate_pct = round((silence_count / total_orgs) * 100, 1)

    if silence_rate_pct >= 60.0:
        interpretation = (
            f"Tacit Acquiescence from Industry Majority: While {current_org}"
            + (f" and {', '.join(sorted(list(co_objectors))[:2])}" if co_objectors else "")
            + f" challenge this provision, {silence_rate_pct}% ({silence_count}/{total_orgs}) of participating organisations "
            f"voiced NO objection to {target_sec or 'this requirement'}. "
            f"In regulatory administration, silence from other affected industry sectors is evaluated as tacit acceptance or absence of operational friction."
        )
    elif support_rate_pct >= 40.0:
        interpretation = (
            f"Broad Cross-Sector Coalition of Concern: {support_count} out of {total_orgs} organisations ({support_rate_pct}%) "
            f"actively challenge {target_sec or 'this provision'} (including {', '.join(sorted(list(co_objectors))[:3])}). "
            f"This represents a major industry friction point requiring formal re-deliberation or transitional relief."
        )
    else:
        interpretation = (
            f"Sector-Specific Observation: Supported by {support_count} stakeholder(s), defended by {defense_count}, "
            f"while {silence_rate_pct}% remained neutral or silent. Drafters should evaluate whether targeted guidance can resolve the friction."
        )

    return {
        "target_clause": target_sec or "Consulted Provision",
        "current_organisation": current_org,
        "total_participating_organisations": total_orgs,
        "co_objectors": sorted(list(co_objectors)),
        "defenders": sorted(list(defenders)),
        "silent_organisations": sorted(silent_orgs),
        "support_count": support_count,
        "defense_count": defense_count,
        "silence_count": silence_count,
        "support_rate_pct": support_rate_pct,
        "defense_rate_pct": defense_rate_pct,
        "silence_rate_pct": silence_rate_pct,
        "regulatory_interpretation": interpretation,
    }


def compute_organisations_analysis(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Computes organisation-level profile:
    - Organisation Name & Category
    - Total comments
    - Net weighted sentiment score, section score, document score
    - Stance label
    - Direction of travel narrative (what the organisation is pushing for)
    - Importance and Comment Type breakdown
    - Top targeted sections
    - Key proposed amendments
    """
    org_map: Dict[str, List[Dict[str, Any]]] = {}
    for c in comments:
        name = (c.get("organisation_name") or c.get("stakeholder_name") or "Stakeholder").strip()
        org_map.setdefault(name, []).append(c)

    results: List[Dict[str, Any]] = []

    for name, c_list in org_map.items():
        total_c = len(c_list)
        category = c_list[0].get("stakeholder_category") or c_list[0].get("stakeholder_group") or "Industry"

        weighted_scores = [c.get("weighted_score", c.get("sentiment_score", 0.0)) for c in c_list]
        section_scores = [c.get("section_score", c.get("sentiment_score", 0.0)) for c in c_list]
        document_scores = [c.get("document_score", c.get("sentiment_score", 0.0)) for c in c_list]

        avg_weighted = round(sum(weighted_scores) / total_c, 2)
        avg_section = round(sum(section_scores) / total_c, 2)
        avg_document = round(sum(document_scores) / total_c, 2)

        if avg_weighted <= -0.4:
            stance = "Strongly Critical"
        elif avg_weighted < 0.0:
            stance = "Concerned / Conditional Support"
        elif avg_weighted < 0.4:
            stance = "Constructive Neutrality"
        else:
            stance = "Strongly Supportive"

        # Direction of travel vectors
        dir_counts: Dict[str, int] = {}
        for c in c_list:
            d = c.get("direction_of_travel") or extract_direction_of_travel(c.get("comment_text", ""), c.get("rationale", ""), c.get("proposed_text", ""))
            dir_counts[d] = dir_counts.get(d, 0) + 1

        top_directions = [d for d, _ in sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)]
        primary_dir = top_directions[0] if top_directions else "Regulatory Refinement"

        # Comprehensive scoring across all possible directions of travel (to visualize alignment and tensions)
        canonical_directions = [
            "Timeline Extension & Transitional Phasing",
            "Proportionality Relief & Scope Exemptions for Non-Complex Entities",
            "Flexibility via Non-Binding Guidance (AMC/GM) rather than Hard Rules",
            "Mitigation of Compliance Costs & Resourcing Burdens",
            "Enhancement of Risk Mitigation & Operational Safety Margins",
            "International Standardization & ICAO Harmonization",
            "Strengthening Reporter Confidentiality & Just Culture Protections",
            "Operational Simplicity & Single-Window Harmonization",
        ]

        dir_scores: Dict[str, float] = {}
        for d in canonical_directions:
            direct_c = [
                c for c in c_list
                if (c.get("direction_of_travel") or extract_direction_of_travel(c.get("comment_text", ""), c.get("rationale", ""), c.get("proposed_text", ""))) == d
            ]
            if direct_c:
                base = 75.0 + min(20.0, len(direct_c) * 5.0)
                if any(c.get("importance") in ["High", "Critical"] for c in direct_c):
                    base += 5.0
                dir_scores[d] = round(min(98.0, base), 1)
            else:
                kw_hits = 0
                for c in c_list:
                    comb = f"{c.get('comment_text', '')} {c.get('rationale', '')} {c.get('proposed_text', '')}".lower()
                    if d == "Timeline Extension & Transitional Phasing" and any(k in comb for k in ["timeline", "transition", "delay", "grace period", "months", "phased"]):
                        kw_hits += 1
                    elif d == "Proportionality Relief & Scope Exemptions for Non-Complex Entities" and any(k in comb for k in ["proportional", "small operator", "exemption", "sme", "non-complex"]):
                        kw_hits += 1
                    elif d == "Flexibility via Non-Binding Guidance (AMC/GM) rather than Hard Rules" and any(k in comb for k in ["amc", "guidance", "gm", "flexibility", "non-binding"]):
                        kw_hits += 1
                    elif d == "Mitigation of Compliance Costs & Resourcing Burdens" and any(k in comb for k in ["cost", "budget", "burden", "procurement", "fee", "financial"]):
                        kw_hits += 1
                    elif d == "Enhancement of Risk Mitigation & Operational Safety Margins" and any(k in comb for k in ["safety", "risk", "mandatory", "hazard", "oversight", "margin"]):
                        kw_hits += 1
                    elif d == "International Standardization & ICAO Harmonization" and any(k in comb for k in ["icao", "faa", "harmoniz", "bilateral", "global"]):
                        kw_hits += 1
                    elif d == "Strengthening Reporter Confidentiality & Just Culture Protections" and any(k in comb for k in ["confidential", "just culture", "identity", "anonym", "protection"]):
                        kw_hits += 1
                    elif d == "Operational Simplicity & Single-Window Harmonization" and any(k in comb for k in ["single window", "single portal", "unified", "simpl", "portal"]):
                        kw_hits += 1

                if kw_hits > 0:
                    dir_scores[d] = round(min(70.0, 42.0 + kw_hits * 10.0), 1)
                else:
                    # Inherent regulatory tension defaults
                    if d == "Enhancement of Risk Mitigation & Operational Safety Margins" and dir_scores.get("Mitigation of Compliance Costs & Resourcing Burdens", 0) > 75:
                        dir_scores[d] = 18.0
                    elif d == "Timeline Extension & Transitional Phasing" and any(w in category.lower() for w in ["authority", "regulator", "oversight"]):
                        dir_scores[d] = 20.0
                    else:
                        dir_scores[d] = 25.0

        # Types and Importance
        type_counts: Dict[str, int] = {}
        imp_counts: Dict[str, int] = {}
        sections_targeted: List[str] = []
        proposals: List[str] = []

        for c in c_list:
            t = c.get("comment_type") or "Observation"
            type_counts[t] = type_counts.get(t, 0) + 1

            imp = c.get("importance") or "Medium"
            imp_counts[imp] = imp_counts.get(imp, 0) + 1

            sec = c.get("chapter_section") or c.get("target_section") or ""
            if sec and sec not in sections_targeted:
                sections_targeted.append(sec)

            prop = c.get("proposed_text", "").strip()
            if prop and prop not in proposals and len(prop) > 5:
                proposals.append(f"{sec}: {prop[:120]}")

        # Narrative description of organisation's strategic intent
        if avg_weighted < -0.2:
            intent = (
                f"{name} ({category}) submitted {total_c} comment(s) with a net critical orientation ({avg_weighted:+0.2f}). "
                f"Their primary direction of travel is '{primary_dir}', concentrating on {', '.join(sections_targeted[:2])}. "
                f"They urge specific amendments to alleviate operational friction."
            )
        elif avg_weighted > 0.2:
            intent = (
                f"{name} ({category}) submitted {total_c} comment(s) strongly endorsing the proposed measures ({avg_weighted:+0.2f}). "
                f"Their direction of travel supports '{primary_dir}', confirming operational feasibility across {', '.join(sections_targeted[:2])}."
            )
        else:
            intent = (
                f"{name} ({category}) submitted {total_c} comment(s) engaging constructively with technical clarifications ({avg_weighted:+0.2f}). "
                f"Their primary vector focuses on '{primary_dir}' across {', '.join(sections_targeted[:2])}."
            )

        results.append({
            "organisation_name": name,
            "stakeholder_category": category,
            "total_comments": total_c,
            "average_weighted_score": avg_weighted,
            "average_section_score": avg_section,
            "average_document_score": avg_document,
            "stance": stance,
            "stance_summary": intent,
            "primary_direction_of_travel": primary_dir,
            "direction_of_travel": primary_dir,
            "direction_of_travel_summary": intent,
            "direction_scores": dir_scores,
            "comment_types_breakdown": type_counts,
            "importance_breakdown": imp_counts,
            "targeted_sections": sections_targeted,
            "key_proposals": proposals[:3],
        })

    results.sort(key=lambda x: (x["average_weighted_score"], -x["total_comments"]))
    return results


def enrich_feedback_comments(
    comments: List[Dict[str, Any]],
    document_sections: List[Dict[str, str]],
    whole_doc_overview: str = ""
) -> List[Dict[str, Any]]:
    """
    Applies themes, sentiment, 75%/25% dual-context weighting, direction of travel,
    validity assessment, section matching, and stakeholder silence accounting to all comments.
    """
    enriched: List[Dict[str, Any]] = []

    all_orgs = sorted(list(set(
        (c.get("organisation_name") or c.get("stakeholder_name") or "").strip()
        for c in comments
        if (c.get("organisation_name") or c.get("stakeholder_name"))
    )))

    for c in comments:
        c_text = c.get("comment_text", "")
        p_text = c.get("proposed_text", "")
        r_text = c.get("rationale") or c.get("rationale_and_changes", "")
        t_sec = c.get("chapter_section") or c.get("target_section", "")
        doc_title = c.get("document_title") or "Consultation Document"
        page = c.get("page")
        orig_text = c.get("original_text", "")
        comment_type = c.get("comment_type") or ("Change Request" if p_text else "Observation")
        importance = c.get("importance") or "Medium"
        org_name = c.get("organisation_name") or c.get("stakeholder_name") or "Stakeholder"
        cat = c.get("stakeholder_category") or c.get("stakeholder_group") or "Industry"
        af_cba = c.get("af_cba", "")
        resp = c.get("response_to_comment", "")
        overall_id = c.get("overall_id") or c.get("comment_id")

        themes = analyze_comment_themes(c_text, p_text, r_text)
        sentiment_label, base_sentiment_score = analyze_comment_sentiment(c_text, r_text)
        validity_label, validity_rationale = assess_comment_validity(c_text, p_text, r_text, t_sec)

        matched_title, matched_snippet = match_comment_to_document_section(t_sec, c_text, document_sections)

        # 75% Specific Section / 25% Whole Document Dual Context Evaluation
        sec_score, doc_score, weighted_score, direction_of_travel, dual_summary = evaluate_comment_dual_context(
            text=c_text,
            proposed_text=p_text,
            rationale=r_text,
            target_section=t_sec,
            importance=importance,
            comment_type=comment_type,
            section_content=matched_snippet or "",
            whole_doc_overview=whole_doc_overview or ""
        )

        comment_record = {
            "comment_id": c.get("comment_id"),
            "document_title": doc_title,
            "chapter_section": t_sec,
            "page": page,
            "original_text": orig_text,
            "comment_text": c_text,
            "comment_type": comment_type,
            "importance": importance,
            "proposed_text": p_text,
            "stakeholder_category": cat,
            "organisation_name": org_name,
            "af_cba": af_cba,
            "response_to_comment": resp,
            "rationale_and_changes": r_text,
            "overall_id": overall_id,
            "stakeholder_name": org_name,
            "stakeholder_group": cat,
            "target_section": t_sec,
            "rationale": r_text,
            "themes": themes,
            "sentiment": sentiment_label,
            "sentiment_score": base_sentiment_score,
            "section_score": sec_score,
            "document_score": doc_score,
            "weighted_score": weighted_score,
            "direction_of_travel": direction_of_travel,
            "dual_evaluation_summary": dual_summary,
            "validity": validity_label,
            "validity_rationale": validity_rationale,
            "matched_section_title": matched_title,
            "matched_section_content": matched_snippet,
            "human_review_status": c.get("human_review_status", "Pending Review"),
            "human_notes": c.get("human_notes", ""),
            "ai_assistance_notes": c.get("ai_assistance_notes"),
        }

        # Stakeholder support & silence accounting
        support_network = analyze_critical_comment_support_and_silence(comment_record, comments, all_orgs)
        comment_record["support_network"] = support_network

        enriched.append(comment_record)

    return enriched


def compute_consultation_metrics(comments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes comprehensive aggregated metrics across all feedback comments."""
    total = len(comments)
    if total == 0:
        return {}

    # Sentiment distribution
    sentiment_counts: Dict[str, int] = {}
    weighted_scores = []
    section_scores = []
    document_scores = []

    for c in comments:
        s = c.get("sentiment", "Neutral / Inquiring")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
        weighted_scores.append(c.get("weighted_score", c.get("sentiment_score", 0.0)))
        section_scores.append(c.get("section_score", c.get("sentiment_score", 0.0)))
        document_scores.append(c.get("document_score", c.get("sentiment_score", 0.0)))

    # Stakeholder groups
    group_counts: Dict[str, int] = {}
    for c in comments:
        g = c.get("stakeholder_group", "Other")
        group_counts[g] = group_counts.get(g, 0) + 1

    # Common themes
    theme_counts: Dict[str, int] = {}
    for c in comments:
        for t in c.get("themes", []):
            theme_counts[t] = theme_counts.get(t, 0) + 1

    # Direction of travel distribution
    direction_counts: Dict[str, int] = {}
    for c in comments:
        d = c.get("direction_of_travel")
        if d:
            direction_counts[d] = direction_counts.get(d, 0) + 1

    # Validity distribution
    validity_counts: Dict[str, int] = {}
    for c in comments:
        v = c.get("validity", "Substantive Technical Concern")
        validity_counts[v] = validity_counts.get(v, 0) + 1

    # Review status distribution
    status_counts: Dict[str, int] = {}
    for c in comments:
        st = c.get("human_review_status", "Pending Review")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Actionable proposal rate
    actionable_count = validity_counts.get("Actionable Proposal", 0)
    actionable_pct = round((actionable_count / total) * 100, 1)

    # Organisation analysis
    org_analysis = compute_organisations_analysis(comments)

    return {
        "total_comments": total,
        "sentiment_distribution": sentiment_counts,
        "average_weighted_score": round(sum(weighted_scores) / total, 2) if weighted_scores else 0.0,
        "average_section_score": round(sum(section_scores) / total, 2) if section_scores else 0.0,
        "average_document_score": round(sum(document_scores) / total, 2) if document_scores else 0.0,
        "stakeholder_groups": group_counts,
        "theme_distribution": theme_counts,
        "direction_of_travel_distribution": direction_counts,
        "validity_distribution": validity_counts,
        "review_status_distribution": status_counts,
        "actionable_proposal_pct": actionable_pct,
        "organisations_count": len(org_analysis),
        "organisations_analysis": org_analysis,
    }


def extract_relevant_snippet(section_content: str, target_clause: str = "", comment_text: str = "") -> str:
    """Extracts the most relevant paragraph or clause from section content."""
    if not section_content:
        return "No specific excerpt found in consulted document draft."

    paras = [p.strip() for p in section_content.split("\n\n") if p.strip()]
    if not paras:
        paras = [p.strip() for p in section_content.splitlines() if p.strip()]

    # If target clause contains a subclause number like (2) or (3) or 2. or 3.
    sub_m = re.search(r"\((\d+)\)|paragraph\s*(\d+)|\b(\d+)\.", (target_clause or "").lower())
    if sub_m:
        num = sub_m.group(1) or sub_m.group(2) or sub_m.group(3)
        for p in paras:
            if re.search(rf"(?:^|\b)(?:{num}\.|\({num}\))\s*", p):
                return p[:700]

    # Keyword search across paragraphs
    words = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", comment_text or "") if w.lower() not in ["shall", "should", "operator", "aerodrome", "airport", "article"]]
    if words:
        best_p = None
        best_cnt = 0
        for p in paras:
            p_lower = p.lower()
            cnt = sum(1 for w in words[:12] if w in p_lower)
            if cnt > best_cnt:
                best_cnt = cnt
                best_p = p
        if best_p and best_cnt > 0:
            return best_p[:700]

    return paras[0][:700] if paras else section_content[:700]


def synthesize_comment_vs_text(
    comment: Dict[str, Any],
    section_content: str = "",
    session_title: str = ""
) -> Dict[str, Any]:
    """
    Synthesizes a single stakeholder feedback comment and concerns vs the consulted text.
    Strictly data-driven with no hardcoded domain assumptions.
    """
    c_text = comment.get("comment_text", "").strip()
    p_text = comment.get("proposed_text", "").strip()
    r_text = comment.get("rationale", "").strip()
    t_sec = comment.get("target_section", "").strip() or "Consulted Text"
    stakeholder = comment.get("stakeholder_name", "").strip() or "Stakeholder"
    group = comment.get("stakeholder_group", "").strip() or "Industry"
    sentiment = comment.get("sentiment", "Neutral / Inquiring")
    themes = comment.get("themes", [])

    text_excerpt = extract_relevant_snippet(section_content or comment.get("matched_section_content", ""), t_sec, c_text)

    # Core stakeholder concern grounded in actual text
    if r_text:
        concern_summary = f"{stakeholder} ({group}) observes: \"{c_text}\". Submitter rationale: \"{r_text}\""
    else:
        concern_summary = f"{stakeholder} ({group}) submits {sentiment.lower()} feedback: \"{c_text}\""

    # Dynamic divergence analysis
    if sentiment in ["Strongly Critical", "Concerned"]:
        if p_text:
            divergence = (
                f"{stakeholder} challenges the drafted stipulation, stating: \"{c_text[:180]}\". "
                f"They urge amendment to reconcile operational viability with regulatory requirements, proposing: '{p_text[:140]}'."
            )
        elif r_text:
            divergence = (
                f"{stakeholder} points out operational or technical friction with the consulted text: \"{r_text[:180]}\", "
                f"arguing that the current formulation requires revision."
            )
        else:
            divergence = (
                f"{stakeholder} expresses substantive concerns regarding the consulted text: \"{c_text[:200]}\", "
                f"cautioning against operational bottlenecks or supervisory difficulties."
            )
    elif sentiment == "Supportive":
        divergence = f"{stakeholder} endorses the consulted text, noting: \"{c_text[:180]}\" and confirming operational alignment."
    else:
        divergence = f"{stakeholder} seeks technical or procedural clarification regarding: \"{c_text[:180]}\"."

    # Dynamic operational & safety impact assessment derived from themes and comment content
    theme_str = " ".join(themes).lower()
    c_lower = c_text.lower()
    if any(k in theme_str or k in c_lower for k in ["safety", "hazard", "risk", "oversight"]):
        impact = f"Safety & Oversight: Directly impacts risk management protocols, hazard mitigation, and supervisory oversight for {group}."
    elif any(k in theme_str or k in c_lower for k in ["cost", "economic", "financial", "budget", "resource"]):
        impact = f"Economic & Resourcing: Implicates capital expenditure, staffing workload, or software/infrastructure investments for {stakeholder}."
    elif any(k in theme_str or k in c_lower for k in ["timeline", "phasing", "transition", "deadline", "entry into force", "grace"]):
        impact = f"Implementation Feasibility: Affects the transition schedule, deployment milestones, and operational readiness of {group}."
    elif any(k in theme_str or k in c_lower for k in ["cyber", "data", "confidentiality", "security"]):
        impact = f"Information & Data Governance: Impacts secure data exchange, system interoperability, and confidential information handling."
    elif any(k in theme_str or k in c_lower for k in ["harmonization", "icao", "international", "standard"]):
        impact = f"International Alignment: Affects regulatory consistency with international baselines (e.g. ICAO) and cross-border operations."
    elif any(k in theme_str or k in c_lower for k in ["proportional", "small", "sme", "scale"]):
        impact = f"Proportionality: Determines whether the requirement places an undue administrative or technical burden on smaller or specialized operators."
    else:
        impact = f"Operational Feasibility: Affects day-to-day procedural execution and legal compliance obligations for {group}."

    # Dynamic drafting remedies
    if p_text:
        remedy = [
            f"Drafting Option A (Stakeholder Proposal): Evaluate incorporating stakeholder wording: '{p_text}'",
            f"Drafting Option B (Guidance Material): Retain rule text but issue Acceptable Means of Compliance (AMC) / Guidance Material (GM) addressing {stakeholder}'s rationale.",
            "Drafting Option C (Maintain Baseline): Retain draft wording if the requested change weakens essential regulatory safeguards."
        ]
    else:
        remedy = [
            f"Drafting Option A: Refine provision drafting in {t_sec} to address the points raised by {stakeholder}.",
            f"Drafting Option B: Issue explanatory Guidance Material (GM) specifying acceptable compliance methods.",
            "Drafting Option C: Retain draft formulation if existing text is determined to provide adequate legal clarity."
        ]

    return {
        "comment_id": comment.get("comment_id"),
        "stakeholder_name": stakeholder,
        "stakeholder_group": group,
        "target_section": t_sec,
        "matched_section_title": comment.get("matched_section_title") or t_sec,
        "sentiment": sentiment,
        "sentiment_score": comment.get("sentiment_score", 0.0),
        "section_score": comment.get("section_score", comment.get("sentiment_score", 0.0)),
        "document_score": comment.get("document_score", comment.get("sentiment_score", 0.0)),
        "weighted_score": comment.get("weighted_score", comment.get("sentiment_score", 0.0)),
        "direction_of_travel": comment.get("direction_of_travel", ""),
        "dual_evaluation_summary": comment.get("dual_evaluation_summary", ""),
        "support_network": comment.get("support_network", {}),
        "validity": comment.get("validity", "Substantive Technical Concern"),
        "themes": themes,
        "comment_text": c_text,
        "proposed_text": p_text,
        "rationale": r_text,
        "text_stipulation": text_excerpt,
        "stakeholder_concern": concern_summary,
        "divergence_analysis": divergence,
        "operational_and_safety_impact": impact,
        "drafting_options": remedy,
    }


def synthesize_by_stakeholder_type(
    group_name: str,
    comments: List[Dict[str, Any]],
    sections: List[Dict[str, str]],
    session_title: str = ""
) -> Dict[str, Any]:
    """
    Synthesizes feedback comments for a specific stakeholder group vs consulted text.
    100% data-driven based on actual comments submitted.
    """
    group_cmts = [c for c in comments if c.get("stakeholder_group") == group_name]
    count = len(group_cmts)
    if count == 0:
        return {
            "stakeholder_group": group_name,
            "comment_count": 0,
            "stakeholders": [],
            "average_sentiment_score": 0.0,
            "sentiment_distribution": {},
            "primary_targeted_sections": [],
            "dominant_themes": [],
            "collective_stance_summary": f"No comments recorded from {group_name}.",
            "core_concerns_vs_consulted_text": [],
            "cross_sector_alignment_and_conflicts": "None",
            "rulemaker_deliberation_advice": "No action required."
        }

    stakeholders = sorted(list(set(c.get("stakeholder_name", "") for c in group_cmts if c.get("stakeholder_name"))))
    avg_score = round(sum(c.get("sentiment_score", 0.0) for c in group_cmts) / count, 2)

    sent_dist: Dict[str, int] = {}
    sec_counts: Dict[str, int] = {}
    theme_counts: Dict[str, int] = {}

    for c in group_cmts:
        s = c.get("sentiment", "Neutral / Inquiring")
        sent_dist[s] = sent_dist.get(s, 0) + 1
        t_sec = c.get("matched_section_title") or c.get("target_section") or "General"
        sec_counts[t_sec] = sec_counts.get(t_sec, 0) + 1
        for t in c.get("themes", []):
            theme_counts[t] = theme_counts.get(t, 0) + 1

    top_sections = [s for s, _ in sorted(sec_counts.items(), key=lambda x: x[1], reverse=True)[:4]]
    top_themes = [t for t, _ in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:4]]

    stk_str = ", ".join(stakeholders[:5]) + (f" (+{len(stakeholders)-5} more)" if len(stakeholders) > 5 else "")

    # Collective stance narrative grounded in actual data
    if avg_score < -0.3:
        stance_summary = (
            f"{group_name} ({stk_str}) submitted {count} feedback comments with a predominantly critical stance (net sentiment {avg_score:+0.2f}). "
            f"Their primary focus areas are {', '.join(top_themes[:2]) if top_themes else 'the draft provisions'}, concentrating on {', '.join(top_sections[:2])}. "
            f"They argue that the drafted obligations pose substantial technical, operational, or economic friction."
        )
    elif avg_score < 0.2:
        stance_summary = (
            f"{group_name} ({stk_str}) submitted {count} feedback comments taking a balanced, inquiring, or conditionally supportive posture (net sentiment {avg_score:+0.2f}). "
            f"While engaging constructively with the rulemaking objectives, they request key amendments and practical clarifications on {', '.join(top_sections[:2])}."
        )
    else:
        stance_summary = (
            f"{group_name} ({stk_str}) submitted {count} feedback comments strongly supporting the proposed regulation (net sentiment {avg_score:+0.2f}). "
            f"They endorse the provisions across {', '.join(top_sections[:2])}, viewing them as beneficial for regulatory standardization and operational safety."
        )

    # Core concerns vs consulted text points
    concerns: List[Dict[str, str]] = []
    for c in group_cmts:
        concerns.append({
            "stakeholder": c.get("stakeholder_name", "Submitter"),
            "target": c.get("target_section", "Draft Text"),
            "concern": c.get("comment_text", ""),
            "proposed_change": c.get("proposed_text", "") or "No text proposed",
            "stance": c.get("sentiment", "Neutral")
        })

    # DYNAMIC cross-sector tension and alignment detection:
    # Look for other stakeholder groups commenting on the SAME target sections or themes
    tensions_list: List[str] = []
    other_cmts = [c for c in comments if c.get("stakeholder_group") != group_name]

    for sec in top_sections[:3]:
        sec_other = [c for c in other_cmts if (c.get("matched_section_title") == sec or c.get("target_section") == sec)]
        if sec_other:
            other_groups = sorted(list(set(c.get("stakeholder_group", "") for c in sec_other if c.get("stakeholder_group"))))
            other_avg_score = sum(c.get("sentiment_score", 0.0) for c in sec_other) / len(sec_other)
            this_sec_cmts = [c for c in group_cmts if (c.get("matched_section_title") == sec or c.get("target_section") == sec)]
            this_sec_score = sum(c.get("sentiment_score", 0.0) for c in this_sec_cmts) / len(this_sec_cmts)

            if (this_sec_score < -0.2 and other_avg_score > 0.2) or (this_sec_score > 0.2 and other_avg_score < -0.2):
                tensions_list.append(
                    f"Divergence on '{sec}': {group_name} expressed opposing views compared to {', '.join(other_groups[:2])} "
                    f"(divergent sentiment scores: {this_sec_score:+0.2f} vs {other_avg_score:+0.2f})."
                )
            elif abs(this_sec_score - other_avg_score) < 0.3:
                tensions_list.append(
                    f"Shared interest on '{sec}': Both {group_name} and {', '.join(other_groups[:2])} submitted concurrent observations."
                )

    if tensions_list:
        tension = " ".join(tensions_list[:3])
    else:
        tension = f"{group_name}'s feedback focuses on sector-specific operational aspects across {', '.join(top_sections[:2])} without direct adversarial opposition from other groups."

    # Deliberation advice dynamically based on actionable proposals
    actionable_in_group = [c for c in group_cmts if c.get("proposed_text")]
    if actionable_in_group:
        advice = (
            f"{group_name} submitted {len(actionable_in_group)} concrete text amendments. "
            f"Rulemaker action: Review proposed wording on {', '.join(top_sections[:2])} to determine whether adjustments can be incorporated "
            f"into the main text or accommodated through transitional provisions and Acceptable Means of Compliance (AMC)."
        )
    else:
        advice = (
            f"{group_name} primarily submitted clarification and policy observations. "
            f"Rulemaker action: Evaluate whether the clarifications requested on {', '.join(top_sections[:2])} can be resolved through "
            f"informative Guidance Material (GM) without amending the primary regulatory requirements."
        )

    return {
        "stakeholder_group": group_name,
        "comment_count": count,
        "stakeholders": stakeholders,
        "average_sentiment_score": avg_score,
        "sentiment_distribution": sent_dist,
        "primary_targeted_sections": top_sections,
        "dominant_themes": top_themes,
        "collective_stance_summary": stance_summary,
        "core_concerns_vs_consulted_text": concerns,
        "cross_sector_alignment_and_conflicts": tension,
        "rulemaker_deliberation_advice": advice,
    }


def synthesize_by_category(
    category_name: str,
    comments: List[Dict[str, Any]],
    sections: List[Dict[str, str]],
    session_title: str = ""
) -> Dict[str, Any]:
    """
    Synthesizes feedback comments across all stakeholders within a specific thematic category vs consulted text.
    100% data-driven based on actual comments.
    """
    cat_cmts = [c for c in comments if category_name in c.get("themes", [])]
    count = len(cat_cmts)
    if count == 0:
        return {
            "category_name": category_name,
            "comment_count": 0,
            "average_sentiment_score": 0.0,
            "sentiment_distribution": {},
            "participating_groups": [],
            "implicated_sections": [],
            "thematic_conflict_summary": f"No comments tagged under '{category_name}'.",
            "stakeholder_positions": [],
            "consulted_text_evaluation": "Provision uncontentious in this category.",
            "policy_tradeoffs_and_remedies": []
        }

    avg_score = round(sum(c.get("sentiment_score", 0.0) for c in cat_cmts) / count, 2)
    sent_dist: Dict[str, int] = {}
    groups_involved = sorted(list(set(c.get("stakeholder_group", "Other") for c in cat_cmts if c.get("stakeholder_group"))))
    sec_involved = sorted(list(set(c.get("matched_section_title") or c.get("target_section") or "General" for c in cat_cmts if c.get("target_section") or c.get("matched_section_title"))))

    for c in cat_cmts:
        s = c.get("sentiment", "Neutral / Inquiring")
        sent_dist[s] = sent_dist.get(s, 0) + 1

    crit_cmts = [c for c in cat_cmts if c.get("sentiment") in ["Strongly Critical", "Concerned"]]
    supp_cmts = [c for c in cat_cmts if c.get("sentiment") == "Supportive"]
    neut_cmts = [c for c in cat_cmts if c.get("sentiment") == "Neutral / Inquiring"]

    # Dynamic thematic conflict synthesis
    if crit_cmts:
        sample_concerns = [f"{c.get('stakeholder_name')}: \"{c.get('comment_text', '')[:110]}\"" for c in crit_cmts[:2]]
        conflict = (
            f"Thematic friction in '{category_name}': {len(crit_cmts)} out of {count} comments express critical or concerned feedback "
            f"across {len(groups_involved)} stakeholder groups ({', '.join(groups_involved[:3])}). "
            f"Key points raised: " + "; ".join(sample_concerns) + ". "
            f"Primary provisions affected: {', '.join(sec_involved[:3])}."
        )
    elif supp_cmts:
        sample_endorsements = [f"{c.get('stakeholder_name')}: \"{c.get('comment_text', '')[:110]}\"" for c in supp_cmts[:2]]
        conflict = (
            f"Broad consensus in '{category_name}': Stakeholders across {', '.join(groups_involved[:3])} endorse the consulted text. "
            f"Positive feedback highlights: " + "; ".join(sample_endorsements) + "."
        )
    else:
        sample_inquiries = [f"{c.get('stakeholder_name')}: \"{c.get('comment_text', '')[:110]}\"" for c in neut_cmts[:2]]
        conflict = (
            f"Technical inquiries and clarification requests in '{category_name}': {count} comments submitted across {', '.join(groups_involved[:3])}. "
            f"Stakeholders focus on operational clarity: " + "; ".join(sample_inquiries) + "."
        )

    # Dynamic remedies based on actual proposed texts
    remedies: List[str] = []
    actionable_proposals = [c for c in cat_cmts if c.get("proposed_text")]
    for p in actionable_proposals[:3]:
        stk = p.get("stakeholder_name", "Stakeholder")
        sec = p.get("target_section", "Provision")
        prop = p.get("proposed_text", "")[:130]
        remedies.append(f"Consider proposal from {stk} on {sec}: \"{prop}\"")

    if not remedies:
        if crit_cmts:
            remedies.append(f"Review core requirements in {', '.join(sec_involved[:2])} to evaluate whether compliance constraints require transitional phasing.")
            remedies.append(f"Provide Acceptable Means of Compliance (AMC) specifying acceptable alternative methods.")
        else:
            remedies.append(f"Maintain regulatory baseline in {', '.join(sec_involved[:2])} while issuing explanatory Guidance Material (GM) on key terms.")

    # Stakeholder positions
    positions = []
    for c in cat_cmts:
        positions.append({
            "stakeholder": c.get("stakeholder_name"),
            "group": c.get("stakeholder_group"),
            "target_section": c.get("target_section"),
            "argument": c.get("comment_text"),
            "proposal": c.get("proposed_text") or "No drafting text proposed",
            "sentiment": c.get("sentiment")
        })

    return {
        "category_name": category_name,
        "comment_count": count,
        "average_sentiment_score": avg_score,
        "sentiment_distribution": sent_dist,
        "participating_groups": groups_involved,
        "implicated_sections": sec_involved,
        "thematic_conflict_summary": conflict,
        "stakeholder_positions": positions,
        "consulted_text_evaluation": f"Affects provisions: {', '.join(sec_involved[:4])}. Evaluation based on {count} stakeholder submission(s).",
        "policy_tradeoffs_and_remedies": remedies,
    }


def synthesize_by_section(
    section_title: str,
    section_content: str,
    comments: List[Dict[str, Any]],
    session_title: str = ""
) -> Dict[str, Any]:
    """
    Synthesizes feedback comments targeting a specific section of the consulted document.
    """
    # Filter comments matching this section
    sec_cmts = [c for c in comments if c.get("matched_section_title") == section_title or section_title.lower() in (c.get("target_section") or "").lower()]
    count = len(sec_cmts)
    if count == 0:
        return {
            "section_title": section_title,
            "section_excerpt": section_content[:600],
            "comment_count": 0,
            "average_sentiment_score": 0.0,
            "sentiment_distribution": {},
            "commenting_groups": [],
            "synthesized_feedback_vs_text": f"No stakeholder comments targeted '{section_title}'. Provision appears widely accepted.",
            "contentious_provisions": [],
            "supported_provisions": ["Entire section accepted without reported friction."],
            "suggested_amendments": [],
            "deliberation_guidance": "Retain draft text as published."
        }

    avg_score = round(sum(c.get("sentiment_score", 0.0) for c in sec_cmts) / count, 2)
    sent_dist: Dict[str, int] = {}
    groups_involved = sorted(list(set(c.get("stakeholder_group", "Other") for c in sec_cmts if c.get("stakeholder_group"))))

    for c in sec_cmts:
        s = c.get("sentiment", "Neutral / Inquiring")
        sent_dist[s] = sent_dist.get(s, 0) + 1

    contentious: List[str] = []
    supported: List[str] = []
    amendments: List[Dict[str, str]] = []

    for c in sec_cmts:
        t_sec = c.get("target_section", section_title)
        st_name = c.get("stakeholder_name", "Submitter")
        c_text = c.get("comment_text", "")
        p_text = c.get("proposed_text", "")

        if c.get("sentiment") in ["Strongly Critical", "Concerned"]:
            contentious.append(f"{t_sec} ({st_name}): {c_text}")
        elif c.get("sentiment") == "Supportive":
            supported.append(f"{t_sec} ({st_name}): {c_text}")

        if p_text:
            amendments.append({
                "stakeholder": st_name,
                "target_clause": t_sec,
                "proposed_text": p_text,
                "rationale": c.get("rationale") or "Clarify and improve operational feasibility."
            })

    # Synthesized narrative
    synth_narrative = (
        f"Section '{section_title}' attracted {count} stakeholder feedback comments across {len(groups_involved)} sectors "
        f"({', '.join(groups_involved)}). Net sentiment stands at {avg_score:+0.2f}."
    )

    if contentious:
        guidance = f"Re-deliberation recommended: Stakeholders express substantive objections on {len(contentious)} point(s). Review proposed amendments and consider phased compliance or GM guidance."
    else:
        guidance = "Stakeholders generally support this section. Minor editorial or clarification amendments may be considered."

    return {
        "section_title": section_title,
        "section_excerpt": section_content[:800],
        "comment_count": count,
        "average_sentiment_score": avg_score,
        "sentiment_distribution": sent_dist,
        "commenting_groups": groups_involved,
        "synthesized_feedback_vs_text": synth_narrative,
        "contentious_provisions": contentious,
        "supported_provisions": supported or ["General regulatory objective accepted."],
        "suggested_amendments": amendments,
        "deliberation_guidance": guidance,
    }


def synthesize_overall_sentiment_and_consultation(
    session_title: str,
    session_description: str,
    comments: List[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Computes an executive-level General Assessment of Stakeholder Sentiment Overall and
    macro synthesis of comments and concerns vs the consulted document text.
    Strictly data-driven with no hardcoded sample datasets or assumptions.
    """
    total = len(comments)
    if total == 0:
        return {
            "overall_sentiment_label": "No Feedback Submitted",
            "overall_sentiment_score": 0.0,
            "total_comments": 0,
            "total_stakeholders": 0,
            "sentiment_breakdown_pct": {},
            "actionable_rate": 0.0,
            "executive_summary": "No feedback comments available to analyze.",
            "top_friction_zones": [],
            "areas_of_broad_consensus": [],
            "stakeholder_coalition_dynamics": [],
            "rulemaker_action_roadmap": []
        }

    sent_dist = metrics.get("sentiment_distribution", {})
    scores = [c.get("sentiment_score", 0.0) for c in comments]
    overall_score = round(sum(scores) / total, 2)

    crit_cnt = sent_dist.get("Strongly Critical", 0)
    conc_cnt = sent_dist.get("Concerned", 0)
    neut_cnt = sent_dist.get("Neutral / Inquiring", 0)
    supp_cnt = sent_dist.get("Supportive", 0)

    pct_crit = round((crit_cnt / total) * 100, 1)
    pct_conc = round((conc_cnt / total) * 100, 1)
    pct_neut = round((neut_cnt / total) * 100, 1)
    pct_supp = round((supp_cnt / total) * 100, 1)

    # Label
    if overall_score <= -0.4:
        overall_label = "Strong Industry Resistance & Critical Objections"
    elif overall_score < 0.0:
        overall_label = "Cautiously Concerned / Conditional Support with Implementation Friction"
    elif overall_score < 0.4:
        overall_label = "Constructive Neutrality / Qualified Endorsement"
    else:
        overall_label = "Broad Consensus & Strong Stakeholder Support"

    stakeholders = sorted(list(set(c.get("stakeholder_name", "") for c in comments if c.get("stakeholder_name"))))
    stk_groups = metrics.get("stakeholder_groups", {})
    actionable_count = metrics.get("validity_distribution", {}).get("Actionable Proposal", 0)
    actionable_rate = round((actionable_count / total) * 100, 1)

    # 1. Top themes analysis for executive summary
    theme_metrics = metrics.get("theme_distribution", {})
    top_themes_overall = sorted(theme_metrics.items(), key=lambda x: x[1], reverse=True)

    # Critical themes
    crit_cmts = [c for c in comments if c.get("sentiment") in ["Strongly Critical", "Concerned"]]
    crit_theme_counts: Dict[str, int] = {}
    for c in crit_cmts:
        for t in c.get("themes", []):
            crit_theme_counts[t] = crit_theme_counts.get(t, 0) + 1
    top_crit_themes = [t for t, _ in sorted(crit_theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]]

    # Supportive themes
    supp_cmts = [c for c in comments if c.get("sentiment") == "Supportive"]
    supp_theme_counts: Dict[str, int] = {}
    for c in supp_cmts:
        for t in c.get("themes", []):
            supp_theme_counts[t] = supp_theme_counts.get(t, 0) + 1
    top_supp_themes = [t for t, _ in sorted(supp_theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]]

    # Dynamic Executive Narrative
    exec_summary_lines = [
        f"Public consultation on '{session_title}' closed with {total} feedback comments submitted by {len(stakeholders)} distinct "
        f"stakeholders across {len(stk_groups)} industry categories.\n",
        f"The general assessment of stakeholder sentiment reveals a climate of {overall_label.lower()} (net sentiment score: {overall_score:+0.2f}). "
        f"Overall, {pct_crit + pct_conc}% of comments express critical or concerned observations, {pct_supp}% provide explicit endorsement, "
        f"and {pct_neut}% raise technical questions or clarification requests. "
        f"The actionable proposal rate stands at {actionable_rate}%, demonstrating high technical engagement from the regulated community.\n"
    ]

    if top_crit_themes:
        exec_summary_lines.append(
            f"The primary regulatory friction zones center on: {', '.join(top_crit_themes)}. "
            f"Submissions highlight operational feasibility challenges, scheduling bottlenecks, or resourcing constraints regarding these provisions."
        )
    if top_supp_themes:
        exec_summary_lines.append(
            f"In contrast, stakeholders express the highest degree of support regarding: {', '.join(top_supp_themes)}."
        )

    exec_summary_lines.append(
        f"Rulemaker deliberation should prioritize addressing the specific drafting modifications proposed on the contested sections, "
        f"reconciling baseline regulatory intent with practical operational considerations."
    )
    exec_summary = "\n\n".join(exec_summary_lines)

    # 2. DYNAMIC Top Friction Zones
    # Group critical comments by target section or theme
    sec_crit_map: Dict[str, List[Dict[str, Any]]] = {}
    for c in crit_cmts:
        sec_key = c.get("matched_section_title") or c.get("target_section") or "General Provisions"
        sec_crit_map.setdefault(sec_key, []).append(c)

    top_friction = []
    sorted_friction_secs = sorted(sec_crit_map.items(), key=lambda x: len(x[1]), reverse=True)

    for sec_title, c_list in sorted_friction_secs[:4]:
        c_groups = sorted(list(set(c.get("stakeholder_group", "Industry") for c in c_list if c.get("stakeholder_group"))))
        distinct_articles = sorted(list(set(c.get("target_section", sec_title) for c in c_list if c.get("target_section"))))

        # Pick the most descriptive comment/rationale
        descriptive_c = next((c for c in c_list if len(c.get("rationale", "")) > 20), None)
        if not descriptive_c:
            descriptive_c = next((c for c in c_list if len(c.get("comment_text", "")) > 30), c_list[0])
            issue_text = descriptive_c.get("comment_text", "")[:180]
        else:
            issue_text = f"{descriptive_c.get('comment_text', '')[:100]} - Submitter notes: '{descriptive_c.get('rationale', '')[:100]}'"

        # Primary theme of this friction cluster
        cluster_themes: Dict[str, int] = {}
        for c in c_list:
            for t in c.get("themes", []):
                cluster_themes[t] = cluster_themes.get(t, 0) + 1
        top_cl_theme = sorted(cluster_themes.items(), key=lambda x: x[1], reverse=True)
        topic_name = top_cl_theme[0][0] if top_cl_theme else sec_title

        top_friction.append({
            "topic": f"{topic_name} ({sec_title})",
            "affected_articles": ", ".join(distinct_articles[:3]),
            "contesting_groups": c_groups,
            "core_issue": issue_text
        })

    if not top_friction and crit_cmts:
        for th, cnt in sorted(crit_theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            th_cmts = [c for c in crit_cmts if th in c.get("themes", [])]
            th_groups = sorted(list(set(c.get("stakeholder_group", "") for c in th_cmts if c.get("stakeholder_group"))))
            top_friction.append({
                "topic": th,
                "affected_articles": ", ".join(set(c.get("target_section", "General") for c in th_cmts[:3])),
                "contesting_groups": th_groups,
                "core_issue": th_cmts[0].get("comment_text", "")[:180] if th_cmts else "Operational and compliance friction reported."
            })

    # 3. DYNAMIC Consensus Areas
    consensus = []
    sec_supp_map: Dict[str, List[Dict[str, Any]]] = {}
    for c in supp_cmts:
        sec_key = c.get("matched_section_title") or c.get("target_section") or "General Requirements"
        sec_supp_map.setdefault(sec_key, []).append(c)

    sorted_sec_supp_map = sorted(sec_supp_map.items(), key=lambda x: len(x[1]), reverse=True)[:3]
    for sec_title, c_list in sorted_sec_supp_map:
        supporters = sorted(list(set(c.get("stakeholder_name", "") for c in c_list if c.get("stakeholder_name"))))
        stk_repr = ", ".join(supporters[:3])
        rep_c = c_list[0].get("comment_text", "")[:120]
        consensus.append(
            f"Support for '{sec_title}': Endorsed by {stk_repr}. Key feedback: \"{rep_c}\""
        )

    if not consensus and supp_cmts:
        for th, _ in sorted(supp_theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            th_cmts = [c for c in supp_cmts if th in c.get("themes", [])]
            th_stk = ", ".join(set(c.get("stakeholder_name", "") for c in th_cmts[:3]))
            consensus.append(f"Broad industry alignment on '{th}': Welcomed by {th_stk}.")

    if not consensus:
        consensus.append(f"General engagement: {total} feedback submissions provide constructive review of '{session_title}' without fundamental challenge to the statutory mandate.")

    # 4. DYNAMIC Stakeholder Coalition Dynamics
    coalitions = []
    for grp_name, grp_cnt in sorted(stk_groups.items(), key=lambda x: x[1], reverse=True):
        g_cmts = [c for c in comments if c.get("stakeholder_group") == grp_name]
        if not g_cmts:
            continue
        g_avg = sum(c.get("sentiment_score", 0.0) for c in g_cmts) / len(g_cmts)
        g_theme_cnt: Dict[str, int] = {}
        for c in g_cmts:
            for t in c.get("themes", []):
                g_theme_cnt[t] = g_theme_cnt.get(t, 0) + 1
        g_top_th = [t for t, _ in sorted(g_theme_cnt.items(), key=lambda x: x[1], reverse=True)[:2]]
        g_top_sec = sorted(list(set(c.get("target_section", "") for c in g_cmts if c.get("target_section"))))[:2]

        if g_avg < -0.2:
            stance_desc = f"Critical stance ({grp_cnt} comments, net sentiment {g_avg:+0.2f}); primary concerns on {', '.join(g_top_th or ['draft rules'])}."
        elif g_avg > 0.2:
            stance_desc = f"Supportive posture ({grp_cnt} comments, net sentiment {g_avg:+0.2f}); endorses regulatory objectives across {', '.join(g_top_sec or ['draft text'])}."
        else:
            stance_desc = f"Technical inquiry & constructive engagement ({grp_cnt} comments, net sentiment {g_avg:+0.2f}); seeks clarifications on {', '.join(g_top_th or ['draft text'])}."

        # Find friction with other groups or text
        other_opposing = []
        for other_grp, _ in stk_groups.items():
            if other_grp == grp_name:
                continue
            og_cmts = [c for c in comments if c.get("stakeholder_group") == other_grp]
            if not og_cmts:
                continue
            og_avg = sum(c.get("sentiment_score", 0.0) for c in og_cmts) / len(og_cmts)
            if (g_avg < -0.2 and og_avg > 0.2) or (g_avg > 0.2 and og_avg < -0.2):
                other_opposing.append(other_grp)

        if other_opposing:
            fric_desc = f"Divergence with {', '.join(other_opposing[:2])} on regulatory stringency and compliance pace."
        else:
            fric_desc = f"Main friction is with draft stipulations in {', '.join(g_top_sec) if g_top_sec else 'consulted text'}."

        coalitions.append({
            "group": grp_name,
            "stance": stance_desc,
            "friction_with": fric_desc
        })

    # 5. DYNAMIC Action Roadmap
    roadmap = []
    actionable_cmts = [c for c in comments if c.get("proposed_text") and len(c.get("proposed_text", "").strip()) > 5]
    actionable_cmts.sort(key=lambda c: (0 if c.get("sentiment") in ["Strongly Critical", "Concerned"] else 1, -len(c.get("proposed_text", ""))))

    step_num = 1
    for act_c in actionable_cmts[:3]:
        sec = act_c.get("target_section") or "consulted section"
        stk = act_c.get("stakeholder_name", "Submitter")
        prop_snippet = act_c.get("proposed_text", "")[:120].strip()
        roadmap.append(
            f"{step_num}. Review {sec}: Deliberate on stakeholder amendment proposed by {stk}: \"{prop_snippet}\""
        )
        step_num += 1

    if len(roadmap) < 4:
        if top_friction:
            top_fz = top_friction[0]
            roadmap.append(
                f"{step_num}. Resolve {top_fz['topic']}: Evaluate potential transitional phasing or Acceptable Means of Compliance (AMC) for affected {', '.join(top_fz['contesting_groups'][:2])}."
            )
            step_num += 1

    if len(roadmap) < 4:
        roadmap.append(
            f"{step_num}. Issue Guidance Material (GM): Develop accompanying AMC/GM to provide practical implementation examples for key ambiguous terms."
        )

    return {
        "overall_sentiment_label": overall_label,
        "overall_sentiment_score": overall_score,
        "total_comments": total,
        "total_stakeholders": len(stakeholders),
        "sentiment_breakdown_pct": {
            "Strongly Critical": pct_crit,
            "Concerned": pct_conc,
            "Neutral / Inquiring": pct_neut,
            "Supportive": pct_supp,
        },
        "actionable_rate": actionable_rate,
        "executive_summary": exec_summary,
        "top_friction_zones": top_friction,
        "areas_of_broad_consensus": consensus,
        "stakeholder_coalition_dynamics": coalitions,
        "rulemaker_action_roadmap": roadmap,
    }


def compute_full_consultation_synthesis(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes a complete, unified multi-level synthesis bundle for a consultation session:
    - General Assessment of Stakeholder Sentiment Overall
    - Per Stakeholder Type Synthesis
    - Per Category / Theme Synthesis
    - Per Consulted Section Synthesis
    - Per Comment vs Consulted Text Synthesis
    """
    comments = session.get("comments", [])
    documents = session.get("documents", [])
    metrics = session.get("metrics", {})
    session_title = session.get("title", "Consultation")
    session_desc = session.get("description", "")

    # Extract all document sections
    all_sections: List[Dict[str, str]] = []
    for doc in documents:
        for sec in doc.get("sections", []):
            all_sections.append(sec)

    # 1. Overall assessment
    overall = synthesize_overall_sentiment_and_consultation(session_title, session_desc, comments, documents, metrics)

    # 2. Per Stakeholder Type
    stakeholder_groups = sorted(list(set(c.get("stakeholder_group", "Other") for c in comments if c.get("stakeholder_group"))))
    st_synthesis = []
    for grp in stakeholder_groups:
        st_synthesis.append(synthesize_by_stakeholder_type(grp, comments, all_sections, session_title))

    # 3. Per Category / Theme
    theme_set = sorted(list(set(t for c in comments for t in c.get("themes", []))))
    cat_synthesis = []
    for th in theme_set:
        cat_synthesis.append(synthesize_by_category(th, comments, all_sections, session_title))

    # 4. Per Section
    sec_titles = []
    for s in all_sections:
        if s["title"] not in sec_titles:
            sec_titles.append(s["title"])

    # Also include any target section referenced in comments that might not be in parsed headings
    for c in comments:
        matched_t = c.get("matched_section_title")
        if matched_t and matched_t not in sec_titles:
            sec_titles.append(matched_t)

    sec_synthesis = []
    for st_title in sec_titles:
        # Find content
        sec_content = ""
        for s in all_sections:
            if s["title"] == st_title:
                sec_content = s.get("content", "")
                break
        sec_synthesis.append(synthesize_by_section(st_title, sec_content, comments, session_title))

    # 5. Per Comment
    cmt_synthesis = []
    for c in comments:
        matched_content = c.get("matched_section_content", "")
        cmt_synthesis.append(synthesize_comment_vs_text(c, matched_content, session_title))

    org_synthesis = compute_organisations_analysis(comments)

    return {
        "consultation_id": session.get("consultation_id"),
        "title": session_title,
        "overall_assessment": overall,
        "organisations_analysis": org_synthesis,
        "required_text_blocks": session.get("required_text_blocks", []),
        "stakeholder_type_synthesis": st_synthesis,
        "category_synthesis": cat_synthesis,
        "section_synthesis": sec_synthesis,
        "comment_synthesis": cmt_synthesis,
    }


def generate_ai_deep_synthesis(
    session: Dict[str, Any],
    scope: str = "overall",
    target_id: Optional[str] = None,
    provider: str = "local"
) -> Dict[str, Any]:
    """
    Invokes LLM (Local LM Studio or Gemini) to generate rich narrative synthesis for any level,
    with automatic domain-specific fallback.
    """
    try:
        from api.utils import call_unified_chat
    except Exception:
        call_unified_chat = None

    bundle = compute_full_consultation_synthesis(session)
    session_title = session.get("title", "Consultation")

    prompt_context = ""
    target_summary = ""

    if scope == "overall":
        ov = bundle["overall_assessment"]
        prompt_context = f"""
Consultation Title: {session_title}
Total Comments: {ov['total_comments']}
Net Sentiment: {ov['overall_sentiment_score']} ({ov['overall_sentiment_label']})
Sentiment Breakdown: {json.dumps(ov['sentiment_breakdown_pct'])}
Key Friction Zones: {json.dumps(ov['top_friction_zones'])}
Consensus Areas: {json.dumps(ov['areas_of_broad_consensus'])}
Coalition Dynamics: {json.dumps(ov['stakeholder_coalition_dynamics'])}
"""
        target_summary = "General Assessment of Stakeholder Sentiment Overall and Macro Consultation Synthesis"

    elif scope == "stakeholder_type":
        match = next((s for s in bundle["stakeholder_type_synthesis"] if s["stakeholder_group"].lower() == (target_id or "").lower()), None)
        if not match and bundle["stakeholder_type_synthesis"]:
            match = bundle["stakeholder_type_synthesis"][0]
        if match:
            prompt_context = f"""
Consultation: {session_title}
Stakeholder Group: {match['stakeholder_group']}
Comments: {match['comment_count']}
Average Sentiment: {match['average_sentiment_score']}
Primary Sections Targeted: {', '.join(match['primary_targeted_sections'])}
Dominant Themes: {', '.join(match['dominant_themes'])}
Detailed Concerns vs Draft Text: {json.dumps(match['core_concerns_vs_consulted_text'], indent=2)}
Cross-Sector Friction: {match['cross_sector_alignment_and_conflicts']}
"""
            target_summary = f"Synthesis for Stakeholder Type: {match['stakeholder_group']}"

    elif scope == "category":
        match = next((c for c in bundle["category_synthesis"] if c["category_name"].lower() == (target_id or "").lower()), None)
        if not match and bundle["category_synthesis"]:
            match = bundle["category_synthesis"][0]
        if match:
            prompt_context = f"""
Consultation: {session_title}
Thematic Category: {match['category_name']}
Comments: {match['comment_count']}
Net Sentiment: {match['average_sentiment_score']}
Participating Groups: {', '.join(match['participating_groups'])}
Implicated Sections: {', '.join(match['implicated_sections'])}
Stakeholder Positions vs Text: {json.dumps(match['stakeholder_positions'], indent=2)}
Policy Trade-offs: {json.dumps(match['policy_tradeoffs_and_remedies'])}
"""
            target_summary = f"Synthesis for Category / Theme: {match['category_name']}"

    elif scope == "section":
        match = next((s for s in bundle["section_synthesis"] if (target_id or "").lower() in s["section_title"].lower()), None)
        if not match and bundle["section_synthesis"]:
            match = bundle["section_synthesis"][0]
        if match:
            prompt_context = f"""
Consultation: {session_title}
Section Title: {match['section_title']}
Draft Legal Text Excerpt:
{match['section_excerpt']}

Comments on this Section: {match['comment_count']}
Commenting Groups: {', '.join(match['commenting_groups'])}
Contentious Points: {json.dumps(match['contentious_provisions'])}
Supported Points: {json.dumps(match['supported_provisions'])}
Proposed Amendments: {json.dumps(match['suggested_amendments'], indent=2)}
"""
            target_summary = f"Synthesis for Section: {match['section_title']}"

    elif scope == "comment":
        match = next((c for c in bundle["comment_synthesis"] if c["comment_id"] == target_id), None)
        if not match and bundle["comment_synthesis"]:
            match = bundle["comment_synthesis"][0]
        if match:
            prompt_context = f"""
Consultation: {session_title}
Comment ID: {match['comment_id']}
Submitter: {match['stakeholder_name']} ({match['stakeholder_group']})
Target Provision: {match['target_section']}
Stance: {match['sentiment']}
Comment Text: {match['comment_text']}
Proposed Text: {match['proposed_text']}
Rationale: {match['rationale']}

Consulted Draft Text Stipulation:
{match['text_stipulation']}
"""
            target_summary = f"Synthesis for Comment {match['comment_id']} ({match['stakeholder_name']})"

    elif scope == "organisation":
        org_list = bundle.get("organisations_analysis", [])
        match = next((o for o in org_list if o["organisation_name"].lower() == (target_id or "").lower()), None)
        if not match and org_list:
            match = org_list[0]
        if match:
            prompt_context = f"""
Consultation: {session_title}
Organisation Name: {match['organisation_name']} ({match['stakeholder_category']})
Total Comments: {match['total_comments']}
Average Weighted Score: {match['average_weighted_score']} (Section: {match['average_section_score']}, Document: {match['average_document_score']})
Stance: {match['stance']}
Primary Direction of Travel: {match['primary_direction_of_travel']}
Strategy Summary: {match['direction_of_travel_summary']}
Targeted Sections: {', '.join(match['targeted_sections'])}
Key Proposed Amendments: {json.dumps(match['key_proposals'], indent=2)}
"""
            target_summary = f"Synthesis for Organisation: {match['organisation_name']} ({match['primary_direction_of_travel']})"

    elif scope == "silence_accounting":
        match = next((c for c in bundle["comment_synthesis"] if c["comment_id"] == target_id), None)
        if not match and bundle["comment_synthesis"]:
            match = bundle["comment_synthesis"][0]
        if match:
            sn = match.get("support_network", {})
            prompt_context = f"""
Consultation: {session_title}
Critical Comment: {match['comment_id']} from {match['stakeholder_name']}
Target Section: {match['target_section']}
Comment Text: {match['comment_text']}
Proposed Text: {match['proposed_text']}
Rationale: {match['rationale']}

Support & Silence Breakdown:
- Total Participating Organisations: {sn.get('total_participating_organisations', 0)}
- Active Co-objectors ({sn.get('support_rate_pct', 0)}%): {', '.join(sn.get('co_objectors', [])) or 'None'}
- Active Defenders ({sn.get('defense_rate_pct', 0)}%): {', '.join(sn.get('defenders', [])) or 'None'}
- Silent Organisations ({sn.get('silence_rate_pct', 0)}%): {', '.join(sn.get('silent_organisations', []))}
- Regulatory Interpretation: {sn.get('regulatory_interpretation', '')}
"""
            target_summary = f"Stakeholder Support vs Silence Accounting for {match['target_section']} ({match['stakeholder_name']})"

    system_prompt = (
        f"You are an expert regulatory drafting counsel assisting a government rulemaking directorate for the consultation: '{session_title}' "
        f"(Domain: {session.get('domain', 'Regulatory Affairs')}). "
        "Your task is to synthesize stakeholder comments and concerns strictly against the provided consulted text and evidence. "
        "Provide objective, rigorous analysis of the legal tension, operational feasibility, and trade-offs. "
        "Do NOT introduce external assumptions or mention unrelated regulations. Highlight practical drafting options for the human rulemaker."
    )

    user_prompt = f"""
Perform a structured synthesis for: {target_summary}

Context and Evidence:
{prompt_context}

Please structure your synthesis into the following sections:
1. Executive Synthesis & Core Tension: How stakeholder arguments intersect or conflict with the consulted text.
2. Operational & Safety Assessment: Real-world operational impacts, safety margins, and economic feasibility.
3. Cross-Stakeholder Dynamics: Who benefits, who bears the burden, and where sectoral interests clash.
4. Deliberation & Drafting Recommendations: 3 concrete, balanced drafting options for the rulemaker.
"""

    narrative = ""
    if call_unified_chat is not None:
        try:
            narrative = call_unified_chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                provider=provider or "local",
                temperature=0.3,
                max_tokens=900
            )
        except Exception as e:
            print(f"[Synthesis Warning] LLM call failed ({e}), using analytical narrative.")

    if not narrative:
        # High quality offline domain synthesis fallback
        if scope == "overall":
            narrative = (
                f"### Executive General Assessment of Consultation Feedback\n\n"
                f"{bundle['overall_assessment']['executive_summary']}\n\n"
                f"#### Key Regulatory Friction Zones vs Consulted Text:\n"
                + "\n".join([f"- **{fz['topic']}** ({fz['affected_articles']}): {fz['core_issue']}" for fz in bundle['overall_assessment']['top_friction_zones']])
                + "\n\n#### Recommended Rulemaker Roadmap:\n"
                + "\n".join([f"- {r}" for r in bundle['overall_assessment']['rulemaker_action_roadmap']])
            )
        else:
            narrative = (
                f"### Analytical Synthesis for {target_summary}\n\n"
                f"• **Regulatory Context:** The consulted draft provisions require balanced reconciliation with operational sector constraints.\n"
                f"• **Stakeholder Stance:** Feedback reflects substantial technical expertise, offering concrete alternatives to the published text.\n"
                f"• **Drafter Guidance:** Evaluate phased implementation and guidance material (AMC/GM) to address legitimate operational concerns without lowering safety thresholds."
            )

    return {
        "status": "success",
        "scope": scope,
        "target_id": target_id,
        "target_summary": target_summary,
        "synthesis_narrative": narrative,
        "structured_data": bundle
    }

