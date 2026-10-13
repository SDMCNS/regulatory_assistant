"""
consultation.py - FastAPI Endpoints for Document Consultation Workspace.

Provides:
- Creation of consultation sessions with uploaded consultation documents (PDF, Word .doc/.docx, XML)
  and stakeholder feedback comments CSV.
- Thematic clustering, regulatory sentiment analysis, and comment validity assessment.
- Human reviewer triage notes and AI consideration assistance.
- Full consultation review matrix export and session lifecycle management.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Response
from pydantic import BaseModel, Field

from ingestion.core.config import settings
from ingestion.user_docs.extractor import extract_user_document
from ingestion.consultation import (
    parse_feedback_csv,
    extract_document_sections,
    enrich_feedback_comments,
    compute_consultation_metrics,
    save_consultation_session,
    get_consultation_session,
    list_consultation_sessions,
    update_comment_review,
    delete_consultation_session,
)
from api.utils import call_unified_chat

router = APIRouter()

CONSULTATION_DATA_DIR = settings.DATA_DIR / "consultations"
CONSULTATION_DATA_DIR.mkdir(parents=True, exist_ok=True)


class UpdateReviewRequest(BaseModel):
    human_review_status: str = Field(..., description="Triage status (e.g. 'Pending Review', 'Under Technical Assessment', 'In Consideration', 'Flagged for Legal Review', 'Draft Response Prepared')")
    human_notes: str = Field("", description="Human analyst reviewer notes and drafting considerations")


class AssistFormulationRequest(BaseModel):
    consultation_id: str
    provider: Optional[str] = "local"


@router.get("/sessions", tags=["CONSULTATION"])
def api_list_consultations():
    """Returns list of consultation sessions with summary metadata."""
    try:
        return list_consultation_sessions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list consultation sessions: {e}")


@router.get("/session/{consultation_id}", tags=["CONSULTATION"])
def api_get_consultation(consultation_id: str):
    """Retrieves a consultation session with all comments, themes, and document excerpts."""
    try:
        sess = get_consultation_session(consultation_id)
        if not sess:
            raise HTTPException(status_code=404, detail=f"Consultation session '{consultation_id}' not found.")
        return sess
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load consultation session: {e}")


@router.post("/session/create", tags=["CONSULTATION"])
async def api_create_consultation(
    title: str = Form(..., description="Title of the consultation (e.g. NPA 2024-05 Aerodrome Safety)"),
    description: Optional[str] = Form("", description="Scope, regulatory reference, or drafter's objectives"),
    domain: Optional[str] = Form("Aviation Safety / Regulatory Affairs", description="Regulatory domain"),
    feedback_csv: UploadFile = File(..., description="CSV file of stakeholder feedback comments"),
    consultation_doc: Optional[UploadFile] = File(None, description="Optional document(s) to be consulted (PDF, Word .doc/.docx, XML, TXT)")
):
    """
    Creates a new Document Consultation Workspace session:
    1. Extracts text and sections from the consulted document(s) (PDF, Word .doc/.docx, etc.).
    2. Parses the stakeholder feedback comments CSV.
    3. Runs analytics: Common Themes, Sentiment, Validity Assessment, and Section Alignment.
    4. Persists session and comments in SQLite.
    """
    consultation_id = f"CONSULT_{str(uuid.uuid4())[:8].upper()}"
    docs_payload: List[Dict[str, Any]] = []
    document_sections: List[Dict[str, str]] = []

    # 1. Process Consultation Document (if provided)
    if consultation_doc is not None and consultation_doc.filename:
        filename = consultation_doc.filename
        save_path = CONSULTATION_DATA_DIR / f"{consultation_id}_{filename}"
        try:
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(consultation_doc.file, buffer)

            extracted = extract_user_document(save_path, filename)
            doc_sections = extract_document_sections(extracted["raw_text"])
            document_sections.extend(doc_sections)

            docs_payload.append({
                "doc_id": f"DOC_{str(uuid.uuid4())[:6]}",
                "filename": filename,
                "title": extracted["title"],
                "author": extracted.get("author"),
                "date": extracted.get("date"),
                "word_count": extracted["word_count"],
                "page_count": extracted["page_count"],
                "sections": doc_sections,
            })
        except Exception as e:
            print(f"[Consultation Warning] Failed to parse consultation document {filename}: {e}")

    # 2. Process Stakeholder Feedback CSV
    try:
        csv_bytes = await feedback_csv.read()
        csv_text = csv_bytes.decode("utf-8", errors="replace")
        raw_comments, map_summary = parse_feedback_csv(csv_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse feedback CSV: {e}")

    if not raw_comments:
        raise HTTPException(status_code=400, detail="Feedback CSV contained no valid comment records.")

    # 3. Analyze Comments (Themes, Sentiment, Validity, Document Section Alignment)
    try:
        enriched_comments = enrich_feedback_comments(raw_comments, document_sections)
        metrics = compute_consultation_metrics(enriched_comments)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze comments: {e}")

    # 4. Save to SQLite
    try:
        save_consultation_session(
            consultation_id=consultation_id,
            title=title,
            description=description or "",
            domain=domain or "Aviation Safety / Regulatory Affairs",
            documents=docs_payload,
            comments=enriched_comments,
            metrics=metrics
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save consultation session: {e}")

    return {
        "status": "success",
        "consultation_id": consultation_id,
        "title": title,
        "description": description,
        "domain": domain,
        "documents_count": len(docs_payload),
        "comments_count": len(enriched_comments),
        "metrics": metrics,
        "column_mapping": map_summary,
        "comments": enriched_comments,
    }


@router.patch("/comment/{comment_id}", tags=["CONSULTATION"])
def api_update_comment(comment_id: str, req: UpdateReviewRequest):
    """
    Updates a comment's human review status (e.g. 'Pending Review', 'Under Technical Assessment',
    'In Consideration', 'Flagged for Legal Review', 'Draft Response Prepared') and human analyst notes.
    """
    try:
        update_comment_review(
            comment_id=comment_id,
            human_review_status=req.human_review_status,
            human_notes=req.human_notes
        )
        return {"status": "success", "comment_id": comment_id, "updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update comment review: {e}")


@router.post("/comment/{comment_id}/assist", tags=["CONSULTATION"])
def api_assist_comment_formulation(comment_id: str, req: AssistFormulationRequest):
    """
    Assists the human reviewer by generating objective draft formulation considerations:
    - Counter-arguments, operational considerations, safety implications, and regulatory precedents.
    - Explicitly does NOT decide whether to accept or reject the comment.
    """
    sess = get_consultation_session(req.consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    target_comment = next((c for c in sess["comments"] if c["comment_id"] == comment_id), None)
    if not target_comment:
        raise HTTPException(status_code=404, detail="Comment not found.")

    prompt = f"""
