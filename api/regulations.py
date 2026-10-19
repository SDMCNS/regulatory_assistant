import sqlite3
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
import hashlib

from ingestion.core.config import settings
from ingestion.retrieval.keyword_search import build_fts_query
from ingestion.parsers.json_to_doc import find_json_file, render_document
from ingestion.retrieval.search_chunks import get_embeddings_batch
from ingestion.retrieval.faiss_index import LocalVectorIndex
from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.core.governance import (
    ensure_governance_schema, 
    deactivate_document, 
    activate_document, 
    get_governance_stats,
    batch_deactivate_documents,
    batch_activate_documents,
    deactivate_category,
    activate_category,
    get_skybrary_topics_stats,
    deactivate_skybrary_topic,
    activate_skybrary_topic
)
from api.utils import get_document_metadata, log_debug_info, call_unified_chat

router = APIRouter()

# In-memory cache for regulations catalog to ensure instant (< 5ms) responses
_CATALOG_CACHE: Dict[str, Any] = {
    "timestamp": 0,
    "ttl_seconds": 600,
    "items": []
}

def get_db_connection():
    db_path = settings.DATA_DIR / 'regulations' / 'sqlite' / 'chunks.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def get_document_markdown_content(document_id: str) -> str:
    """Retrieves full markdown for a document, using JSON renderer or SQLite chunk fallback."""
    json_path = find_json_file(document_id)
    if json_path:
        try:
            return render_document(json_path)
        except Exception as e:
            print(f"Error rendering JSON for {document_id}: {e}")
            
    # Fallback to assembling structured chunks from sqlite
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT title FROM documents WHERE document_id = ?", (document_id,))
            doc_row = c.fetchone()
            doc_title = doc_row["title"] if (doc_row and doc_row["title"]) else document_id
            
            c.execute("""
                SELECT chunk_id, chunk_type, section_path, section_numbers, source_text, metadata_json 
                FROM chunks 
                WHERE document_id = ? 
                ORDER BY rowid
            """, (document_id,))
            rows = c.fetchall()
            if not rows:
                return ""

            md_parts = [f"# {doc_title}\n\n*Regulatory Instrument ID: {document_id}*"]
            for r in rows:
                chunk_id = r["chunk_id"]
                chunk_type = r["chunk_type"] or "section"
                source_text = (r["source_text"] or "").strip()
                
                sec_path = []
                if r["section_path"]:
                    try:
                        sec_path = json.loads(r["section_path"])
                    except Exception:
                        pass
                        
                sec_numbers = []
                if r["section_numbers"]:
                    try:
                        sec_numbers = json.loads(r["section_numbers"])
                    except Exception:
                        pass
                        
                sec_title = sec_path[-1] if sec_path else (sec_numbers[0] if sec_numbers else chunk_id)
                chunk_meta = {
                    "id": chunk_id,
                    "title": sec_title,
                    "type": chunk_type,
                    "section_numbers": sec_numbers,
                    "section_path": sec_path
                }
                meta_json = json.dumps(chunk_meta, ensure_ascii=False)
                break_token = f"\n\n---\n<!-- SECTION_BREAK {meta_json} -->\n\n"
                sec_body = f"### {sec_title}\n\n{source_text}" if not source_text.startswith("#") else source_text
                md_parts.append(break_token + sec_body)
                
            return "".join(md_parts)
    except Exception as e:
        print(f"Error assembling chunks from sqlite for {document_id}: {e}")
        
    return ""

def extract_title_years_and_flags(title: str, date: str, doc_id: str, source: str, origin: str):
    """
    Extracts all 4-digit years and recognizes obsolescence pattern indicators from title and metadata.
    """
    text = f"{title} {doc_id}".lower()

    # 1. Year detection
    years = []
    if date:
        m = re.search(r'\b(19[7-9]\d|20[0-3]\d)\b', str(date))
        if m:
            years.append(int(m.group(1)))

    for m in re.finditer(r'\b(19[7-9]\d|20[0-3]\d)\b', title):
        years.append(int(m.group(1)))

    years = sorted(list(set(years)))
    primary_year = years[-1] if years else None

    # 2. Pattern recognition flags
    flags = []
    if primary_year:
        if primary_year <= 2014:
            flags.append("legacy_pre_2015")
        elif primary_year <= 2019:
            flags.append("aging_2015_2019")
        elif primary_year <= 2024:
            flags.append("review_2020_2024")
        else:
            flags.append("recent_2025_plus")

    if any(k in text for k in ["draft", "proposed", "interim", "provisional", "preliminary"]):
        flags.append("draft")

    if any(k in text for k in ["superseded", "repealed", "withdrawn", "obsolete", "revoked", "replaced", "former", "legacy"]):
        flags.append("superseded_keyword")

    if re.search(r'\b(issue [01]|amendment [01]|rev [0a]|revision [01])\b', text):
        flags.append("early_revision")

    if any(k in text for k in ["216/2008", "1592/2002", "jar-", "jar 25", "jar ops", "jar-fcl"]):
        flags.append("known_repealed")

    if any(k in text for k in ["covid", "pandemic", "temporary exemption"]):
        flags.append("covid_temporary")

    if origin == "skybrary" and primary_year and primary_year <= 2018:
        flags.append("old_skybrary")

    return years, primary_year, flags


