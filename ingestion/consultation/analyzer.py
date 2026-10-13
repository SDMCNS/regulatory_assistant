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

    clean_target = re.sub(r"[^\w]", " ", target_section.lower()).strip()
    target_tokens = [t for t in clean_target.split() if len(t) > 2 and t not in ["general", "whole", "document"]]

    # 1. Match section title with target tokens
    if target_tokens:
        for sec in sections:
            sec_title_lower = sec["title"].lower()
            if all(t in sec_title_lower for t in target_tokens):
                return sec["title"], sec["content"][:2000]

        for sec in sections:
            sec_title_lower = sec["title"].lower()
            if any(t in sec_title_lower for t in target_tokens):
                return sec["title"], sec["content"][:2000]

    # 2. Match key keywords from comment in section contents
    comment_tokens = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", comment_text)]
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
            return best_sec["title"], best_sec["content"][:2000]

    # Fallback to first section if only 1 section
    if len(sections) == 1:
        return sections[0]["title"], sections[0]["content"][:2000]

    return None, None


def enrich_feedback_comments(
    comments: List[Dict[str, Any]],
    document_sections: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    Applies themes, sentiment, validity assessment, and document section matching to all comments.
    """
    enriched: List[Dict[str, Any]] = []

    for c in comments:
        c_text = c.get("comment_text", "")
        p_text = c.get("proposed_text", "")
        r_text = c.get("rationale", "")
        t_sec = c.get("target_section", "")

        themes = analyze_comment_themes(c_text, p_text, r_text)
        sentiment_label, sentiment_score = analyze_comment_sentiment(c_text, r_text)
        validity_label, validity_rationale = assess_comment_validity(c_text, p_text, r_text, t_sec)

        matched_title, matched_snippet = match_comment_to_document_section(t_sec, c_text, document_sections)

        enriched.append({
            "comment_id": c.get("comment_id"),
            "stakeholder_name": c.get("stakeholder_name"),
            "stakeholder_group": c.get("stakeholder_group"),
            "target_section": t_sec,
            "comment_text": c_text,
            "proposed_text": p_text,
            "rationale": r_text,
            "themes": themes,
            "sentiment": sentiment_label,
            "sentiment_score": sentiment_score,
            "validity": validity_label,
            "validity_rationale": validity_rationale,
            "matched_section_title": matched_title,
            "matched_section_content": matched_snippet,
            "human_review_status": "Pending Review",
            "human_notes": "",
            "ai_assistance_notes": None,
        })

    return enriched


def compute_consultation_metrics(comments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes comprehensive aggregated metrics across all feedback comments."""
    total = len(comments)
    if total == 0:
        return {}

    # Sentiment distribution
    sentiment_counts: Dict[str, int] = {}
    for c in comments:
        s = c.get("sentiment", "Neutral / Inquiring")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

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

    return {
        "total_comments": total,
        "sentiment_distribution": sentiment_counts,
        "stakeholder_groups": group_counts,
        "theme_distribution": theme_counts,
        "validity_distribution": validity_counts,
        "review_status_distribution": status_counts,
        "actionable_proposal_pct": actionable_pct,
    }