You are an expert regulatory drafting assistant helping a rulemaker review stakeholder feedback for the consultation: '{sess["title"]}'.

Rulemaking Philosophy:
Your role is to HELP the regulatory officer deliberate, NOT to decide or replace them. Do not state whether the comment is accepted or rejected.

Stakeholder Comment to Analyze:
- Stakeholder: {target_comment["stakeholder_name"]} ({target_comment["stakeholder_group"]})
- Targeted Section: {target_comment["target_section"]}
- Comment: {target_comment["comment_text"]}
- Proposed Text: {target_comment.get("proposed_text") or "None proposed"}
- Stated Rationale: {target_comment.get("rationale") or "None provided"}
- Identified Themes: {", ".join(target_comment.get("themes", []))}
- Stance: {target_comment.get("sentiment")}

Consulted Document Section Context:
{target_comment.get("matched_section_content") or "Relevant section context from consulted text."}

Please provide a structured, concise brief for the human reviewer:
1. Core Stakeholder Argument: A 1-sentence synthesis of the underlying concern.
2. Technical / Regulatory Considerations: Key trade-offs, safety implications, and potential operational impacts.
3. Proportionality & Enforcement Aspect: How this affects different operator sizes or compliance burdens.
4. Suggested Deliberation Points: 2-3 specific questions or drafting adjustments the human analyst should consider.
"""

    messages = [
        {"role": "system", "content": "You are a professional regulatory policy drafting assistant. You provide balanced, objective analysis to support human rulemakers."},
        {"role": "user", "content": prompt}
    ]

    try:
        response_text = call_unified_chat(
            messages=messages,
            provider=req.provider or "local",
            temperature=0.3,
            max_tokens=600
        )
    except Exception as e:
        # Fallback offline structured assistance
        response_text = (
            f"**Synthesis of Stakeholder Feedback:**\n"
            f"• Submitter {target_comment['stakeholder_name']} expresses {target_comment['sentiment'].lower()} concerns regarding {target_comment['target_section']}.\n"
            f"• Primary themes involved: {', '.join(target_comment.get('themes', []))}.\n\n"
            f"**Considerations for Deliberation:**\n"
            f"• **Operational Impact:** Evaluate whether the proposed timeline/requirement creates disproportionate barriers for {target_comment['stakeholder_group']}.\n"
            f"• **Safety Objective:** Confirm whether any concession would compromise the core safety rationale or baseline compliance.\n"
            f"• **Drafting Option:** If accommodating the concern, consider adding guidance material (GM) or phased compliance rather than amending hard rule text."
        )

    # Save to SQLite
    try:
        update_comment_review(
            comment_id=comment_id,
            human_review_status=target_comment["human_review_status"],
            human_notes=target_comment["human_notes"],
            ai_assistance_notes=response_text
        )
    except Exception as e:
        print(f"[Consultation Warning] Failed saving AI assistance notes: {e}")

    return {
        "status": "success",
        "comment_id": comment_id,
        "ai_assistance_notes": response_text
    }


@router.post("/session/load-sample", tags=["CONSULTATION"])
def api_load_sample_consultation():
    """
    Seeds and returns a realistic sample aviation consultation:
    'NPA 2024-05: Implementation of Safety Management Systems in Aerodrome Operations'
    with 12 diverse stakeholder feedback comments across Airlines, Airports, Unions, and Manufacturers.
    """
    consultation_id = f"SAMPLE_NPA_2024_05"
    existing = get_consultation_session(consultation_id)
    if existing:
        return existing

    sample_doc_content = """# NPA 2024-05: Safety Management Systems in Aerodrome Operations