def load_cached_catalog() -> List[Dict[str, Any]]:
    global _CATALOG_CACHE
    now = time.time()
    if _CATALOG_CACHE["items"] and (now - _CATALOG_CACHE["timestamp"]) < _CATALOG_CACHE["ttl_seconds"]:
        return _CATALOG_CACHE["items"]
        
    items = []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.document_id,
                d.title,
                d.date,
                d.source,
                d.metadata_json,
                COALESCE(d.is_active, 1) as is_active,
                d.deactivation_reason,
                d.deactivated_at,
                d.superseded_by,
                COUNT(c.chunk_id) as chunk_count
            FROM documents d
            INNER JOIN chunks c ON d.document_id = c.document_id
            GROUP BY d.document_id
            ORDER BY chunk_count DESC
        """)
        rows = cursor.fetchall()
        
        # Build mapping for parent titles for ANNEX documents
        parent_titles = {}
        for r in rows:
            doc_id = r["document_id"]
            title = (r["title"] or "").strip()
            if title and not title.upper().startswith("ANNEX") and not title.upper().startswith("APPENDIX"):
                prefix = doc_id.split(".")[0]
                if prefix not in parent_titles:
                    parent_titles[prefix] = title

        # Fetch qualifier counts per parent regulation
        qualifier_counts = {}
        try:
            cursor.execute("""
                SELECT parent_regulation_id, target_regulation_ref, COUNT(*) 
                FROM qualifiers 
                GROUP BY parent_regulation_id, target_regulation_ref
            """)
            for p_id, target_ref, q_count in cursor.fetchall():
                if p_id:
                    qualifier_counts[p_id] = qualifier_counts.get(p_id, 0) + q_count
                if target_ref:
                    clean_ref = target_ref.replace("Regulation", "").strip()
                    qualifier_counts[clean_ref] = qualifier_counts.get(clean_ref, 0) + q_count
        except Exception:
            pass

        # Fetch stakeholder domains per document
        doc_stakeholders = {}
        try:
            cursor.execute("""
                SELECT document_id, primary_stakeholder 
                FROM document_stakeholder_scores
            """)
            for d_id, p_stk in cursor.fetchall():
                if d_id:
                    doc_stakeholders[d_id] = p_stk
        except Exception:
            pass

        for r in rows:
            doc_id = r["document_id"]
            raw_title = (r["title"] or "").strip()
            date = r["date"] or ""
            source = r["source"] or ""
            chunk_count = r["chunk_count"]
            
            clean_title = raw_title
            # Enrich title if it's an ANNEX or empty
            if not clean_title or clean_title.upper().startswith("ANNEX") or clean_title.upper().startswith("APPENDIX"):
                prefix = doc_id.split(".")[0]
                parent = parent_titles.get(prefix)
                if parent:
                    clean_title = f"{parent} — {raw_title}" if raw_title else parent
                elif not clean_title:
                    clean_title = doc_id
                    
            # Determine origin
            doc_low = (doc_id + " " + clean_title).lower()
            if source == "SKYBRARY" or doc_id.startswith("SKYBRARY_"):
                origin = "skybrary"
            elif doc_id.startswith("NOTE_") or source in ("Note", "UserNote"):
                origin = "note"
            elif source in ("USER", "User Supplied") or doc_id.startswith("USER_"):
                origin = "user"
            elif source == "FAA XML" or doc_id.startswith("FAA_") or "14 cfr" in doc_low:
                origin = "faa"
            elif source in ("Manual", "Custom") or doc_id.startswith("MANUAL_"):
                origin = "manual"
            elif "easy access" in doc_low or "cs-" in doc_low or "amc" in doc_low:
                origin = "easa"
            else:
                origin = "eu"
                
            meta_dict = {}
            if r["metadata_json"]:
                try:
                    meta_dict = json.loads(r["metadata_json"])
                    if meta_dict.get("origin") == "note":
                        origin = "note"
                    elif meta_dict.get("origin") == "user":
                        origin = "user"
                except Exception:
                    pass

            celex = meta_dict.get("celex")
            doc_num = meta_dict.get("doc_number")
            q_cnt = qualifier_counts.get(doc_id, 0) or (qualifier_counts.get(celex, 0) if celex else 0) or (qualifier_counts.get(doc_num, 0) if doc_num else 0)

            stk = doc_stakeholders.get(doc_id, None)

            # Subtopic (especially for Skybrary categories)
            subtopic = None
            if origin == "skybrary":
                subtopic = (meta_dict.get("category") or "").strip() or "Uncategorized"
            elif meta_dict.get("category"):
                subtopic = str(meta_dict.get("category")).strip()

            # Extract years and obsolescence pattern tags
            det_years, prim_year, obs_flags = extract_title_years_and_flags(clean_title, date, doc_id, source, origin)

            items.append({
                "document_id": doc_id,
                "title": clean_title,
                "raw_title": raw_title,
                "date": date,
                "origin": origin,
                "subtopic": subtopic,
                "source": source,
                "chunk_count": chunk_count,
                "qualifier_count": q_cnt,
                "primary_stakeholder": stk,
                "metadata": meta_dict,
                "is_active": bool(r["is_active"]),
                "deactivation_reason": r["deactivation_reason"],
                "deactivated_at": r["deactivated_at"],
                "superseded_by": r["superseded_by"],
                "detected_years": det_years,
                "primary_year": prim_year,
                "obsolescence_flags": obs_flags
            })
            
    _CATALOG_CACHE["items"] = items
    _CATALOG_CACHE["timestamp"] = now
    return items


# -------------------------------------------------------------
# Models
# -------------------------------------------------------------

class RegulationItem(BaseModel):
    document_id: str
    title: str
    raw_title: Optional[str] = None
    date: Optional[str] = None
    origin: str
    subtopic: Optional[str] = None
    source: Optional[str] = None
    chunk_count: int
    qualifier_count: int = 0
    primary_stakeholder: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: bool = True
    deactivation_reason: Optional[str] = None
    deactivated_at: Optional[str] = None
    superseded_by: Optional[str] = None
    detected_years: List[int] = []
    primary_year: Optional[int] = None
    obsolescence_flags: List[str] = []

class CatalogResponse(BaseModel):
    total: int
    filtered_count: int
    regulations: List[RegulationItem]

class BatchDownloadRequest(BaseModel):
    document_ids: List[str] = Field(..., min_items=1, description="List of document IDs to fetch/download")

class DownloadedDocItem(BaseModel):
    document_id: str
    title: str
    origin: str
    markdown_doc: str
    metadata: Dict[str, Any]
    chunk_count: int

class BatchDownloadResponse(BaseModel):
    count: int
    documents: List[DownloadedDocItem]

class WorkspaceFtsRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Keywords or search phrase to find across workspace documents")
    document_ids: List[str] = Field(..., min_items=1, description="Selected workspace document IDs")
    top_k_per_doc: int = Field(default=8, ge=1, le=50, description="Max chunks to return per document")
    total_top_k: int = Field(default=50, ge=1, le=200, description="Max total chunks across all documents")

class ChunkMatch(BaseModel):
    chunk_id: str
    document_id: str
    section_path: List[str]
    section_title: str
    source_text: str
    text: Optional[str] = None
    snippet: str
    rank: float
    score: float
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None

class DocumentOverlapDetail(BaseModel):
    document_id: str
    title: str
    origin: str
    chunk_count: int
    match_count: int
    best_score: float
    has_match: bool
    top_matches: List[ChunkMatch]

class OverlapSummary(BaseModel):
    query: str
    total_documents_queried: int
    total_documents_matched: int
    overlap_rate: float
    all_documents_matched: bool
    total_chunks_matched: int
    matched_document_ids: List[str]
    shared_search_terms: List[str]
    document_summaries: List[Dict[str, Any]]

class WorkspaceFtsResponse(BaseModel):
    query: str
    fts_expression: str
    total_matches: int
    overlap_summary: OverlapSummary
    results_by_document: Dict[str, List[ChunkMatch]]
    all_results: List[ChunkMatch]

class DeactivateDocumentRequest(BaseModel):
    reason: str = Field(..., min_length=2, description="Reason for deactivating / superseding this document")
    superseded_by: Optional[str] = Field(None, description="Optional ID or title of the superseding regulation")

class BatchDeactivateRequest(BaseModel):
    document_ids: List[str] = Field(..., min_items=1, description="List of document IDs to batch deactivate")
    reason: str = Field(..., min_length=2, description="Common reason for deactivation / suppression")
    superseded_by: Optional[str] = Field(None, description="Optional ID or title of superseding regulation")

class BatchActivateRequest(BaseModel):
    document_ids: List[str] = Field(..., min_items=1, description="List of document IDs to batch reactivate")

class CategoryDeactivateRequest(BaseModel):
    reason: str = Field(..., min_length=2, description="Reason for suppressing entire category")
    superseded_by: Optional[str] = Field(None, description="Optional ID or title of superseding regulation")

class SkybraryTopicDeactivateRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Name of the SKYbrary subtopic to suppress")
    reason: str = Field(..., min_length=2, description="Reason for suppressing this SKYbrary subtopic")
    superseded_by: Optional[str] = Field(None, description="Optional ID or title of superseding guidance")

class SkybraryTopicActivateRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Name of the SKYbrary subtopic to reactivate")

class GovernanceStatsResponse(BaseModel):
    total_documents: int
    active_documents: int
    deactivated_documents: int
    total_chunks: int
    active_chunks: int
    forgotten_chunks: int
    category_stats: Optional[Dict[str, Dict[str, int]]] = None
    recent_logs: List[Dict[str, Any]]


class CandidateTitleItem(BaseModel):
    document_id: str
    title: str
    origin: Optional[str] = None
    subtopic: Optional[str] = None
    year: Optional[int] = None

class AiObsolescenceScanRequest(BaseModel):
    documents: List[CandidateTitleItem] = Field(..., max_items=150, description="Batch of document titles to analyze for obsolescence")
    focus: Optional[str] = Field("all", description="'all', 'older_than_2020', 'review_2020_2024', 'skybrary', 'easa_eu'")
    provider: Optional[str] = Field("local", description="LLM provider: 'local' or 'gemini'")
    gemini_api_key: Optional[str] = Field(None, description="Optional Gemini API key")
    gemini_model: Optional[str] = Field("gemini-3.5-flash", description="Optional Gemini model name")

class ObsolescenceCandidateFinding(BaseModel):
    document_id: str
    title: str
    is_suspect_obsolete: bool = True
    confidence: str # "HIGH", "MEDIUM", "LOW"
    likely_status: Optional[str] = "OBSOLETE"
    detected_year: Optional[int] = None
    reason: str
    suggested_action: str
    superseded_by: Optional[str] = None

class AiObsolescenceScanResponse(BaseModel):
    total_scanned: int
    flagged_count: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    summary: str
    findings: List[ObsolescenceCandidateFinding]


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------

@router.get("/catalog", response_model=CatalogResponse, tags=["REGULATIONS"])
def api_get_regulations_catalog(
    query: Optional[str] = Query(None, description="Title-level search query (searches title and document ID)"),
    origin: Optional[str] = Query("all", description="Filter by origin: 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', 'note', or 'user'"),
    subtopic: Optional[str] = Query(None, description="Filter by subtopic / category (e.g. for Skybrary subtopics)"),
    status: Optional[str] = Query("all", description="Filter by status: 'all', 'active', 'deactivated'"),
    stakeholder: Optional[str] = Query(None, description="Filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'"),
    year_min: Optional[int] = Query(None, description="Minimum publication or referenced year (e.g. 2020)"),
    year_max: Optional[int] = Query(None, description="Maximum publication or referenced year (e.g. 2024)"),
    pattern_flag: Optional[str] = Query(None, description="Filter by obsolescence pattern: 'legacy_pre_2015', 'aging_2015_2019', 'review_2020_2024', 'draft', 'superseded_keyword', 'early_revision', 'known_repealed', 'covid_temporary', 'old_skybrary'"),
    fuzzy: Optional[bool] = Query(False, description="Enable fuzzy / smart title & year matching"),
    sort_by: Optional[str] = Query("chunks", description="Sort by 'chunks', 'title', or 'date'"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    limit: Optional[int] = Query(500, ge=1, le=2000, description="Max regulations to return"),
    offset: Optional[int] = Query(0, ge=0, description="Pagination offset")
):
    """
    Returns the comprehensive catalog of European aviation regulations indexed in the database.
    Supports title-level search, origin filtering (EASA vs EU), subtopic filtering (Skybrary categories), status filtering (active vs deactivated), stakeholder domain filtering, year ranges (e.g. 2020-2024), obsolescence patterns, and sorting.
    """
    # Safely extract values if called directly outside FastAPI
    q_clean = query.strip() if (isinstance(query, str) and query.strip()) else None
    origin_str = (origin.lower() if isinstance(origin, str) else "all")
    sub_clean = (subtopic.lower().strip() if isinstance(subtopic, str) and subtopic.strip() else None)
    status_str = (status.lower() if isinstance(status, str) else "all")
    stk_clean = (stakeholder.lower().strip() if isinstance(stakeholder, str) and stakeholder.strip() else None)
    sort_by_str = (sort_by.lower() if isinstance(sort_by, str) else "chunks")
    sort_order_str = (sort_order.lower() if isinstance(sort_order, str) else "desc")
    limit_val = limit if isinstance(limit, int) else 500
    offset_val = offset if isinstance(offset, int) else 0

    all_items = load_cached_catalog()
    filtered = all_items
    
    # 1. Filter by status (active vs deactivated)
    if status_str == "active":
        filtered = [item for item in filtered if item.get("is_active", True) is True]
    elif status_str == "deactivated":
        filtered = [item for item in filtered if item.get("is_active", True) is False]

    # 2. Filter by origin
    if origin_str != "all":
        filtered = [item for item in filtered if item["origin"] == origin_str]

    # 2b. Filter by subtopic (e.g. SKYbrary category)
    if sub_clean and sub_clean != "all":
        filtered = [
            item for item in filtered
            if (item.get("subtopic") or "").lower().strip() == sub_clean
        ]

    # 3. Filter by stakeholder
    if stk_clean and stk_clean != "all":
        filtered = [item for item in filtered if (item.get("primary_stakeholder") or "").lower() == stk_clean]

    # 3b. Filter by year range (e.g. 2020 - 2024)
    if year_min is not None:
        filtered = [
            item for item in filtered
            if (item.get("primary_year") is not None and item["primary_year"] >= year_min)
            or any(y >= year_min for y in item.get("detected_years", []))
        ]
    if year_max is not None:
        filtered = [
            item for item in filtered
            if (item.get("primary_year") is not None and item["primary_year"] <= year_max)
            or any(y <= year_max for y in item.get("detected_years", []))
        ]

    # 3c. Filter by obsolescence pattern flag
    if pattern_flag and pattern_flag.lower().strip() not in ("all", "none", ""):
        p_clean = pattern_flag.lower().strip()
        filtered = [
            item for item in filtered
            if p_clean in [f.lower() for f in item.get("obsolescence_flags", [])]
        ]
        
    # 4. Title-level search (standard or fuzzy/range-aware)
    if q_clean:
        # Check if query explicitly contains a year range like "2020-2024" or "2018 - 2022"
        yr_range_match = re.search(r'\b(19[7-9]\d|20[0-3]\d)\s*[-–]\s*(19[7-9]\d|20[0-3]\d)\b', q_clean)
        extracted_min_yr = int(yr_range_match.group(1)) if yr_range_match else None
        extracted_max_yr = int(yr_range_match.group(2)) if yr_range_match else None

        clean_text_q = re.sub(r'\b(19[7-9]\d|20[0-3]\d)\s*[-–]\s*(19[7-9]\d|20[0-3]\d)\b', '', q_clean).strip()
        terms = clean_text_q.lower().split() if clean_text_q else []
        
        def matches_query(item: Dict[str, Any]) -> bool:
            # If a year range was in query, ensure item has year in that span
            if extracted_min_yr is not None and extracted_max_yr is not None:
                has_year_in_range = any(extracted_min_yr <= y <= extracted_max_yr for y in item.get("detected_years", []))
                if not has_year_in_range:
                    return False

            if not terms:
                return True

            text = (item["title"] + " " + item["document_id"]).lower()
            return all(term in text for term in terms)
            
        filtered = [item for item in filtered if matches_query(item)]
        
    # 5. Sorting
    reverse = (sort_order_str == "desc")
    if sort_by_str == "title":
        filtered.sort(key=lambda x: x["title"].lower(), reverse=reverse)
    elif sort_by_str == "date":
        filtered.sort(key=lambda x: x["date"] or "", reverse=reverse)
    else:  # chunks
        filtered.sort(key=lambda x: x["chunk_count"], reverse=reverse)
        
    total_count = len(all_items)
    filtered_count = len(filtered)
    paged_items = filtered[offset_val : offset_val + limit_val]
    
    return {
        "total": total_count,
        "filtered_count": filtered_count,
        "regulations": paged_items
    }


@router.get("/governance/stats", response_model=GovernanceStatsResponse, tags=["REGULATIONS"])
def api_get_governance_stats():
    """Returns knowledge governance and forgetting statistics."""
    return get_governance_stats()


@router.post("/governance/batch/deactivate", tags=["REGULATIONS"])
def api_batch_deactivate_documents(req: BatchDeactivateRequest):
    """
    Deactivates multiple documents and their chunks in a single operation.
    """
    global _CATALOG_CACHE
    try:
        res = batch_deactivate_documents(
            document_ids=req.document_ids, 
            reason=req.reason, 
            superseded_by=req.superseded_by
        )
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/batch/activate", tags=["REGULATIONS"])
def api_batch_activate_documents(req: BatchActivateRequest):
    """
    Reactivates multiple previously deactivated documents and restores their chunks to search.
    """
    global _CATALOG_CACHE
    try:
        res = batch_activate_documents(document_ids=req.document_ids)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/category/{category}/deactivate", tags=["REGULATIONS"])
def api_category_deactivate(category: str, req: CategoryDeactivateRequest):
    """
    Deactivates an entire category/origin of documents and their chunks.
    """
    global _CATALOG_CACHE
    try:
        res = deactivate_category(category=category, reason=req.reason, superseded_by=req.superseded_by)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/category/{category}/activate", tags=["REGULATIONS"])
def api_category_activate(category: str):
    """
    Reactivates an entire category/origin of documents and restores their chunks to search.
    """
    global _CATALOG_CACHE
    try:
        res = activate_category(category=category)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/governance/skybrary/topics", tags=["REGULATIONS"])
def api_get_skybrary_topics():
    """
    Returns aggregated statistics for all sub-topics/categories in SKYbrary.
    """
    return get_skybrary_topics_stats()


@router.post("/governance/skybrary/topic/deactivate", tags=["REGULATIONS"])
def api_deactivate_skybrary_topic(req: SkybraryTopicDeactivateRequest):
    """
    Deactivates and suppresses all documents under a given SKYbrary subtopic with a common reason.
    """
    global _CATALOG_CACHE
    try:
        res = deactivate_skybrary_topic(topic=req.topic, reason=req.reason, superseded_by=req.superseded_by)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/skybrary/topic/activate", tags=["REGULATIONS"])
def api_activate_skybrary_topic(req: SkybraryTopicActivateRequest):
    """
    Reactivates all documents under a given SKYbrary subtopic.
    """
    global _CATALOG_CACHE
    try:
        res = activate_skybrary_topic(topic=req.topic)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/ai-obsolescence-scan", response_model=AiObsolescenceScanResponse, tags=["REGULATIONS"])
def api_ai_obsolescence_scan(req: AiObsolescenceScanRequest):
    """
    Scans a batch of document titles using aviation regulatory heuristics and LLM inference
    to identify candidate obsolete, superseded, or aged documents for suppression.
    """
    docs_to_scan = req.documents[:120]  # Cap at 120 per batch for low latency
    if not docs_to_scan:
        return AiObsolescenceScanResponse(
            total_scanned=0,
            flagged_count=0,
            high_confidence_count=0,
            medium_confidence_count=0,
            low_confidence_count=0,
            summary="No documents provided for obsolescence scanning.",
            findings=[]
        )

    # 1. Rule-based heuristic findings (guarantees zero-failure baseline)
    heuristic_findings: Dict[str, ObsolescenceCandidateFinding] = {}
    for d in docs_to_scan:
        det_years, prim_yr, flags = extract_title_years_and_flags(
            d.title, "", d.document_id, "", d.origin or ""
        )
        yr = d.year or prim_yr
        title_lower = (d.title + " " + d.document_id).lower()

        if "known_repealed" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="HIGH",
                likely_status="REPEALED",
                detected_year=yr,
                reason="Regulation (EC) 216/2008 and earlier basic frameworks were repealed and superseded by EASA Basic Regulation (EU) 2018/1139.",
                suggested_action="Deactivate and supersede with Regulation (EU) 2018/1139",
                superseded_by="Regulation (EU) 2018/1139"
            )
        elif "covid_temporary" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="HIGH",
                likely_status="EXPIRED",
                detected_year=yr,
                reason="Emergency temporary pandemic exemption measure; expired following cessation of COVID-19 emergency circumstances.",
                suggested_action="Suppress expired temporary exemption",
                superseded_by=None
            )
        elif "draft" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="HIGH",
                likely_status="DRAFT",
                detected_year=yr,
                reason="Draft, provisional, or proposed version likely superseded by final enacted instrument.",
                suggested_action="Verify if final adopted act exists and suppress draft",
                superseded_by=None
            )
        elif "early_revision" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="HIGH",
                likely_status="SUPERSEDED",
                detected_year=yr,
                reason="Initial or early iteration (Issue 0/1 or Amendment 0/1); subject to subsequent regulatory revisions.",
                suggested_action="Review for later amendment and deactivate initial issue",
                superseded_by=None
            )
        elif "legacy_pre_2015" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="MEDIUM",
                likely_status="OBSOLETE",
                detected_year=yr,
                reason=f"Legacy document dating from {yr or 'pre-2015'}; high likelihood of being superseded by modern consolidated rules.",
                suggested_action="Review against current EU/EASA consolidated rules",
                superseded_by=None
            )
        elif "old_skybrary" in flags:
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="MEDIUM",
                likely_status="OUTDATED",
                detected_year=yr,
                reason=f"SKYbrary article published in {yr or 'pre-2018'}; operational procedures and avionics references may be superseded.",
                suggested_action="Review for modern RNP/ATM practices or suppress from primary search",
                superseded_by=None
            )
        elif "review_2020_2024" in flags and req.focus in ("review_2020_2024", "all"):
            heuristic_findings[d.document_id] = ObsolescenceCandidateFinding(
                document_id=d.document_id,
                title=d.title,
                is_suspect_obsolete=True,
                confidence="LOW",
                likely_status="REVIEW_NEEDED",
                detected_year=yr,
                reason=f"Dated between 2020 and 2024 ({yr}); requires review for newer amending regulations or subsequent corrigenda.",
                suggested_action="Verify against recent 2024/2025 regulatory amendments",
                superseded_by=None
            )

    # 2. LLM-Assisted Analysis
    llm_findings: List[ObsolescenceCandidateFinding] = []
    llm_summary = ""

    prompt_docs = [
        {
            "document_id": d.document_id,
            "title": d.title,
            "origin": d.origin,
            "subtopic": d.subtopic,
            "year": d.year or heuristic_findings.get(d.document_id, {}).detected_year
        }
        for d in docs_to_scan
    ]

    system_prompt = (
        "You are an expert Senior Aviation Regulatory Specialist and EASA/EU/FAA Legal Archivist. "
        "Analyze the provided batch of aviation document titles and identify regulations, specifications, or SKYbrary articles "
        "that are likely OBSOLETE, SUPERSEDED, REPEALED, TEMPORARY EXEMPTIONS, or in need of review. "
        "Return ONLY a valid JSON object matching the requested schema."
    )

    user_prompt = f"""Analyze these {len(prompt_docs)} aviation documents:
{json.dumps(prompt_docs, indent=2)}

