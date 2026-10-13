"""
upload.py - FastAPI Endpoints for Document Upload, Duplicate/Update Comparison & Ingestion.

Supports:
- Analyzing uploaded documents (format detection: EU/EASA/FAA XML vs User Skybrary).
- Search and compare for duplicates or updates with executive control (supersede / suppress).
- Full ingestion into SQLite, FAISS, and FTS5 search index.
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ingestion.core.config import settings
from ingestion.user_docs import (
    DocFormat,
    detect_document_format,
    extract_user_document,
    search_and_compare_document,
    ingest_user_document,
)

router = APIRouter()

# Staging directory for uploaded documents pending executive action
STAGING_DIR = settings.DATA_DIR / "user_docs" / "staging"
ARCHIVE_DIR = settings.DATA_DIR / "user_docs" / "archive"
STAGING_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


class ComparisonMatchItem(BaseModel):
    document_id: str
    title: str
    source: str
    date: Optional[str] = None
    is_active: bool = True
    superseded_by: Optional[str] = None
    similarity_score: float
    match_type: str  # "exact_duplicate", "update", "similar"
    comparison_details: str


class UploadAnalysisResponse(BaseModel):
    staging_id: str
    filename: str
    format: str
    workflow: str
    category: str
    origin: str
    is_xml: bool
    detection_reason: str
    extracted_metadata: Dict[str, Any]
    has_conflict: bool
    suggested_action: str  # "none", "supersede", "suppress"
    suggested_target_doc_id: Optional[str] = None
    matches: List[ComparisonMatchItem]


class IngestConfirmRequest(BaseModel):
    staging_id: str = Field(..., description="Staging ID returned from /analyze")
    executive_action: str = Field("none", description="Action to take on matched old document: 'none', 'supersede', or 'suppress'")
    target_doc_id: Optional[str] = Field(None, description="Document ID to supersede or suppress if action is not 'none'")
    custom_title: Optional[str] = Field(None, description="Optional custom title override")
    custom_date: Optional[str] = Field(None, description="Optional custom publication date override")


class IngestionResultResponse(BaseModel):
    status: str
    document_id: str
    title: str
    source: str
    origin: str
    workflow: str
    chunks_count: int
    embeddings_count: int
    executive_action: str
    target_doc_id: Optional[str] = None
    action_summary: str


@router.post("/analyze", response_model=UploadAnalysisResponse, tags=["DOCUMENTS"])
async def api_analyze_upload(
    file: UploadFile = File(..., description="Uploaded document (PDF, XML, TXT, MD, HTML, etc.)")
):
    """
    Step 1: Analyzes an uploaded document:
    - Identifies format: EU Formex XML, EASA XML, FAA CFR XML, or User Skybrary document.
    - Extracts title, publication date, pages, and content SHA-256 hash.
    - Searches existing documents to compare for duplicates or updates.
    - Proposes executive recommendation (supersede, suppress, or keep both).
    """
    staging_id = str(uuid.uuid4())[:12]
    filename = file.filename or f"upload_{staging_id}.bin"
    staging_path = STAGING_DIR / f"{staging_id}_{filename}"

    try:
        with open(staging_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    try:
        # 1. Format Detection
        fmt_info = detect_document_format(staging_path, filename)
        doc_format = fmt_info["format"]

        # 2. Text and Metadata Extraction
        extracted_meta: Dict[str, Any] = {}
        title = ""
        date_str = None
        pub_year = None
        sha256_hash = ""
        raw_text = ""

        if doc_format in (DocFormat.EASA_XML.value, DocFormat.EU_FORMEX_XML.value, DocFormat.FAA_CFR_XML.value):
            # Specialized XML format
            with open(staging_path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read(32 * 1024)
            title = Path(filename).stem.replace("_", " ").title()
            from ingestion.user_docs.extractor import compute_sha256, extract_date_from_text
            sha256_hash = compute_sha256(staging_path)
            date_str, pub_year = extract_date_from_text(raw_text)
            extracted_meta = {
                "title": title,
                "date": date_str,
                "year": pub_year,
                "page_count": 1,
                "word_count": len(raw_text.split()),
                "sha256": sha256_hash,
                "is_xml": True
            }
        else:
            # Standard User Document
            ext_res = extract_user_document(staging_path, filename)
            title = ext_res["title"]
            date_str = ext_res["date"]
            pub_year = ext_res["year"]
            sha256_hash = ext_res["sha256"]
            raw_text = ext_res["raw_text"]
            extracted_meta = {
                "title": title,
                "date": date_str,
                "year": pub_year,
                "page_count": ext_res["page_count"],
                "word_count": ext_res["word_count"],
                "char_count": ext_res["char_count"],
                "sha256": sha256_hash,
                "is_pdf": ext_res["is_pdf"],
                "is_word": ext_res.get("is_word", False),
                "word_format": ext_res.get("word_format"),
                "author": ext_res.get("author"),
            }

        # 3. Search and Compare for Duplicates or Updates
        comparison = search_and_compare_document(
            title=title,
            raw_text=raw_text,
            sha256_hash=sha256_hash,
            date_str=date_str,
            pub_year=pub_year,
            top_k=5
        )

        return {
            "staging_id": staging_id,
            "filename": filename,
            "format": doc_format,
            "workflow": fmt_info["workflow"],
            "category": fmt_info["category"],
            "origin": fmt_info["origin"],
            "is_xml": fmt_info["is_xml"],
            "detection_reason": fmt_info["detection_reason"],
            "extracted_metadata": extracted_meta,
            "has_conflict": comparison["has_conflict"],
            "suggested_action": comparison["suggested_action"],
            "suggested_target_doc_id": comparison["suggested_target_doc_id"],
            "matches": comparison["matches"]
        }

    except Exception as e:
        if staging_path.exists():
            staging_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/confirm", response_model=IngestionResultResponse, tags=["DOCUMENTS"])
def api_confirm_ingestion(req: IngestConfirmRequest):
    """
    Step 2: Confirms and executes ingestion of the staged document.
    Applies the user's executive action:
    - 'none': Ingest new document, keep old document active.
    - 'supersede': Ingest new document, mark old document as superseded.
    - 'suppress': Ingest new document, deactivate/suppress old document.
    """
    # Locate staged file
    matches = list(STAGING_DIR.glob(f"{req.staging_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail=f"Staged file '{req.staging_id}' not found or expired.")

    staged_file = matches[0]
    original_filename = staged_file.name[len(req.staging_id) + 1:]

    try:
        # Ingest document
        res = ingest_user_document(
            file_path=staged_file,
            filename=original_filename,
            custom_title=req.custom_title,
            custom_date=req.custom_date,
            executive_action=req.executive_action,
            target_doc_id=req.target_doc_id,
            embed_vectors=True
        )

        # Move staged file to permanent archive
        archive_path = ARCHIVE_DIR / staged_file.name
        shutil.move(str(staged_file), str(archive_path))

        return res

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.post("/upload", response_model=IngestionResultResponse, tags=["DOCUMENTS"])
async def api_direct_upload(
    file: UploadFile = File(...),
    executive_action: str = Form("none", description="'none', 'supersede', or 'suppress'"),
    target_doc_id: Optional[str] = Form(None, description="Optional doc ID to supersede or suppress"),
    custom_title: Optional[str] = Form(None),
    custom_date: Optional[str] = Form(None)
):
    """
    Direct single-step upload and ingestion endpoint for programmatic / CLI use.
    """
    staging_id = str(uuid.uuid4())[:12]
    filename = file.filename or f"upload_{staging_id}.bin"
    staging_path = STAGING_DIR / f"{staging_id}_{filename}"

    try:
        with open(staging_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    try:
        res = ingest_user_document(
            file_path=staging_path,
            filename=filename,
            custom_title=custom_title,
            custom_date=custom_date,
            executive_action=executive_action,
            target_doc_id=target_doc_id,
            embed_vectors=True
        )

        archive_path = ARCHIVE_DIR / staging_path.name
        shutil.move(str(staging_path), str(archive_path))
        return res
    except Exception as e:
        if staging_path.exists():
            staging_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Direct ingestion failed: {e}")
