import sys
from pathlib import Path

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import sqlite3
import json
from typing import List, Dict, Any, Optional
import time

# Import ingestion logic
from ingestion.retrieval.search_chunks import search_semantic, get_query_embedding, get_embeddings_batch
from ingestion.retrieval.keyword_search import search_keywords
from ingestion.retrieval.hybrid_search import search_hybrid
from ingestion.parsers.json_to_doc import render_document, find_json_file, parse_document_sections
from ingestion.core.config import settings

# Shared API utilities
from api.utils import log_debug_info, call_lm_studio_chat, cosine_similarity, get_document_metadata
from api import research
from api import regulations

tags_metadata = [
    {
        "name": "REGULATIONS",
        "description": "Regulation catalog, multi-select download, and workspace FTS cross-document overlap analysis."
    },
    {
        "name": "SEARCH",
        "description": "Regulatory search operations (semantic vector search and SQLite FTS5 BM25 keyword search)."
    },
    {
        "name": "RESEARCH",
        "description": "Autonomous Deep Regulatory Research with recursive background jobs and citation tracking."
    },
    {
        "name": "LLM",
        "description": "Local LLM operations (contextual regulatory Q&A and structured schema extraction)."
    },
]

app = FastAPI(
    title="Regulation Assistant API",
    version="1.0.0",
    openapi_tags=tags_metadata
)
app.include_router(research.router, prefix="/research", tags=["RESEARCH"])
app.include_router(regulations.router, prefix="/regulations", tags=["REGULATIONS"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchResponse(BaseModel):
    chunk_id: str
    score: float
    raw_vector_score: Optional[float] = None
    act_prior_score: Optional[float] = None
    source: str
    document_id: str
    path: List[str]
    text: str
    metadata: Dict[str, Any]
    primary_stakeholder: Optional[str] = None
    stakeholder_scores: Optional[Dict[str, float]] = None

class SearchDocResponse(SearchResponse):
    markdown_doc: str

class KeywordSearchResponse(SearchResponse):
    expanded_terms: Optional[List[str]] = Field(
        default=None,
        description="Keywords and acronyms suggested by the LLM for query expansion, if enabled"
    )

class LLMAskRequest(BaseModel):
    prompt: str
    chunk_ids: Optional[List[str]] = None
    context_sections: Optional[List[Dict[str, Any]]] = None

class LLMExtractRequest(BaseModel):
    text: str
    json_schema: Dict[str, Any]

def get_markdown_for_doc(document_id: str) -> str:
    json_path = find_json_file(document_id)
    if not json_path:
        return ""
    try:
        return render_document(json_path)
    except Exception as e:
        print(f"Failed to render document {document_id}: {e}")
        return ""


@app.get("/search", response_model=List[SearchResponse], tags=["SEARCH"])
def api_search(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_hyde: bool = Query(False, description="Use Hypothetical Document Embeddings (HyDE)"),
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'")
):
    results = search_semantic(query, top_k, origin, use_hyde=use_hyde, stakeholder=stakeholder)
    return results

@app.get("/search/docs", response_model=List[SearchDocResponse], tags=["SEARCH"])
def api_search_docs(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_hyde: bool = Query(False, description="Use Hypothetical Document Embeddings (HyDE)"),
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'")
):
    results = search_hybrid(query, top_k, origin, use_hyde=use_hyde, stakeholder=stakeholder)
    
    enriched_results = []
    for r in results:
        r_dict = dict(r)
        r_dict["markdown_doc"] = get_markdown_for_doc(r_dict["document_id"])
        enriched_results.append(r_dict)
        
    return enriched_results


@app.get("/search/docs/{document_id:path}", tags=["SEARCH"])
def api_get_doc_markdown(
    document_id: str, 
    query: str = Query(None, description="Optional search query to semantically score sections")
):
    """
    Retrieve full markdown document and optionally semantic scores for its sections.
    """
    json_path = find_json_file(document_id)
    if not json_path:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    md_text = render_document(json_path)
    
    section_scores = []
    if query:
        # Get sections
        sections = parse_document_sections(md_text)
        
        # Get query embedding
        q_vec = get_query_embedding(query)
        if q_vec:
            # Batch embed sections
            sec_texts = [s["markdown"] for s in sections]
            # Since some documents are large, we might want to batch this, but for now we send all
            sec_vecs = get_embeddings_batch(sec_texts)
            
            for s, v in zip(sections, sec_vecs):
                score = cosine_similarity(q_vec, v) if v else 0.0
                section_scores.append({
                    "sectionId": s["id"],
                    "score": score
                })
                
    return {
        "document_id": document_id,
        "markdown_doc": md_text,
        "metadata": get_document_metadata(document_id),
        "section_scores": section_scores
    }

@app.get("/search/docs/{document_id:path}/sections", tags=["SEARCH"])
def api_get_doc_sections(document_id: str):
    """
    Retrieve structured parsed sections for a specific regulation document.
    Returns a list of sections with metadata (id, title, type) and individual markdown text.
    """
    json_path = find_json_file(document_id)
    if not json_path:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    md_text = render_document(json_path)
    sections = parse_document_sections(md_text)
    return {
        "document_id": document_id,
        "total_sections": len(sections),
        "sections": sections
    }

@app.get("/search/keyword", response_model=List[KeywordSearchResponse], tags=["SEARCH"])
def api_search_keyword(
    query: str = Query(..., description="Keywords, acronyms, or search terms to match"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_llm: bool = Query(True, description="Enable LLM keyword expansion (synonyms, acronyms)")
):
    """
    Perform high-speed keyword search using SQLite FTS5 with BM25 ranking and Porter stemming.
    Ideal for short queries, acronyms (e.g. ATSEP, AMC-20), and specific regulatory terms.
    Optionally uses local LLM to expand queries with synonyms and domain terms.
    """
    results = search_keywords(query=query, top_k=top_k, origin=origin, use_llm_expansion=use_llm)
    return results

@app.get("/search/hybrid", response_model=List[KeywordSearchResponse], tags=["SEARCH"])
def api_search_hybrid(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_hyde: bool = Query(False, description="Use HyDE for the semantic component")
):
    """
    Perform Reciprocal Rank Fusion (RRF) between semantic vector search and BM25 keyword search.
    """
    results = search_hybrid(query=query, top_k=top_k, origin=origin, use_hyde=use_hyde)
    return results

@app.post("/llm/ask", tags=["LLM"])
def api_llm_ask(request: LLMAskRequest):
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        raise HTTPException(status_code=500, detail="Database not found")
        
    chunk_texts = {}
    
    # If chunk_ids are missing or just the Swagger default, do the search automatically!
    active_chunk_ids = request.chunk_ids or []
    if active_chunk_ids == ["string"]:
        active_chunk_ids = []
        
    if not active_chunk_ids and (not request.context_sections or len(request.context_sections) == 0):
        log_debug_info("API /llm/ask - DOING AUTO SEARCH", request.prompt)
        search_results = search_hybrid(request.prompt, top_k=5, use_hyde=False)
        active_chunk_ids = [res["chunk_id"] for res in search_results]

    log_debug_info("API /llm/ask - INCOMING/AUTO CHUNK IDs", active_chunk_ids)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for chunk_id in active_chunk_ids:
            # Small-to-Big: Sliding Window Retrieval
            cursor.execute("SELECT previous_chunk_id, next_chunk_id, source_text FROM chunks WHERE chunk_id = ?", (chunk_id,))
            row = cursor.fetchone()
            if row:
                prev_id, next_id, text = row
                context_text = text
                
                # Fetch previous chunk for context
                if prev_id:
                    cursor.execute("SELECT source_text FROM chunks WHERE chunk_id = ?", (prev_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        context_text = f"[Previous Context]\n{p_row[0]}\n\n[Matched Section]\n{context_text}"
                        
                # Fetch next chunk for context
                if next_id:
                    cursor.execute("SELECT source_text FROM chunks WHERE chunk_id = ?", (next_id,))
                    n_row = cursor.fetchone()
                    if n_row:
                        context_text = f"{context_text}\n\n[Following Context]\n{n_row[0]}"
                        
                chunk_texts[chunk_id] = context_text

    context_str = ""
    # Process user supplied sections if available
    if request.context_sections and len(request.context_sections) > 0:
        context_str += "--- USER BOOKMARKED SECTIONS ---\n"
        for sec in request.context_sections:
            if sec.get('enabled', True):
                context_str += f"[Section: {sec.get('title', 'Unknown')}]\n{sec.get('markdown', '')}\n\n"

    context_str += "\n\n".join([f"--- Chunk: {cid} ---\n{text}" for cid, text in chunk_texts.items()])
    
    log_debug_info("API /llm/ask - RESOLVED CONTEXT CHUNKS", list(chunk_texts.keys()))
    
    messages = [
        {"role": "system", "content": "You are a helpful regulatory assistant. Use the provided document contexts to answer the user's question."},
        {"role": "user", "content": f"Context documents:\n{context_str}\n\nQuestion:\n{request.prompt}"}
    ]
    
    answer = call_lm_studio_chat(messages)
    return {"answer": answer}

@app.post("/llm/extract", tags=["LLM"])
def api_llm_extract(request: LLMExtractRequest):
    messages = [
        {"role": "system", "content": "You are a helpful assistant that extracts information into precise JSON matching the requested schema."},
        {"role": "user", "content": f"Extract information from the following text into JSON format:\n\n{request.text}"}
    ]
    
    result = call_lm_studio_chat(messages, schema=request.json_schema)
    
    try:
        parsed_result = json.loads(result)
        return {"extracted_data": parsed_result}
    except json.JSONDecodeError:
        return {"extracted_data": result, "warning": "Failed to parse LLM response as JSON"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