Focus area: {req.focus}

For each document that is a candidate for obsolescence or review:
1. Identify if it is suspect obsolete.
2. Assign confidence: 'HIGH' (repealed/superseded/expired), 'MEDIUM' (likely superseded/old revision/aging guidance), 'LOW' (requires review against newer amendments).
3. Provide a clear reason explaining why it is suspected obsolete.
4. Provide a suggested action and optional superseded_by reference.

Return ONLY a JSON object:
{{
  "findings": [
    {{
      "document_id": "<id>",
      "title": "<title>",
      "is_suspect_obsolete": true,
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "detected_year": <int or null>,
      "reason": "<clear explanation>",
      "suggested_action": "<recommendation>",
      "superseded_by": "<optional newer regulation or null>"
    }}
  ],
  "summary": "<summary of findings>"
}}
"""

    try:
        raw_res = call_unified_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=3000,
            temperature=0.1,
            provider=req.provider or "local",
            gemini_api_key=req.gemini_api_key,
            gemini_model=req.gemini_model or "gemini-3.5-flash"
        )

        cleaned_json = raw_res.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json)

        parsed = json.loads(cleaned_json)
        llm_summary = parsed.get("summary", "")
        raw_items = parsed.get("findings", [])

        valid_doc_ids = {d.document_id for d in docs_to_scan}
        for item in raw_items:
            doc_id = str(item.get("document_id") or "").strip()
            if doc_id in valid_doc_ids and item.get("is_suspect_obsolete"):
                conf = str(item.get("confidence") or "MEDIUM").upper()
                if conf not in ("HIGH", "MEDIUM", "LOW"):
                    conf = "MEDIUM"
                llm_findings.append(ObsolescenceCandidateFinding(
                    document_id=doc_id,
                    title=str(item.get("title") or next((d.title for d in docs_to_scan if d.document_id == doc_id), "")),
                    is_suspect_obsolete=True,
                    confidence=conf,
                    likely_status=str(item.get("likely_status") or ("REPEALED" if item.get("superseded_by") else "OBSOLETE")),
                    detected_year=item.get("detected_year"),
                    reason=str(item.get("reason") or "Identified by AI analysis as candidate obsolete document."),
                    suggested_action=str(item.get("suggested_action") or "Review for superseding regulation"),
                    superseded_by=item.get("superseded_by")
                ))

    except Exception as e:
        log_debug_info("AI_OBSOLESCENCE_SCAN_ERROR", {"error": str(e)})
        llm_summary = f"AI analysis supplemented with legal rule-based pattern detection ({len(heuristic_findings)} candidate flags identified)."

    # 3. Merge findings (LLM findings take precedence, augmented by heuristic findings)
    final_findings_map: Dict[str, ObsolescenceCandidateFinding] = {}
    for f in llm_findings:
        final_findings_map[f.document_id] = f

    for doc_id, hf in heuristic_findings.items():
        if doc_id not in final_findings_map:
            final_findings_map[doc_id] = hf
        elif hf.confidence == "HIGH" and final_findings_map[doc_id].confidence != "HIGH":
            # Upgrade confidence if heuristic is definitively known repealed
            final_findings_map[doc_id].confidence = "HIGH"
            if hf.superseded_by and not final_findings_map[doc_id].superseded_by:
                final_findings_map[doc_id].superseded_by = hf.superseded_by

    # Sort findings by confidence (HIGH first, then MEDIUM, then LOW)
    conf_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_findings = sorted(
        final_findings_map.values(),
        key=lambda x: (conf_order.get(x.confidence, 3), -(x.detected_year or 0))
    )

    high_c = sum(1 for f in sorted_findings if f.confidence == "HIGH")
    med_c = sum(1 for f in sorted_findings if f.confidence == "MEDIUM")
    low_c = sum(1 for f in sorted_findings if f.confidence == "LOW")

    if not llm_summary:
        llm_summary = (
            f"Obsolescence review completed on {len(docs_to_scan)} documents. "
            f"Identified {high_c} high-confidence, {med_c} medium-confidence, and {low_c} review candidate titles."
        )

    return AiObsolescenceScanResponse(
        total_scanned=len(docs_to_scan),
        flagged_count=len(sorted_findings),
        high_confidence_count=high_c,
        medium_confidence_count=med_c,
        low_confidence_count=low_c,
        summary=llm_summary,
        findings=sorted_findings
    )


@router.post("/governance/{document_id:path}/deactivate", tags=["REGULATIONS"])
def api_deactivate_document(document_id: str, req: DeactivateDocumentRequest):
    """
    Deactivates a document and its chunks in the database (knowledge forgetting).
    Omitted from all search queries and LLM retrieval.
    """
    global _CATALOG_CACHE
    try:
        res = deactivate_document(document_id, reason=req.reason, superseded_by=req.superseded_by)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/governance/{document_id:path}/activate", tags=["REGULATIONS"])
def api_activate_document(document_id: str):
    """
    Reactivates a previously deactivated document and restores its chunks to search.
    """
    global _CATALOG_CACHE
    try:
        res = activate_document(document_id)
        _CATALOG_CACHE["timestamp"] = 0  # Invalidate catalog cache
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=BatchDownloadResponse, tags=["REGULATIONS"])
def api_batch_download_regulations(req: BatchDownloadRequest):
    """
    Fetches full markdown and metadata for multiple selected regulations.
    Used by the client to download regulations for local viewing and caching in the app.
    """
    catalog = {item["document_id"]: item for item in load_cached_catalog()}
    documents = []
    
    for doc_id in req.document_ids:
        cat_info = catalog.get(doc_id, {})
        title = cat_info.get("title", doc_id)
        origin = cat_info.get("origin", "eu")
        chunk_count = cat_info.get("chunk_count", 0)
        
        meta = get_document_metadata(doc_id)
        if not meta and cat_info.get("metadata"):
            meta = cat_info["metadata"]
            
        markdown = get_document_markdown_content(doc_id)
        
        documents.append({
            "document_id": doc_id,
            "title": title,
            "origin": origin,
            "markdown_doc": markdown,
            "metadata": meta,
            "chunk_count": chunk_count
        })
        
    return {
        "count": len(documents),
        "documents": documents
    }


@router.get("/regulations/{document_id}/qualifiers", tags=["REGULATIONS"])
def api_get_regulation_qualifiers(document_id: str):
    """
    Returns supporting qualifiers (Decisions, Corrigenda, Implementing acts)
    associated with a regulation.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, metadata_json FROM documents WHERE document_id = ?", (document_id,))
            doc_row = cursor.fetchone()
            
            celex = None
            doc_num = None
            if doc_row and doc_row["metadata_json"]:
                try:
                    m = json.loads(doc_row["metadata_json"])
                    celex = m.get("celex")
                    doc_num = m.get("doc_number")
                except Exception:
                    pass

            query = """
                SELECT qualifier_id, parent_regulation_id, target_regulation_ref,
                       qualifier_type, celex, title, date, source_file, content_text, metadata_json
                FROM qualifiers
                WHERE parent_regulation_id = ? OR qualifier_id = ?
            """
            params = [document_id, document_id]
            if celex:
                query += " OR parent_regulation_id = ? OR celex = ?"
                params.extend([celex, celex])
            if doc_num:
                query += " OR target_regulation_ref LIKE ?"
                params.append(f"%{doc_num}%")

            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            qualifiers = []
            for r in rows:
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                qualifiers.append({
                    "qualifier_id": r["qualifier_id"],
                    "parent_regulation_id": r["parent_regulation_id"],
                    "target_regulation_ref": r["target_regulation_ref"],
                    "qualifier_type": r["qualifier_type"],
                    "celex": r["celex"],
                    "title": r["title"],
                    "date": r["date"],
                    "source_file": r["source_file"],
                    "content_preview": (r["content_text"] or "")[:300],
                    "metadata": meta
                })
                
            return {
                "document_id": document_id,
                "count": len(qualifiers),
                "qualifiers": qualifiers
            }
    except Exception as e:
        return {
            "document_id": document_id,
            "count": 0,
            "qualifiers": [],
            "error": str(e)
        }