## Article 1: Subject Matter and Scope
This Regulation establishes harmonized requirements for aerodrome certificate holders regarding the management of operational safety risks, mandatory safety reporting, and coordination with air navigation service providers.

## Article 4: Hazard Identification and Reporting Systems
1. The aerodrome operator shall establish a voluntary and mandatory safety occurrence reporting system accessible to all personnel, ground handlers, and air operators.
2. Reports received shall be investigated within 14 calendar days of receipt.
3. Where a report identifies a latent hazard affecting runway operations, immediate mitigation measures shall be coordinated with the appropriate Air Traffic Control (ATC) unit.

## Article 7: Transition Periods and Phased Implementation
1. This Regulation enters into force on the twentieth day following that of its publication in the Official Journal of the European Union.
2. Aerodrome operators shall achieve full compliance with Articles 4 and 5 within 6 months from the date of entry into force.
3. For aerodromes handling fewer than 2 million passengers annually, an additional grace period of 3 months may be granted by the Competent Authority.

## Article 9: Cybersecurity and Data Protection in Safety Management
All safety databases containing occurrence reports must comply with Commission Implementing Regulation (EU) 2023/203 (Part-IS) to prevent unauthorized disclosure of reporter identity while facilitating just culture data sharing.
"""

    doc_sections = extract_document_sections(sample_doc_content)
    docs_payload = [{
        "doc_id": "DOC_NPA_2024_05",
        "filename": "NPA_2024_05_Aerodrome_SMS.docx",
        "title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
        "author": "EASA Rulemaking Directorate",
        "date": "2024-04-10",
        "word_count": len(sample_doc_content.split()),
        "page_count": 4,
        "sections": doc_sections,
    }]

    sample_csv_data = [
        {
            "comment_id": "CMT-001",
            "stakeholder_name": "Lufthansa Group",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(2)",
            "comment_text": "The 14-day mandatory investigation timeframe is completely unrealistic for complex runway incursion occurrences requiring multi-party data coordination between the airport, airline, and ATC.",
            "proposed_text": "Amend Article 4(2) to read: 'Initial safety assessment shall be conducted within 30 days, with full investigation completed within 90 days.'",
            "rationale": "High quality safety investigations take time; forcing a 14-day closeout will lead to superficial box-ticking rather than genuine root cause discovery.",
        },
        {
            "comment_id": "CMT-002",
            "stakeholder_name": "ACI Europe (Airports Council International)",
            "stakeholder_group": "Aerodrome Operator",
            "target_section": "Article 7(2)",
            "comment_text": "A 6-month transition period across the entire network is unachievable due to software procurement and procurement cycles for safety management databases.",
            "proposed_text": "Extend transition period in Article 7(2) from 6 months to 18 months.",
            "rationale": "Airport operators need sufficient budget lead time to integrate reporting tools with ground handling contractors.",
        },
        {
            "comment_id": "CMT-003",
            "stakeholder_name": "ECA (European Cockpit Association)",
            "stakeholder_group": "Pilots / Crew / Professional Union",
            "target_section": "Article 9",
            "comment_text": "We strongly support the integration of Part-IS cybersecurity principles, but must stress that de-identification of pilot reporter details is an inviolable prerequisite for Just Culture.",
            "proposed_text": "Add paragraph 9(2): 'Reporter identity shall be cryptographically pseudonymized prior to inter-agency data sharing.'",
            "rationale": "Without strict identity protection guarantees, voluntary reporting rates by flight crew will drop precipitously.",
        },
        {
            "comment_id": "CMT-004",
            "stakeholder_name": "DGAC France",
            "stakeholder_group": "National Aviation Authority (NAA) / Regulator",
            "target_section": "Article 7(3)",
            "comment_text": "The passenger threshold of 2 million is appropriate, but the Competent Authority must have clear objective criteria to evaluate whether a 3-month grace period should be authorized.",
            "proposed_text": "Include AMC/GM defining the criteria under which National Authorities may grant grace periods.",
            "rationale": "Ensures uniform enforcement and level playing field across Member States.",
        },
        {
            "comment_id": "CMT-005",
            "stakeholder_name": "Airbus Commercial Aviation",
            "stakeholder_group": "Manufacturer / OEM",
            "target_section": "Article 4(3)",
            "comment_text": "We welcome the requirement to coordinate latent runway hazards directly with ATC units, which aligns with ICAO Global Aviation Safety Plan priorities.",
            "proposed_text": "",
            "rationale": "Prompt ATC notification significantly reduces risk of runway contamination incidents.",
        },
        {
            "comment_id": "CMT-006",
            "stakeholder_name": "Regional Airports Association",
            "stakeholder_group": "Aerodrome Operator",
            "target_section": "Article 7(3)",
            "comment_text": "The 3-month grace period for small airports is completely inadequate. Small aerodromes operating on seasonal schedules require at least a 12-month exemption.",
            "proposed_text": "Increase small operator grace period from 3 months to 12 months in Article 7(3).",
            "rationale": "Small regional aerodromes operate with minimal staffing and cannot implement sophisticated SMS software in one quarter.",
        },
        {
            "comment_id": "CMT-007",
            "stakeholder_name": "Ryanair DAC",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(1)",
            "comment_text": "Ground handlers should not operate isolated reporting databases. Aerodrome operators must establish a unified single-window portal.",
            "proposed_text": "Insert in Article 4(1): 'The aerodrome operator shall host a unified single-window portal accessible by all contracted ground service providers.'",
            "rationale": "Airlines currently encounter fragmented reporting forms at every different European airport.",
        },
        {
            "comment_id": "CMT-008",
            "stakeholder_name": "CANSO (Civil Air Navigation Services Organisation)",
            "stakeholder_group": "Air Navigation Service Provider (ANSP)",
            "target_section": "Article 4(3)",
            "comment_text": "Please clarify what communication protocol should be utilized between aerodrome operations and ATC tower when logging latent hazard mitigations.",
            "proposed_text": "Develop accompanying GM detailing standard coordination channels and logging formats.",
            "rationale": "Ambiguity over formal vs tactical coordination could create confusion during live runway operations.",
        },
        {
            "comment_id": "CMT-009",
            "stakeholder_name": "European Gliding Union",
            "stakeholder_group": "General Aviation / Aerial Work",
            "target_section": "Article 1",
            "comment_text": "Glider fields and grass airstrips should be categorically excluded from the scope of this Regulation.",
            "proposed_text": "Amend Article 1 to specify: 'This Regulation does not apply to aerodromes exclusively accommodating non-powered aircraft.'",
            "rationale": "Disproportionate administrative burden on non-commercial sporting aviation.",
        },
        {
            "comment_id": "CMT-010",
            "stakeholder_name": "EasyJet Airline Company",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(2)",
            "comment_text": "We concur with Lufthansa regarding the 14-day timeline. 30 days is standard across ICAO Annex 13 protocols.",
            "proposed_text": "Replace '14 calendar days' with '30 calendar days'.",
            "rationale": "Harmonization with international occurrence investigation practices.",
        },
        {
            "comment_id": "CMT-011",
            "stakeholder_name": "Austro Control",
            "stakeholder_group": "National Aviation Authority (NAA) / Regulator",
            "target_section": "Article 9",
            "comment_text": "Cross-reference to Commission Implementing Regulation (EU) 2023/203 is supported, but verify that definition of 'sensitive safety information' matches Regulation (EU) 376/2014.",
            "proposed_text": "Ensure alignment with Article 15 of Regulation (EU) 376/2014.",
            "rationale": "Avoid legal conflict between cybersecurity obligations and occurrence reporting protections.",
        },
        {
            "comment_id": "CMT-012",
            "stakeholder_name": "European Business Aviation Association (EBAA)",
            "stakeholder_group": "General Aviation / Aerial Work",
            "target_section": "Article 7",
            "comment_text": "Business aviation operators need clear guidance on how ad-hoc non-scheduled charter flights interact with aerodrome hazard systems.",
            "proposed_text": "Provide GM on transient operator access to reporting tools.",
            "rationale": "Non-base operators need instant guest access to log aerodrome surface issues.",
        }
    ]

    enriched = enrich_feedback_comments(sample_csv_data, doc_sections)
    metrics = compute_consultation_metrics(enriched)

    save_consultation_session(
        consultation_id=consultation_id,
        title="NPA 2024-05: Safety Management Systems in Aerodrome Operations",
        description="Public consultation on draft rules updating aerodrome safety risk management, occurrence investigation timelines, and Part-IS cybersecurity coordination.",
        domain="Aerodromes & Air Traffic Management",
        documents=docs_payload,
        comments=enriched,
        metrics=metrics
    )

    return get_consultation_session(consultation_id)


@router.get("/session/{consultation_id}/export", tags=["CONSULTATION"])
def api_export_consultation(consultation_id: str, format: Optional[str] = "csv"):
    """Exports consultation review matrix with stakeholder comments, themes, and human notes as CSV or JSON."""
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    if format == "json":
        return Response(
            content=json.dumps(sess, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={consultation_id}_review_matrix.json"}
        )

    # Export CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Comment ID",
        "Stakeholder Name",
        "Stakeholder Group",
        "Target Section",
        "Comment Text",
        "Proposed Text",
        "Rationale",
        "Themes",
        "Sentiment",
        "Validity",
        "Human Review Status",
        "Human Analyst Notes",
        "AI Assistance Notes"
    ])

    for c in sess["comments"]:
        writer.writerow([
            c.get("comment_id", ""),
            c.get("stakeholder_name", ""),
            c.get("stakeholder_group", ""),
            c.get("target_section", ""),
            c.get("comment_text", ""),
            c.get("proposed_text", ""),
            c.get("rationale", ""),
            ", ".join(c.get("themes", [])),
            c.get("sentiment", ""),
            c.get("validity", ""),
            c.get("human_review_status", ""),
            c.get("human_notes", ""),
            c.get("ai_assistance_notes", "") or ""
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={consultation_id}_review_matrix.csv"}
    )


@router.delete("/session/{consultation_id}", tags=["CONSULTATION"])
def api_delete_consultation(consultation_id: str):
    """Deletes a consultation session and associated records."""
    success = delete_consultation_session(consultation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Consultation session not found or already deleted.")
    return {"status": "success", "consultation_id": consultation_id, "deleted": True}
