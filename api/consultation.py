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
    CONSULTATION_TEMPLATE_FIELDS,
    parse_feedback_csv,
    parse_feedback_csv_with_mapping,
    detect_csv_columns,
    inspect_feedback_csv,
    build_required_text_blocks,
    extract_document_sections,
    enrich_feedback_comments,
    compute_consultation_metrics,
    compute_organisations_analysis,
    compute_full_consultation_synthesis,
    generate_ai_deep_synthesis,
    save_consultation_session,
    get_consultation_session,
    list_consultation_sessions,
    update_comment_review,
    update_session_text_block,
    delete_consultation_session,
)
from api.utils import call_unified_chat

router = APIRouter()

CONSULTATION_DATA_DIR = settings.DATA_DIR / "consultations"
CONSULTATION_DATA_DIR.mkdir(parents=True, exist_ok=True)


class UpdateReviewRequest(BaseModel):
    human_review_status: str = Field(..., description="Triage status (e.g. 'Pending Review', 'Under Technical Assessment', 'In Consideration', 'Flagged for Legal Review', 'Draft Response Prepared')")
    human_notes: str = Field("", description="Human analyst reviewer notes and drafting considerations")


class UpdateTextBlockRequest(BaseModel):
    content: str = Field(..., description="Provided document text block content")


class AssistFormulationRequest(BaseModel):
    consultation_id: str
    provider: Optional[str] = "local"


class DeepSynthesisRequest(BaseModel):
    scope: str = Field(default="overall", description="'overall' | 'stakeholder_type' | 'category' | 'section' | 'comment' | 'organisation' | 'silence_accounting'")
    target_id: Optional[str] = Field(default=None, description="Identifier for target stakeholder group, theme name, section title, organisation name, or comment ID")
    provider: Optional[str] = Field(default="local", description="LLM provider: 'local' | 'gemini'")


@router.get("/template-fields", tags=["CONSULTATION"])
def api_get_template_fields():
    """Returns the standard consultation feedback comment template fields and descriptions."""
    return {
        "status": "success",
        "template_fields": CONSULTATION_TEMPLATE_FIELDS
    }