@router.post("/workspace-fts", response_model=WorkspaceFtsResponse, tags=["REGULATIONS"])
def api_search_workspace_fts(req: WorkspaceFtsRequest):
    """
    Executes a high-speed SQLite FTS5 search restricted specifically to the user's
    active workspace regulations. Computes cross-document overlap metrics and returns
    matching chunks grouped by document to visualize where the search idea overlaps.
    """
    q_str = req.query.strip()
    if not q_str or not req.document_ids:
        empty_overlap = {
            "query": q_str,
            "total_documents_queried": len(req.document_ids),
            "total_documents_matched": 0,
            "overlap_rate": 0.0,
            "all_documents_matched": False,
            "total_chunks_matched": 0,
            "matched_document_ids": [],
            "shared_search_terms": [],
            "document_summaries": []
        }
        return {
            "query": q_str,
            "fts_expression": "",
            "total_matches": 0,
            "overlap_summary": empty_overlap,
            "results_by_document": {d: [] for d in req.document_ids},
            "all_results": []
        }
        
    fts_expr = build_fts_query(q_str)
    if not fts_expr:
        fts_expr = f'"{q_str}"'
        
    placeholders = ",".join(["?"] * len(req.document_ids))
    sql = f"""
        SELECT 
            c.chunk_id,
            c.document_id,
            c.section_path,
            c.source_text,
            c.metadata_json,
            c.previous_chunk_id,
            c.next_chunk_id,
            bm25(chunks_fts) as rank
        FROM chunks_fts f
        JOIN chunks c ON f.rowid = c.rowid
        WHERE chunks_fts MATCH ?
          AND c.document_id IN ({placeholders})
        ORDER BY rank
        LIMIT ?
    """
    
    results_by_doc = {d: [] for d in req.document_ids}
    all_results = []
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, [fts_expr] + req.document_ids + [req.total_top_k])
            rows = cursor.fetchall()
            
            for r in rows:
                d_id = r["document_id"]
                sec_path = []
                if r["section_path"]:
                    try:
                        sec_path = json.loads(r["section_path"])
                    except Exception:
                        sec_path = [r["section_path"]]
                        
                sec_title = sec_path[-1] if sec_path else r["chunk_id"]
                raw_text = r["source_text"] or ""
                
                # Extract clean snippet
                snippet = " ".join(raw_text.split()[:50])
                if len(raw_text.split()) > 50:
                    snippet += "..."
                    
                rank_val = float(r["rank"])
                score = round(1.0 / (1.0 + abs(rank_val)), 4)
                
                match_obj = {
                    "chunk_id": r["chunk_id"],
                    "document_id": d_id,
                    "section_path": sec_path,
                    "section_title": sec_title,
                    "source_text": raw_text,
                    "text": raw_text,
                    "snippet": snippet,
                    "rank": rank_val,
                    "score": score,
                    "previous_chunk_id": r["previous_chunk_id"],
                    "next_chunk_id": r["next_chunk_id"]
                }
                
                if len(results_by_doc[d_id]) < req.top_k_per_doc:
                    results_by_doc[d_id].append(match_obj)
                    
                all_results.append(match_obj)
                
    except Exception as e:
        print(f"FTS workspace query error: {e}")
        log_debug_info("WORKSPACE_FTS_ERROR", {"error": str(e), "query": q_str, "fts_expr": fts_expr})
        
    catalog = {item["document_id"]: item for item in load_cached_catalog()}
    
    # Analyze matched documents
    matched_doc_ids = [d for d in req.document_ids if len(results_by_doc.get(d, [])) > 0]
    total_docs = len(req.document_ids)
    matched_count = len(matched_doc_ids)
    overlap_rate = round(matched_count / total_docs, 3) if total_docs > 0 else 0.0
    
    # Identify shared query terms across results
    q_tokens = [w.lower() for w in re.findall(r'\b[A-Za-z0-9_-]{3,}\b', q_str)]
    shared_terms = []
    if all_results:
        full_result_text = " ".join([m["source_text"].lower() for m in all_results])
        for tok in q_tokens:
            if tok in full_result_text and tok not in shared_terms:
                shared_terms.append(tok)
                
    doc_summaries = []
    for d_id in req.document_ids:
        matches = results_by_doc.get(d_id, [])
        cat_info = catalog.get(d_id, {})
        doc_summaries.append({
            "document_id": d_id,
            "title": cat_info.get("title", d_id),
            "origin": cat_info.get("origin", "eu"),
            "chunk_count": cat_info.get("chunk_count", 0),
            "match_count": len(matches),
            "best_score": matches[0]["score"] if matches else 0.0,
            "has_match": len(matches) > 0,
            "top_section": matches[0]["section_title"] if matches else None
        })
        
    overlap_summary = {
        "query": q_str,
        "total_documents_queried": total_docs,
        "total_documents_matched": matched_count,
        "overlap_rate": overlap_rate,
        "all_documents_matched": (matched_count == total_docs and total_docs > 0),
        "total_chunks_matched": len(all_results),
        "matched_document_ids": matched_doc_ids,
        "shared_search_terms": shared_terms,
        "document_summaries": doc_summaries
    }
    
    return {
        "query": q_str,
        "fts_expression": fts_expr,
        "total_matches": len(all_results),
        "overlap_summary": overlap_summary,
        "results_by_document": results_by_doc,
        "all_results": all_results
    }


