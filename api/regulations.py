import sqlite3
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ingestion.core.config import settings
from ingestion.retrieval.keyword_search import build_fts_query
from ingestion.parsers.json_to_doc import find_json_file, render_document
from api.utils import get_document_metadata, log_debug_info

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
            
    # Fallback to assembling chunks from sqlite
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT source_text FROM chunks WHERE document_id = ? ORDER BY rowid", (document_id,))
            rows = c.fetchall()
            if rows:
                return "\n\n---\n\n".join([r[0] for r in rows if r[0]])
    except Exception as e:
        print(f"Error assembling chunks from sqlite for {document_id}: {e}")
        
    return ""

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
            if "easy access" in doc_low or "cs-" in doc_low or "amc" in doc_low:
                origin = "easa"
            else:
                origin = "eu"
                
            meta_dict = {}
            if r["metadata_json"]:
                try:
                    meta_dict = json.loads(r["metadata_json"])
                except Exception:
                    pass

            items.append({
                "document_id": doc_id,
                "title": clean_title,
                "raw_title": raw_title,
                "date": date,
                "origin": origin,
                "source": source,
                "chunk_count": chunk_count,
                "metadata": meta_dict
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
    source: Optional[str] = None
    chunk_count: int
    metadata: Optional[Dict[str, Any]] = None

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


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------

@router.get("/catalog", response_model=CatalogResponse, tags=["REGULATIONS"])
def api_get_regulations_catalog(
    query: Optional[str] = Query(None, description="Title-level search query (searches title and document ID)"),
    origin: Optional[str] = Query("all", description="Filter by origin: 'all', 'eu', or 'easa'"),
    sort_by: Optional[str] = Query("chunks", description="Sort by 'chunks', 'title', or 'date'"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    limit: Optional[int] = Query(500, ge=1, le=2000, description="Max regulations to return"),
    offset: Optional[int] = Query(0, ge=0, description="Pagination offset")
):
    """
    Returns the comprehensive catalog of European aviation regulations indexed in the database.
    Supports title-level search, origin filtering (EASA vs EU), and sorting by chunk size or date.
    """
    # Safely extract values if called directly outside FastAPI
    q_clean = query.strip() if (isinstance(query, str) and query.strip()) else None
    origin_str = (origin.lower() if isinstance(origin, str) else "all")
    sort_by_str = (sort_by.lower() if isinstance(sort_by, str) else "chunks")
    sort_order_str = (sort_order.lower() if isinstance(sort_order, str) else "desc")
    limit_val = limit if isinstance(limit, int) else 500
    offset_val = offset if isinstance(offset, int) else 0

    all_items = load_cached_catalog()
    filtered = all_items
    
    # 1. Filter by origin
    if origin_str != "all":
        filtered = [item for item in filtered if item["origin"] == origin_str]
        
    # 2. Title-level search
    if q_clean:
        terms = q_clean.lower().split()
        
        def matches_query(item: Dict[str, Any]) -> bool:
            text = (item["title"] + " " + item["document_id"]).lower()
            return all(term in text for term in terms)
            
        filtered = [item for item in filtered if matches_query(item)]
        
    # 3. Sorting
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
                    "score": score
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