@router.post("/inspect-file", tags=["CONSULTATION"])
async def api_inspect_file(
    feedback_file: UploadFile = File(..., description="Stakeholder feedback CSV/TSV to inspect before grouping"),
    delimiter: Optional[str] = Form(None)
):
    """
    Inspects uploaded comments file, extracts headers and sample rows,
    and returns detected mapping against the standard consultation template before user confirms.
    """
    try:
        content_bytes = await feedback_file.read()
        content_text = content_bytes.decode("utf-8", errors="replace")
        return inspect_feedback_csv(content_text, delimiter=delimiter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inspect feedback file: {e}")


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
    consultation_doc: Optional[UploadFile] = File(None, description="Optional document(s) to be consulted (PDF, Word .doc/.docx, XML, TXT)"),
    column_mapping: Optional[str] = Form(None, description="Optional JSON string of user-confirmed column mapping"),
    delimiter: Optional[str] = Form(None, description="Optional delimiter override (',' or '\t' or ';')")
):
    """
    Creates a new Document Consultation Workspace session:
    1. Extracts text and sections from the consulted document(s) (PDF, Word .doc/.docx, etc.).
    2. Parses the stakeholder feedback comments CSV according to user-confirmed column mappings.
    3. Identifies required document text blocks from (document_title, chapter_section) comment references.
    4. Runs dual-context analytics (75% section / 25% whole doc), support network & silence accounting.
    5. Computes organisation-level stances and direction of travel.
    6. Persists session, text blocks, organisations, and comments in SQLite.
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

        parsed_mapping = None
        if column_mapping:
            try:
                parsed_mapping = json.loads(column_mapping)
            except Exception as e:
                print(f"[Consultation Warning] Could not parse column_mapping JSON: {e}")

        if parsed_mapping:
            raw_comments, map_summary = parse_feedback_csv_with_mapping(csv_text, parsed_mapping, delimiter=delimiter)
        else:
            raw_comments, map_summary = parse_feedback_csv(csv_text, delimiter=delimiter)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse feedback CSV: {e}")

    if not raw_comments:
        raise HTTPException(status_code=400, detail="Feedback CSV contained no valid comment records.")

    # 3. Analyze Comments & Extract Text Blocks
    try:
        # Build required text blocks from comments referencing (document_title, chapter_section)
        required_text_blocks = build_required_text_blocks(raw_comments, document_sections)

        # Analyze & enrich comments with dual context (75% section / 25% doc), support networks, etc.
        enriched_comments = enrich_feedback_comments(raw_comments, document_sections)

        # Compute metrics
        metrics = compute_consultation_metrics(enriched_comments)

        # Compute organisations analysis (stances, direction of travel, support profiles)
        organisations_analysis = compute_organisations_analysis(enriched_comments)
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
            metrics=metrics,
            field_mapping=map_summary,
            required_text_blocks=required_text_blocks,
            organisations_analysis=organisations_analysis
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
        "required_text_blocks": required_text_blocks,
        "organisations_analysis": organisations_analysis,
        "comments": enriched_comments,
    }


@router.get("/session/{consultation_id}/text-blocks", tags=["CONSULTATION"])
def api_get_text_blocks(consultation_id: str):
    """
    Returns the list of required document text blocks for this consultation session.
    Derived from (Document title, Chapter/Section) pairs identified in stakeholder comments.
    """
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Consultation session not found.")
    return {
        "status": "success",
        "consultation_id": consultation_id,
        "text_blocks": sess.get("required_text_blocks", [])
    }


@router.put("/session/{consultation_id}/text-block/{block_id}", tags=["CONSULTATION"])
def api_update_text_block(consultation_id: str, block_id: str, req: UpdateTextBlockRequest):
    """
    Updates the provided content of a required text block (pasted or edited by user)
    and re-evaluates associated comment matches and section scores.
    """
    success = update_session_text_block(consultation_id, block_id, req.content)
    if not success:
        raise HTTPException(status_code=404, detail=f"Text block '{block_id}' not found or update failed.")

    sess = get_consultation_session(consultation_id)
    return {
        "status": "success",
        "consultation_id": consultation_id,
        "block_id": block_id,
        "text_blocks": sess.get("required_text_blocks", []) if sess else []
    }


@router.get("/session/{consultation_id}/organisations", tags=["CONSULTATION"])
def api_get_organisations(consultation_id: str):
    """
    Returns the organisation-level analysis: stances, weighted average scores,
    strategic directions of travel, and support networks.
    """
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Consultation session not found.")
    return {
        "status": "success",
        "consultation_id": consultation_id,
        "organisations": sess.get("organisations_analysis", [])
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

    domain_name = sess.get("domain", "Regulatory Affairs")
    prompt = f"""
You are an expert regulatory drafting assistant helping a rulemaker review stakeholder feedback for the consultation: '{sess["title"]}' (Domain: {domain_name}).