# -------------------------------------------------------------
# Manual Document Builder Endpoint & Models
# -------------------------------------------------------------

class ManualSectionInput(BaseModel):
    section_number: str = Field(..., description="e.g. '1.1' or '21.A.1'")
    title: str = Field(..., description="Section title or clause heading")
    subpart: Optional[str] = Field(None, description="e.g. 'Subpart A - General'")
    subject_group: Optional[str] = Field(None, description="e.g. 'AIRWORTHINESS'")
    text: str = Field(..., min_length=1, description="Clause text or markdown formatted content")

class ManualDocumentRequest(BaseModel):
    title: str = Field(..., min_length=3, description="Full title of the regulation or policy document")
    document_id: Optional[str] = Field(None, description="Custom identifier, or auto-generated if omitted")
    source: Optional[str] = Field(default="Manual", description="Issuing agency, company or authority")
    date: Optional[str] = Field(default="", description="Effective date (YYYY-MM-DD)")
    language: Optional[str] = Field(default="eng", description="Language code")
    stakeholder: Optional[str] = Field(default="general", description="Primary stakeholder domain")
    description: Optional[str] = Field(default="", description="Optional summary or description")
    sections: List[ManualSectionInput] = Field(..., min_items=1, description="Structured sections of the document")

class ManualDocumentResponse(BaseModel):
    success: bool
    document_id: str
    title: str
    chunk_count: int
    message: str

@router.post("/manual-document", response_model=ManualDocumentResponse, tags=["REGULATIONS"])
def api_create_manual_document(req: ManualDocumentRequest):
    """
    Manually build, structure, chunk, and index an aviation regulation or policy document.
    Enforces the exact same chunk schema and hierarchy as EASA / FAA documents,
    linking sequential chunks and indexing them in SQLite FTS5.
    """
    if not req.sections:
        raise HTTPException(status_code=400, detail="Document must contain at least one section.")

    # Determine document ID
    if req.document_id and req.document_id.strip():
        clean_doc_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', req.document_id.strip()).strip('_')
    else:
        title_slug = re.sub(r'[^A-Za-z0-9_]+', '_', req.title.strip())[:35].strip('_')
        clean_doc_id = f"MANUAL_{title_slug}_{int(time.time())}"

    source = req.source.strip() if (req.source and req.source.strip()) else "Manual"
    date_str = req.date.strip() if req.date else time.strftime("%Y-%m-%d")
    lang = req.language.strip() if req.language else "eng"
    stakeholder = req.stakeholder.strip().lower() if req.stakeholder else "general"

    doc_metadata = {
        "title": req.title.strip(),
        "source": source,
        "date": date_str,
        "language": lang,
        "stakeholder": stakeholder,
        "description": (req.description or "").strip(),
        "type": "ManualDocument",
        "origin": "manual",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    # Prepare chunks and sequential links
    chunks_to_insert = []
    easa_style_json = []
    seen_chunk_ids = set()

    # Add preface item to json representation
    if req.description:
        easa_style_json.append({
            "meta": {
                "title": "Scope & Description",
                "type": "preface",
                "subject": req.title,
                "id": f"{clean_doc_id}_preface"
            },
            "text": f"{req.title}\n\n{req.description}"
        })

    for idx, sec in enumerate(req.sections):
        sec_num = sec.section_number.strip()
        sec_title = sec.title.strip()
        sec_subpart = sec.subpart.strip() if sec.subpart else ""
        sec_group = sec.subject_group.strip() if sec.subject_group else ""
        sec_text = sec.text.strip()

        # Sanitize section number for ID
        safe_num = re.sub(r'[^A-Za-z0-9_]+', '_', sec_num).strip('_')
        base_chunk_id = f"{clean_doc_id}:sec_{safe_num}" if safe_num else f"{clean_doc_id}:sec_{idx+1}"
        chunk_id = base_chunk_id
        c_suffix = 1
        while chunk_id in seen_chunk_ids:
            chunk_id = f"{base_chunk_id}_{c_suffix}"
            c_suffix += 1
        seen_chunk_ids.add(chunk_id)

        # Build section path hierarchy
        path = [req.title.strip()]
        if sec_subpart:
            path.append(sec_subpart)
        if sec_group:
            path.append(sec_group)
        full_clause_title = f"{sec_num} {sec_title}".strip() if sec_num else sec_title
        path.append(full_clause_title)

        # Source text
        source_text = f"{full_clause_title}\n\n{sec_text}"

        # Embedding text enriched with hierarchical context
        emb_parts = [f"Document: {req.title.strip()}"]
        if sec_subpart:
            emb_parts.append(f"Subpart: {sec_subpart}")
        if sec_group:
            emb_parts.append(f"Subject Group: {sec_group}")
        emb_parts.append(f"Section: {full_clause_title}\n\n{sec_text}")
        embedding_text = "\n".join(emb_parts)

        chunk_meta = {
            "document_id": clean_doc_id,
            "section_number": sec_num,
            "section_title": sec_title,
            "subpart": sec_subpart,
            "subject_group": sec_group,
            "origin": "manual",
            "source": source,
            "stakeholder": stakeholder
        }

        chunks_to_insert.append({
            "chunk_id": chunk_id,
            "document_id": clean_doc_id,
            "section_path": path,
            "source_text": source_text,
            "embedding_text": embedding_text,
            "metadata_json": json.dumps(chunk_meta),
            "previous_chunk_id": None,
            "next_chunk_id": None
        })

        # Add to structured JSON representation
        easa_style_json.append({
            "meta": {
                "title": full_clause_title,
                "type": "section",
                "subject": sec_subpart or sec_group or req.title,
                "id": chunk_id
            },
            "text": source_text
        })

    # Link sequential chunks
    for i in range(len(chunks_to_insert)):
        if i > 0:
            chunks_to_insert[i]["previous_chunk_id"] = chunks_to_insert[i-1]["chunk_id"]
        if i < len(chunks_to_insert) - 1:
            chunks_to_insert[i]["next_chunk_id"] = chunks_to_insert[i+1]["chunk_id"]

    # Write to SQLite database
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Insert document
            cursor.execute("""
                INSERT OR REPLACE INTO documents (document_id, title, date, language, source, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (clean_doc_id, req.title.strip(), date_str, lang, source, json.dumps(doc_metadata)))

            # Delete any existing chunks for this document_id if updating
            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (clean_doc_id,))

            # Insert chunks
            for c in chunks_to_insert:
                cursor.execute("""
                    INSERT INTO chunks (
                        chunk_id, document_id, section_path, source_text, embedding_text,
                        previous_chunk_id, next_chunk_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["chunk_id"],
                    c["document_id"],
                    json.dumps(c["section_path"]),
                    c["source_text"],
                    c["embedding_text"],
                    c["previous_chunk_id"],
                    c["next_chunk_id"],
                    c["metadata_json"]
                ))

            # Insert primary stakeholder score if table exists
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO document_stakeholder_scores (document_id, primary_stakeholder, score)
                    VALUES (?, ?, 1.0)
                """, (clean_doc_id, stakeholder))
            except Exception:
                pass

            conn.commit()

            # Rebuild FTS5 index to immediately index new chunks
            try:
                cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');")
                cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize');")
                conn.commit()
            except Exception as fts_err:
                print(f"Warning: FTS rebuild for manual doc: {fts_err}")

        # Also save JSON file to data/regulations for find_json_file
        try:
            reg_dir = settings.DATA_DIR / "regulations"
            reg_dir.mkdir(parents=True, exist_ok=True)
            json_file = reg_dir / f"{clean_doc_id}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(easa_style_json, f, indent=2, ensure_ascii=False)
        except Exception as file_err:
            print(f"Warning: could not save JSON representation: {file_err}")

        # Flush in-memory catalog cache
        global _CATALOG_CACHE
        _CATALOG_CACHE["timestamp"] = 0
        _CATALOG_CACHE["items"] = []

        return {
            "success": True,
            "document_id": clean_doc_id,
            "title": req.title.strip(),
            "chunk_count": len(chunks_to_insert),
            "message": f"Successfully created and indexed '{req.title.strip()}' with {len(chunks_to_insert)} chunks."
        }

    except Exception as e:
        print(f"Error creating manual document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create manual document: {str(e)}")


# -------------------------------------------------------------
# USER NOTES & USER-GENERATED DOCUMENTATION OPERATIONS
# -------------------------------------------------------------

def embed_chunks_for_document(chunk_records: List[Dict[str, Any]]) -> int:
    """
    Computes vector embeddings for a list of chunk dicts (containing 'chunk_id' and 'embedding_text')
    and persists them to the local FAISS index (EmbeddingType.CHUNK).
    Returns count of successfully embedded chunks.
    """
    if not chunk_records:
        return 0
    try:
        texts = [c["embedding_text"] for c in chunk_records]
        vectors = get_embeddings_batch(texts)
        if not vectors or len(vectors) != len(chunk_records):
            print(f"Embedding generation warning: received {len(vectors) if vectors else 0} vectors for {len(chunk_records)} chunks")
            return 0

        vector_index = LocalVectorIndex(settings.EMBEDDINGS_DIR, settings.EMBEDDING_DIMENSIONS)
        records = []
        for c, vec in zip(chunk_records, vectors):
            if not vec:
                continue
            text_hash = hashlib.md5(c["embedding_text"].encode("utf-8")).hexdigest()
            records.append(EmbeddingRecord(
                embedding_id=c["chunk_id"],
                fragment_id=c["chunk_id"],
                embedding_type=EmbeddingType.CHUNK,
                model=settings.EMBEDDING_MODEL_NAME,
                dimensions=len(vec),
                vector=vec,
                text_hash=text_hash
            ))

        if records:
            vector_index.add_records(records)
            vector_index.save()
            return len(records)
    except Exception as e:
        print(f"Failed to embed chunks for document: {e}")
    return 0


class NoteSectionInput(BaseModel):
    section_number: Optional[str] = Field(None, description="Optional section number or timestamp (e.g. '1', '10:30')")
    heading: str = Field(default="Section", description="Section heading or topic title")
    content: str = Field(default="", description="Markdown or text content of the section")
    tags: Optional[List[str]] = Field(default=[], description="Optional section tags")

class CreateNoteRequest(BaseModel):
    title: str = Field(..., min_length=2, description="Title of the note or meeting minutes")
    document_id: Optional[str] = Field(None, description="Optional custom ID (e.g. NOTE_PROJECT_XYZ_STATUS)")
    note_type: str = Field(default="general_note", description="Type: meeting_minutes, daily_journal, project_note, general_note")
    date: Optional[str] = Field(default="", description="Date (YYYY-MM-DD)")
    created_by: Optional[str] = Field(None, description="Creator / author of the note ('who created it')")
    author: Optional[str] = Field(None, description="Author alias (maps to created_by)")
    project: Optional[str] = Field(default="", description="Associated project or topic (e.g. 'Project XYZ')")
    is_indefinite: bool = Field(default=True, description="Whether the note has indefinite validity or expires")
    expires_at: Optional[str] = Field(None, description="Expiration date (YYYY-MM-DD) if is_indefinite is False")
    keywords: Optional[List[str]] = Field(default=[], description="Keywords associated with the note")
    tags: Optional[List[str]] = Field(default=[], description="Tags or categorization labels")
    description: Optional[str] = Field(default="", description="High level overview or meeting attendees summary")
    sections: List[NoteSectionInput] = Field(..., min_items=1, description="Structured sections/entries of the note")
    auto_embed: Optional[bool] = Field(default=True, description="Immediately generate vector embeddings via LM Studio")

class NoteSummaryItem(BaseModel):
    document_id: str
    title: str
    note_type: str
    date: str
    author: str
    created_by: str
    project: str
    tags: List[str]
    keywords: List[str]
    is_indefinite: bool
    expires_at: Optional[str] = None
    is_expired: bool = False
    chunk_count: int
    is_embedded: bool
    created_at: str

class NoteDetailResponse(BaseModel):
    document_id: str
    title: str
    note_type: str
    date: str
    author: str
    created_by: str
    project: str
    tags: List[str]
    keywords: List[str]
    is_indefinite: bool
    expires_at: Optional[str] = None
    is_expired: bool = False
    description: str
    chunk_count: int
    is_embedded: bool
    created_at: str
    sections: List[NoteSectionInput]
    markdown_doc: str

class NoteActionResponse(BaseModel):
    success: bool
    document_id: str
    title: str
    chunk_count: int
    is_embedded: bool
    message: str

class GenerateNoteKeywordsRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Title of the note")
    content: Optional[str] = Field(default="", description="Optional full content or summary text")
    sections: Optional[List[NoteSectionInput]] = Field(default=None, description="Structured sections")
    project: Optional[str] = Field(default=None, description="Project context")
    provider: Optional[str] = Field(default="local", description="LLM provider: 'local' (LM Studio) or 'gemini'")
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None

class GenerateNoteKeywordsResponse(BaseModel):
    success: bool
    keywords: List[str]
    message: str


@router.post("/notes/generate-keywords", response_model=GenerateNoteKeywordsResponse, tags=["REGULATIONS"])
def api_generate_note_keywords(req: GenerateNoteKeywordsRequest):
    """
    Uses the local LLM (or Gemini) to analyze note title, project, and section contents,
    extracting 4 to 8 high-value aviation regulatory and operational keywords.
    """
    # Assemble content
    content_parts = []
    if req.title:
        content_parts.append(f"Title: {req.title.strip()}")
    if req.project:
        content_parts.append(f"Project: {req.project.strip()}")
    if req.content:
        content_parts.append(f"Summary: {req.content.strip()}")
    if req.sections:
        for s in req.sections:
            if s.heading or s.content:
                content_parts.append(f"Section {s.heading}: {s.content.strip()[:400]}")

    full_context = "\n".join(content_parts)[:2500]

    system_prompt = (
        "You are an expert aviation knowledge manager and ontology specialist. "
        "Your task is to analyze note content and extract 4 to 8 concise, specific, high-value domain keywords or phrases. "
        "Focus on regulatory standards (e.g. Part-ADR, Part-ORO, CS-AWO, ICAO), systems (e.g. SMR, CPDLC, ADS-B, ILS), "
        "operational procedures (e.g. Low Visibility Procedures, De-icing, Fatigue Risk), or project initiatives. "
        "Respond ONLY with a valid JSON array of strings, for example: [\"Keyword 1\", \"Keyword 2\", \"Keyword 3\"]. "
        "Do not include any preamble, markdown code blocks, or explanations."
    )
    user_prompt = f"Extract keywords for this note:\n\n{full_context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        raw_resp = call_unified_chat(
            messages=messages,
            provider="gemini" if req.provider == "gemini" else "local",
            gemini_api_key=req.gemini_api_key,
            gemini_model=req.gemini_model,
            temperature=0.2,
            max_tokens=300
        )
        clean_text = raw_resp.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:].strip()
        if clean_text.startswith("```"):
            clean_text = clean_text[3:].strip()
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip()

        parsed_keywords = []
        try:
            val = json.loads(clean_text)
            if isinstance(val, list):
                parsed_keywords = [str(k).strip() for k in val if str(k).strip()]
        except Exception:
            # Fallback regex extraction of quoted strings
            parsed_keywords = re.findall(r'"([^"\\]+)"', clean_text)

        # Clean and deduplicate
        final_keywords = []
        for kw in parsed_keywords:
            clean_kw = kw.strip().strip("-*• ")
            if clean_kw and len(clean_kw) <= 40 and clean_kw not in final_keywords:
                final_keywords.append(clean_kw)

        if final_keywords:
            return GenerateNoteKeywordsResponse(
                success=True,
                keywords=final_keywords[:8],
                message=f"Generated {len(final_keywords[:8])} keywords using {req.provider or 'LLM'}."
            )
    except Exception as e:
        print(f"LLM keyword generation failed: {e}. Falling back to rule-based keyword extraction...")

    # Graceful heuristic fallback: extract aviation acronyms & key domain terms
    acronyms = re.findall(r'\b[A-Z]{2,}(?:-[A-Z0-9]+)?\b', full_context)
    words = [w for w in re.findall(r'\b[A-Za-z]{4,}\b', full_context) if w.lower() not in {"this", "that", "with", "from", "have", "note", "section", "about", "project", "title"}]
    fallback_pool = []
    for ac in acronyms:
        if ac not in fallback_pool and len(ac) <= 12:
            fallback_pool.append(ac)
    for w in words[:6]:
        cap = w.capitalize()
        if cap not in fallback_pool:
            fallback_pool.append(cap)

    fallback_keywords = fallback_pool[:6] if fallback_pool else ["Aviation Note", "Operational Knowledge"]
    return GenerateNoteKeywordsResponse(
        success=True,
        keywords=fallback_keywords,
        message="Generated keywords via domain heuristic extraction (LLM offline)."
    )


@router.post("/notes", response_model=NoteActionResponse, tags=["REGULATIONS"])
def api_create_note(req: CreateNoteRequest):
    """
    Creates and indexes user-generated documentation (daily journals, minutes of meetings, or project notes).
    Chunks the note by user-defined sections with full contextual metadata, saves to SQLite,
    updates SQLite FTS5, and computes vector embeddings for full semantic search.
    Enforces author ('who created it'), expiration policy (indefinite vs expires_at), and keywords.
    """
    if not req.sections:
        raise HTTPException(status_code=400, detail="Note must contain at least one section.")

    creator_str = (req.created_by or req.author or "").strip()
    if not creator_str:
        raise HTTPException(
            status_code=400, 
            detail="Creator ('who created it') is required. Please specify who recorded or created this note."
        )

    if req.document_id and req.document_id.strip():
        raw_id = req.document_id.strip()
        if not raw_id.startswith("NOTE_"):
            raw_id = f"NOTE_{raw_id}"
        clean_doc_id = re.sub(r'[^A-Za-z0-9_.-]+', '_', raw_id).strip('_')
    else:
        title_slug = re.sub(r'[^A-Za-z0-9_]+', '_', req.title.strip())[:30].strip('_')
        clean_doc_id = f"NOTE_{title_slug}_{int(time.time())}"

    date_str = req.date.strip() if req.date and req.date.strip() else time.strftime("%Y-%m-%d")
    project_str = req.project.strip() if req.project and req.project.strip() else ""
    note_type_str = req.note_type.strip() if req.note_type and req.note_type.strip() else "general_note"
    tags_list = [t.strip() for t in (req.tags or []) if t and t.strip()]

    # Keywords handling
    keywords_list = [k.strip() for k in (req.keywords or []) if k and k.strip()]
    for t in tags_list:
        if t not in keywords_list:
            keywords_list.append(t)

    # Expiration handling
    is_indefinite = bool(req.is_indefinite)
    expires_at = (req.expires_at or "").strip() if not is_indefinite else None
    if not is_indefinite and not expires_at:
        # Default expiration to 1 year if marked as expiring without date
        expires_at = time.strftime("%Y-%m-%d", time.localtime(time.time() + 365*24*3600))

    doc_metadata = {
        "title": req.title.strip(),
        "source": creator_str,
        "author": creator_str,
        "created_by": creator_str,
        "date": date_str,
        "language": "eng",
        "project": project_str,
        "note_type": note_type_str,
        "tags": tags_list,
        "keywords": keywords_list,
        "is_indefinite": is_indefinite,
        "expires_at": expires_at,
        "description": (req.description or "").strip(),
        "type": "Note",
        "origin": "note",
        "is_embedded": False,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    chunks_to_insert = []
    easa_style_json = []
    seen_chunk_ids = set()

    if req.description:
        easa_style_json.append({
            "meta": {
                "title": "Overview & Context",
                "type": "preface",
                "subject": req.title,
                "id": f"{clean_doc_id}_preface"
            },
            "text": f"{req.title}\n\n{req.description}"
        })

    for idx, sec in enumerate(req.sections):
        sec_num = sec.section_number.strip() if sec.section_number else str(idx + 1)
        sec_heading = sec.heading.strip()
        sec_content = sec.content.strip()

        safe_num = re.sub(r'[^A-Za-z0-9_]+', '_', sec_num).strip('_')
        base_chunk_id = f"{clean_doc_id}:sec_{safe_num}" if safe_num else f"{clean_doc_id}:sec_{idx+1}"
        chunk_id = base_chunk_id
        c_suffix = 1
        while chunk_id in seen_chunk_ids:
            chunk_id = f"{base_chunk_id}_{c_suffix}"
            c_suffix += 1
        seen_chunk_ids.add(chunk_id)

        path = ["Notes"]
        if project_str:
            path.append(project_str)
        else:
            path.append(note_type_str.replace("_", " ").title())
        path.append(f"{sec_num}. {sec_heading}" if sec_num else sec_heading)

        source_text = f"## {sec_heading}\n\n{sec_content}"

        emb_lines = [
            f"Document: {req.title.strip()}",
            f"Type: {note_type_str.replace('_', ' ').title()}",
            f"Date: {date_str}",
            f"Created by: {creator_str}"
        ]
        if project_str:
            emb_lines.append(f"Project: {project_str}")
        if keywords_list:
            emb_lines.append(f"Keywords: {', '.join(keywords_list)}")
        if not is_indefinite and expires_at:
            emb_lines.append(f"Expiration: {expires_at}")
        elif is_indefinite:
            emb_lines.append("Validity: Indefinite")
        if tags_list:
            emb_lines.append(f"Tags: {', '.join(tags_list)}")
        emb_lines.append(f"Section: {sec_heading}\n\n{sec_content}")
        embedding_text = "\n".join(emb_lines)

        chunk_meta = {
            "document_id": clean_doc_id,
            "document_title": req.title.strip(),
            "section_number": sec_num,
            "section_title": sec_heading,
            "origin": "note",
            "source": creator_str,
            "doc_type": "note",
            "note_type": note_type_str,
            "project": project_str,
            "author": creator_str,
            "created_by": creator_str,
            "date": date_str,
            "is_indefinite": is_indefinite,
            "expires_at": expires_at,
            "keywords": keywords_list,
            "tags": tags_list
        }

        chunks_to_insert.append({
            "chunk_id": chunk_id,
            "document_id": clean_doc_id,
            "section_path": path,
            "source_text": source_text,
            "embedding_text": embedding_text,
            "metadata_json": json.dumps(chunk_meta),
            "previous_chunk_id": None,
            "next_chunk_id": None
        })

        easa_style_json.append({
            "meta": {
                "title": sec_heading,
                "type": "section",
                "subject": project_str or req.title,
                "id": chunk_id
            },
            "text": source_text
        })

    for i in range(len(chunks_to_insert)):
        if i > 0:
            chunks_to_insert[i]["previous_chunk_id"] = chunks_to_insert[i-1]["chunk_id"]
        if i < len(chunks_to_insert) - 1:
            chunks_to_insert[i]["next_chunk_id"] = chunks_to_insert[i+1]["chunk_id"]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO documents (document_id, title, date, language, source, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (clean_doc_id, req.title.strip(), date_str, "eng", creator_str, json.dumps(doc_metadata)))

            # Delete any previous chunks for this document
            try:
                cursor.execute("""
                    INSERT INTO chunks_fts(chunks_fts, rowid, source_text, section_path, document_id)
                    SELECT 'delete', rowid, source_text, section_path, document_id 
                    FROM chunks 
                    WHERE document_id = ?;
                """, (clean_doc_id,))
            except Exception:
                pass
            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (clean_doc_id,))

            for c in chunks_to_insert:
                cursor.execute("""
                    INSERT INTO chunks (
                        chunk_id, document_id, section_path, source_text, embedding_text,
                        previous_chunk_id, next_chunk_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["chunk_id"],
                    c["document_id"],
                    json.dumps(c["section_path"]),
                    c["source_text"],
                    c["embedding_text"],
                    c["previous_chunk_id"],
                    c["next_chunk_id"],
                    c["metadata_json"]
                ))
                new_rowid = cursor.lastrowid
                try:
                    cursor.execute("""
                        INSERT INTO chunks_fts (rowid, source_text, section_path, document_id)
                        VALUES (?, ?, ?, ?);
                    """, (new_rowid, c["source_text"], json.dumps(c["section_path"]), c["document_id"]))
                except Exception:
                    pass

            conn.commit()

        # Save JSON file for document viewer
        try:
            reg_dir = settings.DATA_DIR / "regulations"
            reg_dir.mkdir(parents=True, exist_ok=True)
            json_file = reg_dir / f"{clean_doc_id}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(easa_style_json, f, indent=2, ensure_ascii=False)
        except Exception as file_err:
            print(f"Warning: could not save Note JSON representation: {file_err}")

        # Vector embedding
        is_embedded = False
        if req.auto_embed:
            embedded_count = embed_chunks_for_document(chunks_to_insert)
            if embedded_count > 0:
                is_embedded = True
                doc_metadata["is_embedded"] = True
                with get_db_connection() as conn_up:
                    conn_up.execute("UPDATE documents SET metadata_json = ? WHERE document_id = ?", (json.dumps(doc_metadata), clean_doc_id))
                    conn_up.commit()

        # Flush catalog cache
        global _CATALOG_CACHE
        _CATALOG_CACHE["timestamp"] = 0
        _CATALOG_CACHE["items"] = []

        return {
            "success": True,
            "document_id": clean_doc_id,
            "title": req.title.strip(),
            "chunk_count": len(chunks_to_insert),
            "is_embedded": is_embedded,
            "message": f"Successfully created and indexed note '{req.title.strip()}' with {len(chunks_to_insert)} sections." + (" Vector embeddings generated." if is_embedded else "")
        }

    except Exception as e:
        print(f"Error creating note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create note: {str(e)}")