Rulemaking Philosophy:
Your role is to HELP the regulatory officer deliberate, NOT to decide or replace them. Base all points STRICTLY on the stakeholder's submitted comment and the consulted document text excerpt below. Do NOT make outside assumptions or refer to unrelated regulations. Do not state whether the comment is accepted or rejected.

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
2. Technical / Regulatory Considerations: Key trade-offs, operational implications, and alignment with the consulted provision.
3. Proportionality & Enforcement Aspect: How this affects different stakeholder categories or compliance burdens.
4. Suggested Deliberation Points: 2-3 specific questions or drafting adjustments the human analyst should consider.
"""

    messages = [
        {"role": "system", "content": f"You are a professional regulatory policy drafting assistant specializing in {domain_name}. You provide balanced, objective analysis grounded strictly in the provided consultation documents and comments."},
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
    if existing and existing.get("required_text_blocks") and existing.get("organisations_analysis"):
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
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 4(2)",
            "page": "14",
            "original_text": "Reports received shall be investigated within 14 calendar days of receipt.",
            "comment_text": "The 14-day mandatory investigation timeframe is completely unrealistic for complex runway incursion occurrences requiring multi-party data coordination between the airport, airline, and ATC.",
            "comment_type": "Technical / Change Request",
            "importance": "Critical",
            "proposed_text": "Amend Article 4(2) to read: 'Initial safety assessment shall be conducted within 30 days, with full investigation completed within 90 days.'",
            "stakeholder_category": "Air Operator / Airline",
            "organisation_name": "Lufthansa Group",
            "stakeholder_name": "Lufthansa Group",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(2)",
            "af_cba": "CBA: Major overtime and consultant surge costs (€1.8M/yr)",
            "response_to_comment": "Under Technical Assessment",
            "rationale": "High quality safety investigations take time; forcing a 14-day closeout will lead to superficial box-ticking rather than genuine root cause discovery.",
            "rationale_and_changes": "Evaluate accommodating 30 days in AMC with 90-day final report envelope.",
            "overall_id": "OVR-001",
        },
        {
            "comment_id": "CMT-002",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 7(2)",
            "page": "22",
            "original_text": "Aerodrome operators shall achieve full compliance with Articles 4 and 5 within 6 months from the date of entry into force.",
            "comment_text": "A 6-month transition period across the entire network is unachievable due to software procurement and procurement cycles for safety management databases.",
            "comment_type": "Schedule / Transition",
            "importance": "High",
            "proposed_text": "Extend transition period in Article 7(2) from 6 months to 18 months.",
            "stakeholder_category": "Aerodrome Operator",
            "organisation_name": "ACI Europe (Airports Council International)",
            "stakeholder_name": "ACI Europe (Airports Council International)",
            "stakeholder_group": "Aerodrome Operator",
            "target_section": "Article 7(2)",
            "af_cba": "AF: Risk of widespread non-compliance at entry into force across 450 airports.",
            "response_to_comment": "In Consideration",
            "rationale": "Airport operators need sufficient budget lead time to integrate reporting tools with ground handling contractors.",
            "rationale_and_changes": "Phased implementation proposal being drafted.",
            "overall_id": "OVR-002",
        },
        {
            "comment_id": "CMT-003",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 9",
            "page": "31",
            "original_text": "All safety databases containing occurrence reports must comply with Commission Implementing Regulation (EU) 2023/203 (Part-IS)...",
            "comment_text": "We strongly support the integration of Part-IS cybersecurity principles, but must stress that de-identification of pilot reporter details is an inviolable prerequisite for Just Culture.",
            "comment_type": "Legal / Just Culture",
            "importance": "Critical",
            "proposed_text": "Add paragraph 9(2): 'Reporter identity shall be cryptographically pseudonymized prior to inter-agency data sharing.'",
            "stakeholder_category": "Pilots / Crew / Professional Union",
            "organisation_name": "ECA (European Cockpit Association)",
            "stakeholder_name": "ECA (European Cockpit Association)",
            "stakeholder_group": "Pilots / Crew / Professional Union",
            "target_section": "Article 9",
            "af_cba": "AF: Preserving trust in reporting channels directly prevents fatal accidents.",
            "response_to_comment": "Flagged for Legal Review",
            "rationale": "Without strict identity protection guarantees, voluntary reporting rates by flight crew will drop precipitously.",
            "rationale_and_changes": "Coordinate with Data Protection Officer regarding GDPR and Part-IS alignment.",
            "overall_id": "OVR-003",
        },
        {
            "comment_id": "CMT-004",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 7(3)",
            "page": "23",
            "original_text": "For aerodromes handling fewer than 2 million passengers annually, an additional grace period of 3 months may be granted by the Competent Authority.",
            "comment_text": "The passenger threshold of 2 million is appropriate, but the Competent Authority must have clear objective criteria to evaluate whether a 3-month grace period should be authorized.",
            "comment_type": "Regulatory / Enforcement",
            "importance": "Medium",
            "proposed_text": "Include AMC/GM defining the criteria under which National Authorities may grant grace periods.",
            "stakeholder_category": "National Aviation Authority (NAA) / Regulator",
            "organisation_name": "DGAC France",
            "stakeholder_name": "DGAC France",
            "stakeholder_group": "National Aviation Authority (NAA) / Regulator",
            "target_section": "Article 7(3)",
            "af_cba": "CBA: Standardized criteria saves €300k in audit appeals.",
            "response_to_comment": "Draft Response Prepared",
            "rationale": "Ensures uniform enforcement and level playing field across Member States.",
            "rationale_and_changes": "AMC criteria to be published alongside final ED Decision.",
            "overall_id": "OVR-004",
        },
        {
            "comment_id": "CMT-005",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 4(3)",
            "page": "15",
            "original_text": "Where a report identifies a latent hazard affecting runway operations, immediate mitigation measures shall be coordinated with the appropriate Air Traffic Control (ATC) unit.",
            "comment_text": "We welcome the requirement to coordinate latent runway hazards directly with ATC units, which aligns with ICAO Global Aviation Safety Plan priorities.",
            "comment_type": "Support / Endorsement",
            "importance": "Low",
            "proposed_text": "",
            "stakeholder_category": "Manufacturer / OEM",
            "organisation_name": "Airbus Commercial Aviation",
            "stakeholder_name": "Airbus Commercial Aviation",
            "stakeholder_group": "Manufacturer / OEM",
            "target_section": "Article 4(3)",
            "af_cba": "AF: Global interoperability benefit.",
            "response_to_comment": "Noted with Appreciation",
            "rationale": "Prompt ATC notification significantly reduces risk of runway contamination incidents.",
            "rationale_and_changes": "Retain baseline text with editorial polish.",
            "overall_id": "OVR-005",
        },
        {
            "comment_id": "CMT-006",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 7(3)",
            "page": "23",
            "original_text": "For aerodromes handling fewer than 2 million passengers annually, an additional grace period of 3 months may be granted by the Competent Authority.",
            "comment_text": "The 3-month grace period for small airports is completely inadequate. Small aerodromes operating on seasonal schedules require at least a 12-month exemption.",
            "comment_type": "Proportionality / Exemption",
            "importance": "Critical",
            "proposed_text": "Increase small operator grace period from 3 months to 12 months in Article 7(3).",
            "stakeholder_category": "Aerodrome Operator",
            "organisation_name": "Regional Airports Association",
            "stakeholder_name": "Regional Airports Association",
            "stakeholder_group": "Aerodrome Operator",
            "target_section": "Article 7(3)",
            "af_cba": "CBA: Prevents potential temporary closure of regional feeder links.",
            "response_to_comment": "Under Technical Assessment",
            "rationale": "Small regional aerodromes operate with minimal staffing and cannot implement sophisticated SMS software in one quarter.",
            "rationale_and_changes": "Assessing tiered grace period based on passenger volumes.",
            "overall_id": "OVR-006",
        },
        {
            "comment_id": "CMT-007",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 4(1)",
            "page": "14",
            "original_text": "The aerodrome operator shall establish a voluntary and mandatory safety occurrence reporting system accessible to all personnel, ground handlers, and air operators.",
            "comment_text": "Ground handlers should not operate isolated reporting databases. Aerodrome operators must establish a unified single-window portal.",
            "comment_type": "Technical / Architecture",
            "importance": "High",
            "proposed_text": "Insert in Article 4(1): 'The aerodrome operator shall host a unified single-window portal accessible by all contracted ground service providers.'",
            "stakeholder_category": "Air Operator / Airline",
            "organisation_name": "Ryanair DAC",
            "stakeholder_name": "Ryanair DAC",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(1)",
            "af_cba": "CBA: Eliminates €1.1M in redundant airline crew data-entry hours.",
            "response_to_comment": "In Consideration",
            "rationale": "Airlines currently encounter fragmented reporting forms at every different European airport.",
            "rationale_and_changes": "Recommend GM describing API specifications for single-window reporting.",
            "overall_id": "OVR-007",
        },
        {
            "comment_id": "CMT-008",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 4(3)",
            "page": "15",
            "original_text": "Where a report identifies a latent hazard affecting runway operations, immediate mitigation measures shall be coordinated with the appropriate Air Traffic Control (ATC) unit.",
            "comment_text": "Please clarify what communication protocol should be utilized between aerodrome operations and ATC tower when logging latent hazard mitigations.",
            "comment_type": "Operational / Clarification",
            "importance": "Medium",
            "proposed_text": "Develop accompanying GM detailing standard coordination channels and logging formats.",
            "stakeholder_category": "Air Navigation Service Provider (ANSP)",
            "organisation_name": "CANSO (Civil Air Navigation Services Organisation)",
            "stakeholder_name": "CANSO (Civil Air Navigation Services Organisation)",
            "stakeholder_group": "Air Navigation Service Provider (ANSP)",
            "target_section": "Article 4(3)",
            "af_cba": "AF: Eliminates operational misunderstanding on live runways.",
            "response_to_comment": "Draft Response Prepared",
            "rationale": "Ambiguity over formal vs tactical coordination could create confusion during live runway operations.",
            "rationale_and_changes": "Incorporate standard ATC coordination format into GM1 ADR.OPS.B.015.",
            "overall_id": "OVR-008",
        },
        {
            "comment_id": "CMT-009",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 1",
            "page": "4",
            "original_text": "This Regulation establishes harmonized requirements for aerodrome certificate holders regarding the management of operational safety risks...",
            "comment_text": "Glider fields and grass airstrips should be categorically excluded from the scope of this Regulation.",
            "comment_type": "Scope / Exemption",
            "importance": "High",
            "proposed_text": "Amend Article 1 to specify: 'This Regulation does not apply to aerodromes exclusively accommodating non-powered aircraft.'",
            "stakeholder_category": "General Aviation / Aerial Work",
            "organisation_name": "European Gliding Union",
            "stakeholder_name": "European Gliding Union",
            "stakeholder_group": "General Aviation / Aerial Work",
            "target_section": "Article 1",
            "af_cba": "CBA: Unnecessary administrative burden on recreational clubs.",
            "response_to_comment": "Under Technical Assessment",
            "rationale": "Disproportionate administrative burden on non-commercial sporting aviation.",
            "rationale_and_changes": "Confirm that Basic Regulation Article 2 already exempts non-EASA aerodromes.",
            "overall_id": "OVR-009",
        },
        {
            "comment_id": "CMT-010",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 4(2)",
            "page": "14",
            "original_text": "Reports received shall be investigated within 14 calendar days of receipt.",
            "comment_text": "We concur with Lufthansa regarding the 14-day timeline. 30 days is standard across ICAO Annex 13 protocols.",
            "comment_type": "Technical / Change Request",
            "importance": "Critical",
            "proposed_text": "Replace '14 calendar days' with '30 calendar days'.",
            "stakeholder_category": "Air Operator / Airline",
            "organisation_name": "EasyJet Airline Company",
            "stakeholder_name": "EasyJet Airline Company",
            "stakeholder_group": "Air Operator / Airline",
            "target_section": "Article 4(2)",
            "af_cba": "AF: International regulatory harmonization with UK CAA & ICAO.",
            "response_to_comment": "Under Technical Assessment",
            "rationale": "Harmonization with international occurrence investigation practices.",
            "rationale_and_changes": "Reviewing coalition feedback on Article 4(2).",
            "overall_id": "OVR-010",
        },
        {
            "comment_id": "CMT-011",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 9",
            "page": "31",
            "original_text": "All safety databases containing occurrence reports must comply with Commission Implementing Regulation (EU) 2023/203 (Part-IS)...",
            "comment_text": "Cross-reference to Commission Implementing Regulation (EU) 2023/203 is supported, but verify that definition of 'sensitive safety information' matches Regulation (EU) 376/2014.",
            "comment_type": "Legal / Harmonization",
            "importance": "Medium",
            "proposed_text": "Ensure alignment with Article 15 of Regulation (EU) 376/2014.",
            "stakeholder_category": "National Aviation Authority (NAA) / Regulator",
            "organisation_name": "Austro Control",
            "stakeholder_name": "Austro Control",
            "stakeholder_group": "National Aviation Authority (NAA) / Regulator",
            "target_section": "Article 9",
            "af_cba": "AF: Legal certainty during cross-border regulatory oversight.",
            "response_to_comment": "Draft Response Prepared",
            "rationale": "Avoid legal conflict between cybersecurity obligations and occurrence reporting protections.",
            "rationale_and_changes": "Added explicit cross-reference in Recital 12.",
            "overall_id": "OVR-011",
        },
        {
            "comment_id": "CMT-012",
            "document_title": "NPA 2024-05: Safety Management Systems in Aerodrome Operations",
            "chapter_section": "Article 7",
            "page": "22",
            "original_text": "Aerodrome operators shall achieve full compliance with Articles 4 and 5 within 6 months...",
            "comment_text": "Business aviation operators need clear guidance on how ad-hoc non-scheduled charter flights interact with aerodrome hazard systems.",
            "comment_type": "Operational / Guidance",
            "importance": "Medium",
            "proposed_text": "Provide GM on transient operator access to reporting tools.",
            "stakeholder_category": "General Aviation / Aerial Work",
            "organisation_name": "European Business Aviation Association (EBAA)",
            "stakeholder_name": "European Business Aviation Association (EBAA)",
            "stakeholder_group": "General Aviation / Aerial Work",
            "target_section": "Article 7",
            "af_cba": "CBA: Reduces onboarding delay for unscheduled medical and cargo flights.",
            "response_to_comment": "In Consideration",
            "rationale": "Non-base operators need instant guest access to log aerodrome surface issues.",
            "rationale_and_changes": "Drafting GM text for transient user access.",
            "overall_id": "OVR-012",
        },
        {
            "comment_id": "CMT-013",
            "document_title": "NPA 2024-05 Annex I - Technical Specifications",
            "chapter_section": "Annex I, Part-OPS.040 Runway De-icing Protocols",
            "page": "88",
            "original_text": "Runway friction measurement shall be calibrated at temperature intervals not exceeding 3 degrees Celsius during active precipitation.",
            "comment_text": "The requirement for 3-degree calibration intervals during freezing precipitation is technically infeasible for automated surface decelerometers currently deployed in northern European hubs.",
            "comment_type": "Technical / Change Request",
            "importance": "High",
            "proposed_text": "Allow manufacturer-specified calibration bands up to 5 degrees Celsius.",
            "stakeholder_category": "Aerodrome Operator",
            "organisation_name": "Munich Airport International",
            "stakeholder_name": "Munich Airport International",
            "stakeholder_group": "Aerodrome Operator",
            "target_section": "Annex I, Part-OPS.040 Runway De-icing Protocols",
            "af_cba": "CBA: Retooling fleet of 18 friction vehicles would cost €850k per airport.",
            "response_to_comment": "Pending Review",
            "rationale": "Sensor drift specifications from certified equipment manufacturers allow 5-degree increments without degrading friction index reliability.",
            "rationale_and_changes": "Awaiting technical review from aerodrome standards working group.",
            "overall_id": "OVR-013",
        }
    ]

    required_text_blocks = build_required_text_blocks(sample_csv_data, doc_sections)
    enriched = enrich_feedback_comments(sample_csv_data, doc_sections)
    metrics = compute_consultation_metrics(enriched)
    organisations_analysis = compute_organisations_analysis(enriched)

    save_consultation_session(
        consultation_id=consultation_id,
        title="NPA 2024-05: Safety Management Systems in Aerodrome Operations",
        description="Public consultation on draft rules updating aerodrome safety risk management, occurrence investigation timelines, and Part-IS cybersecurity coordination.",
        domain="Aerodromes & Air Traffic Management",
        documents=docs_payload,
        comments=enriched,
        metrics=metrics,
        field_mapping={k: k for k in [
            "ID", "Please select the document title from the drop down below",
            "Chapter/Section", "Page", "Original text in document", "Comment",
            "Type of Comment", "Importance", "Proposed new text (required in case of change request)",
            "Stakeholder Category", "Organisation Name", "AF / CBA", "Response to comment",
            "Rationale and resulting changes (if applicable)", "Overall ID#"
        ]},
        required_text_blocks=required_text_blocks,
        organisations_analysis=organisations_analysis
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


@router.get("/session/{consultation_id}/synthesis", tags=["CONSULTATION"])
def api_get_consultation_synthesis(consultation_id: str):
    """
    Computes a complete multi-level synthesis of stakeholder comments and concerns vs consulted text:
    - General assessment of stakeholder sentiment overall and macro dynamics
    - Per stakeholder type synthesis
    - Per category / theme synthesis
    - Per consulted section synthesis
    - Per comment vs consulted text synthesis
    """
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Consultation session '{consultation_id}' not found.")
    try:
        bundle = compute_full_consultation_synthesis(sess)
        return bundle
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute consultation synthesis: {e}")


@router.post("/session/{consultation_id}/synthesis/generate", tags=["CONSULTATION"])
def api_generate_deep_synthesis(consultation_id: str, req: DeepSynthesisRequest):
    """
    Generates AI-assisted narrative and structured synthesis at any specified scope:
    'overall', 'stakeholder_type', 'category', 'section', or 'comment'.
    """
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Consultation session '{consultation_id}' not found.")
    try:
        res = generate_ai_deep_synthesis(
            session=sess,
            scope=req.scope,
            target_id=req.target_id,
            provider=req.provider or "local"
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate deep synthesis: {e}")


@router.get("/session/{consultation_id}/synthesis/export", tags=["CONSULTATION"])
def api_export_consultation_synthesis(consultation_id: str, format: Optional[str] = "markdown"):
    """
    Exports a comprehensive regulatory consultation synthesis report as Markdown or JSON,
    ready for review by rulemaking committees and regulatory directorates.
    """
    sess = get_consultation_session(consultation_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Consultation session not found.")

    bundle = compute_full_consultation_synthesis(sess)
    if format == "json":
        return Response(
            content=json.dumps(bundle, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={consultation_id}_synthesis_report.json"}
        )

    # Generate structured Markdown report
    ov = bundle["overall_assessment"]
    md = [
        f"# Regulatory Consultation Synthesis Report: {sess.get('title', 'Consultation')}",
        f"**Consultation ID:** `{consultation_id}`  ",
        f"**Domain:** {sess.get('domain', 'Aviation Safety')}  ",
        f"**Total Comments:** {ov.get('total_comments', 0)} | **Distinct Stakeholders:** {ov.get('total_stakeholders', 0)}  ",
        f"**General Sentiment Assessment:** {ov.get('overall_sentiment_label', 'Neutral')} (Score: {ov.get('overall_sentiment_score', 0.0):+0.2f})  ",
        f"**Actionable Proposals Rate:** {ov.get('actionable_rate', 0.0)}%  ",
        "",
        "---",
        "",
        "## 1. Executive General Assessment of Stakeholder Sentiment Overall",
        ov.get("executive_summary", ""),
        "",
        "### Sentiment Distribution",
        "| Stance | Percentage |",
        "| :--- | :--- |",
    ]
    for k, v in ov.get("sentiment_breakdown_pct", {}).items():
        md.append(f"| {k} | {v}% |")

    md.extend([
        "",
        "### Top Regulatory Friction Zones vs Consulted Text",
    ])
    for fz in ov.get("top_friction_zones", []):
        md.append(f"- **{fz.get('topic')}** ({fz.get('affected_articles')}): Contested by {', '.join(fz.get('contesting_groups', []))}. *Core Issue:* {fz.get('core_issue')}")

    md.extend([
        "",
        "### Areas of Broad Consensus",
    ])
    for c in ov.get("areas_of_broad_consensus", []):
        md.append(f"- {c}")

    md.extend([
        "",
        "### Stakeholder Coalition Dynamics & Cross-Sector Clashes",
    ])
    for co in ov.get("stakeholder_coalition_dynamics", []):
        md.append(f"- **{co.get('group')}**: {co.get('stance')} *(Friction with: {co.get('friction_with')})*")

    md.extend([
        "",
        "### Rulemaker Deliberation Roadmap",
    ])
    for r in ov.get("rulemaker_action_roadmap", []):
        md.append(f"- {r}")

    md.extend([
        "",
        "---",
        "",
        "## 2. Per Stakeholder Type Synthesis vs Consulted Text",
    ])
    for st in bundle.get("stakeholder_type_synthesis", []):
        md.append(f"### Sector: {st.get('stakeholder_group')} ({st.get('comment_count')} comments, Avg Sentiment: {st.get('average_sentiment_score'):+0.2f})")
        md.append(f"{st.get('collective_stance_summary')}\n")
        md.append(f"**Cross-Sector Tensions:** {st.get('cross_sector_alignment_and_conflicts')}\n")
        md.append(f"**Rulemaker Advice:** {st.get('rulemaker_deliberation_advice')}\n")

    md.extend([
        "",
        "---",
        "",
        "## 3. Per Category / Theme Synthesis vs Consulted Text",
    ])
    for cat in bundle.get("category_synthesis", []):
        md.append(f"### Theme: {cat.get('category_name')} ({cat.get('comment_count')} comments, Avg Sentiment: {cat.get('average_sentiment_score'):+0.2f})")
        md.append(f"{cat.get('thematic_conflict_summary')}\n")
        md.append(f"**Implicated Sections:** {', '.join(cat.get('implicated_sections', []))}\n")
        md.append("**Policy Trade-offs & Drafting Remedies:**")
        for rem in cat.get("policy_tradeoffs_and_remedies", []):
            md.append(f"- {rem}")
        md.append("")

    md.extend([
        "",
        "---",
        "",
        "## 4. Per Consulted Section Synthesis",
    ])
    for sec in bundle.get("section_synthesis", []):
        md.append(f"### Section: {sec.get('section_title')} ({sec.get('comment_count')} comments, Avg Sentiment: {sec.get('average_sentiment_score'):+0.2f})")
        md.append(f"{sec.get('synthesized_feedback_vs_text')}\n")
        md.append(f"**Deliberation Guidance:** {sec.get('deliberation_guidance')}\n")

    md_content = "\n".join(md)
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={consultation_id}_synthesis_report.md"}
    )


@router.delete("/session/{consultation_id}", tags=["CONSULTATION"])
def api_delete_consultation(consultation_id: str):
    """Deletes a consultation session and associated records."""
    success = delete_consultation_session(consultation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Consultation session not found or already deleted.")
    return {"status": "success", "consultation_id": consultation_id, "deleted": True}