@router.get("/notes", response_model=List[NoteSummaryItem], tags=["REGULATIONS"])
def api_list_notes(project: Optional[str] = Query(None, description="Optional filter by project")):
    """Lists all user-generated notes, daily journals, and meeting minutes."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.document_id, d.title, d.date, d.source, d.metadata_json,
                       COUNT(c.chunk_id) as chunk_count
                FROM documents d
                LEFT JOIN chunks c ON d.document_id = c.document_id
                WHERE d.document_id LIKE 'NOTE_%' OR d.metadata_json LIKE '%"origin": "note"%'
                GROUP BY d.document_id
                ORDER BY d.rowid DESC;
            """)
            rows = cursor.fetchall()

            today_str = time.strftime("%Y-%m-%d")
            notes = []
            for r in rows:
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                
                note_proj = meta.get("project") or ""
                if project and project.lower() not in note_proj.lower():
                    continue

                author_val = meta.get("created_by") or meta.get("author") or r["source"] or "User"
                is_indef = bool(meta.get("is_indefinite", True))
                exp_date = meta.get("expires_at")
                is_exp = False
                if not is_indef and exp_date:
                    is_exp = str(exp_date).strip() < today_str

                keywords_val = meta.get("keywords") or meta.get("tags") or []

                notes.append({
                    "document_id": r["document_id"],
                    "title": r["title"] or r["document_id"],
                    "note_type": meta.get("note_type") or "general_note",
                    "date": r["date"] or "",
                    "author": author_val,
                    "created_by": author_val,
                    "project": note_proj,
                    "tags": meta.get("tags") or [],
                    "keywords": keywords_val,
                    "is_indefinite": is_indef,
                    "expires_at": exp_date if not is_indef else None,
                    "is_expired": is_exp,
                    "chunk_count": r["chunk_count"] or 0,
                    "is_embedded": bool(meta.get("is_embedded", False)),
                    "created_at": meta.get("created_at") or r["date"] or ""
                })
            return notes
    except Exception as e:
        print(f"Error listing notes: {e}")
        return []


@router.get("/notes/{document_id}", response_model=NoteDetailResponse, tags=["REGULATIONS"])
def api_get_note(document_id: str):
    """Retrieves full details, structured sections, and markdown of a specific note."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,))
            doc_row = cursor.fetchone()
            if not doc_row:
                raise HTTPException(status_code=404, detail="Note not found")

            meta = {}
            if doc_row["metadata_json"]:
                try:
                    meta = json.loads(doc_row["metadata_json"])
                except Exception:
                    pass

            cursor.execute("""
                SELECT chunk_id, section_path, source_text, metadata_json
                FROM chunks WHERE document_id = ?
                ORDER BY rowid ASC
            """, (document_id,))
            chunk_rows = cursor.fetchall()

            sections = []
            for cr in chunk_rows:
                cm = {}
                if cr["metadata_json"]:
                    try:
                        cm = json.loads(cr["metadata_json"])
                    except Exception:
                        pass
                
                heading = cm.get("section_title") or ""
                sec_num = cm.get("section_number") or ""
                src_txt = cr["source_text"] or ""
                content = re.sub(r'^##\s+[^\n]+\n+', '', src_txt).strip() if src_txt.startswith("## ") else src_txt

                sections.append({
                    "section_number": sec_num,
                    "heading": heading or cr["chunk_id"],
                    "content": content,
                    "tags": cm.get("tags") or []
                })

            markdown_doc = get_document_markdown_content(document_id)
            today_str = time.strftime("%Y-%m-%d")
            author_val = meta.get("created_by") or meta.get("author") or doc_row["source"] or "User"
            is_indef = bool(meta.get("is_indefinite", True))
            exp_date = meta.get("expires_at")
            is_exp = False
            if not is_indef and exp_date:
                is_exp = str(exp_date).strip() < today_str

            keywords_val = meta.get("keywords") or meta.get("tags") or []

            return {
                "document_id": doc_row["document_id"],
                "title": doc_row["title"],
                "note_type": meta.get("note_type") or "general_note",
                "date": doc_row["date"] or "",
                "author": author_val,
                "created_by": author_val,
                "project": meta.get("project") or "",
                "tags": meta.get("tags") or [],
                "keywords": keywords_val,
                "is_indefinite": is_indef,
                "expires_at": exp_date if not is_indef else None,
                "is_expired": is_exp,
                "description": meta.get("description") or "",
                "chunk_count": len(chunk_rows),
                "is_embedded": bool(meta.get("is_embedded", False)),
                "created_at": meta.get("created_at") or doc_row["created_at"] or "",
                "sections": sections,
                "markdown_doc": markdown_doc
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching note {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notes/{document_id}", tags=["REGULATIONS"])
def api_delete_note(document_id: str):
    """Deletes a note and its chunks from the database and FTS index."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO chunks_fts(chunks_fts, rowid, source_text, section_path, document_id)
                    SELECT 'delete', rowid, source_text, section_path, document_id 
                    FROM chunks 
                    WHERE document_id = ?;
                """, (document_id,))
            except Exception as fts_del_err:
                print(f"Warning: FTS delete for note: {fts_del_err}")

            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            conn.commit()

        # Remove JSON representation if present
        try:
            json_file = settings.DATA_DIR / "regulations" / f"{document_id}.json"
            if json_file.exists():
                json_file.unlink()
        except Exception:
            pass

        global _CATALOG_CACHE
        _CATALOG_CACHE["timestamp"] = 0
        _CATALOG_CACHE["items"] = []

        return {"success": True, "document_id": document_id, "message": f"Note '{document_id}' deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notes/{document_id}/embed", tags=["REGULATIONS"])
def api_embed_note(document_id: str):
    """Generates vector embeddings for a note's chunks and adds them to FAISS."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id, embedding_text FROM chunks WHERE document_id = ? ORDER BY rowid ASC", (document_id,))
            rows = cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No chunks found for note.")

            chunk_records = [{"chunk_id": r["chunk_id"], "embedding_text": r["embedding_text"]} for r in rows]
            embedded_count = embed_chunks_for_document(chunk_records)
            if embedded_count == 0:
                raise HTTPException(status_code=500, detail="Failed to generate embeddings via LM Studio. Verify LM Studio embedding service is active.")

            cursor.execute("SELECT metadata_json FROM documents WHERE document_id = ?", (document_id,))
            doc_row = cursor.fetchone()
            if doc_row and doc_row["metadata_json"]:
                meta = json.loads(doc_row["metadata_json"])
                meta["is_embedded"] = True
                cursor.execute("UPDATE documents SET metadata_json = ? WHERE document_id = ?", (json.dumps(meta), document_id))
                conn.commit()

        return {
            "success": True,
            "document_id": document_id,
            "embedded_count": embedded_count,
            "message": f"Successfully generated vector embeddings for {embedded_count} chunks in '{document_id}'."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# SKYBRARY BOOKSHELF OPERATIONS
# -------------------------------------------------------------

class SkybraryCategoryInfo(BaseModel):
    category: str
    doc_count: int

class SkybraryCategoriesResponse(BaseModel):
    total_categories: int
    categories: List[SkybraryCategoryInfo]

class SkybrarySearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    category: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    page: Optional[int] = None
    score: float
    source_text: str
    pdf_url: Optional[str] = None
    summary_url: Optional[str] = None
    pdf_filename: Optional[str] = None
    section_path: List[str] = Field(default_factory=list)

class SkybrarySearchResponse(BaseModel):
    query: str
    total_found: int
    items: List[SkybrarySearchResultItem]


@router.get("/skybrary/categories", response_model=SkybraryCategoriesResponse, tags=["REGULATIONS"])
def api_get_skybrary_categories():
    """Returns all SKYbrary Bookshelf publication categories with publication counts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                json_extract(metadata_json, '$.category') as cat,
                COUNT(document_id) as doc_count
            FROM documents
            WHERE source = 'SKYBRARY'
            GROUP BY cat
            ORDER BY doc_count DESC
        """)
        rows = cursor.fetchall()
        categories = [
            SkybraryCategoryInfo(category=r["cat"] or "Uncategorized", doc_count=r["doc_count"])
            for r in rows
        ]
        return SkybraryCategoriesResponse(
            total_categories=len(categories),
            categories=categories
        )


@router.get("/skybrary/search", response_model=SkybrarySearchResponse, tags=["SEARCH", "REGULATIONS"])
def api_search_skybrary(
    query: str = Query(..., description="Keywords or phrases to search in SKYbrary Bookshelf"),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. 'Accident Investigation')"),
    author: Optional[str] = Query(None, description="Optional publishing organization (e.g. 'EASA', 'FAA', 'UK AAIB', 'NTSB')"),
    top_k: int = Query(10, ge=1, le=100, description="Max results to return"),
    sort_by: str = Query("relevance", description="Sort order: 'relevance' or 'date'")
):
    """
    Dedicated high-speed search across 228,000+ SKYbrary Bookshelf chunks with metadata filtering.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        fts_q = build_fts_query(query)
        if not fts_q:
            return SkybrarySearchResponse(query=query, total_found=0, items=[])

        where_clauses = ["chunks_fts MATCH ?", "d.source = 'SKYBRARY'"]
        params: List[Any] = [fts_q]

        if category and category.lower() != "all":
            where_clauses.append("json_extract(d.metadata_json, '$.category') = ?")
            params.append(category)

        if author and author.lower() != "all":
            where_clauses.append("json_extract(d.metadata_json, '$.author') LIKE ?")
            params.append(f"%{author}%")

        order_by = "bm25_score ASC" if sort_by == "relevance" else "d.date DESC"

        sql = f"""
            SELECT 
                c.chunk_id,
                c.document_id,
                c.section_path,
                c.source_text,
                c.metadata_json as chunk_meta_json,
                d.title,
                d.date,
                d.metadata_json as doc_meta_json,
                bm25(chunks_fts, 1.0, 3.0, 2.0) AS bm25_score
            FROM chunks_fts f
            JOIN chunks c ON f.rowid = c.rowid
            JOIN documents d ON c.document_id = d.document_id
            WHERE {" AND ".join(where_clauses)}
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(top_k)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback for simple tokens if complex boolean query fails
            clean_words = re.sub(r'[^\w\s\-/]', ' ', query).split()
            safe_terms = [f'"{w}"' if ("-" in w or "/" in w) else w for w in clean_words if w]
            simple_q = " OR ".join(safe_terms)
            if not simple_q:
                return SkybrarySearchResponse(query=query, total_found=0, items=[])
            params[0] = simple_q
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        items = []
        for r in rows:
            doc_meta = json.loads(r["doc_meta_json"]) if r["doc_meta_json"] else {}
            chunk_meta = json.loads(r["chunk_meta_json"]) if r["chunk_meta_json"] else {}
            sec_path = json.loads(r["section_path"]) if r["section_path"] else []

            raw_bm25 = float(r["bm25_score"])
            norm_score = round(abs(raw_bm25), 4)

            items.append(SkybrarySearchResultItem(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                title=r["title"] or r["document_id"],
                category=doc_meta.get("category"),
                author=doc_meta.get("author"),
                date=r["date"],
                page=chunk_meta.get("page_start"),
                score=norm_score,
                source_text=r["source_text"] or "",
                pdf_url=doc_meta.get("pdf_url"),
                summary_url=doc_meta.get("summary_url"),
                pdf_filename=doc_meta.get("pdf_filename"),
                section_path=sec_path
            ))

        return SkybrarySearchResponse(
            query=query,
            total_found=len(items),
            items=items
        )


