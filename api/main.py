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
from ingestion.retrieval.search_chunks import search_semantic, get_query_embedding, get_embeddings_batch, get_chunk_surrounding_context
from ingestion.retrieval.keyword_search import search_keywords
from ingestion.retrieval.hybrid_search import search_hybrid
from ingestion.parsers.json_to_doc import render_document, find_json_file, parse_document_sections
from ingestion.core.config import settings

# Shared API utilities
from api.utils import log_debug_info, call_lm_studio_chat, call_unified_chat, cosine_similarity, get_document_metadata
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

class ContextSummaryRequest(BaseModel):
    query: str = Field(..., description="User query or legal topic being investigated")
    window: int = Field(2, ge=1, le=8, description="Number of surrounding chunks before and after")
    provider: Optional[str] = Field("local", description="LLM provider: 'local' or 'gemini'")
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None

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
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation")
):
    results = search_semantic(query, top_k, origin, use_hyde=use_hyde, stakeholder=stakeholder, document_id=document_id)
    return results

@app.get("/search/docs", response_model=List[SearchDocResponse], tags=["SEARCH"])
def api_search_docs(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_hyde: bool = Query(False, description="Use Hypothetical Document Embeddings (HyDE)"),
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation")
):
    results = search_hybrid(query, top_k, origin, use_hyde=use_hyde, stakeholder=stakeholder, document_id=document_id)
    
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
    use_llm: bool = Query(True, description="Enable LLM keyword expansion (synonyms, acronyms)"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation")
):
    """
    Perform high-speed keyword search using SQLite FTS5 with BM25 ranking and Porter stemming.
    Ideal for short queries, acronyms (e.g. ATSEP, AMC-20), and specific regulatory terms.
    Optionally uses local LLM to expand queries with synonyms and domain terms.
    """
    results = search_keywords(query=query, top_k=top_k, origin=origin, use_llm_expansion=use_llm, document_id=document_id)
    return results

@app.get("/search/hybrid", response_model=List[KeywordSearchResponse], tags=["SEARCH"])
def api_search_hybrid(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', or 'easa'"),
    use_hyde: bool = Query(False, description="Use HyDE for the semantic component"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation")
):
    """
    Perform Reciprocal Rank Fusion (RRF) between semantic vector search and BM25 keyword search.
    """
    results = search_hybrid(query=query, top_k=top_k, origin=origin, use_hyde=use_hyde, document_id=document_id)
    return results

@app.get("/search/chunks/{chunk_id:path}/context", tags=["SEARCH"])
def api_get_chunk_context(
    chunk_id: str,
    window: int = Query(2, ge=1, le=8, description="Number of chunks before and after")
):
    """
    Retrieve immediate surrounding chunks from the same document in strict sequence.
    """
    try:
        data = get_chunk_surrounding_context(chunk_id, window=window)
        return data
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunk context: {str(e)}")

@app.post("/search/chunks/{chunk_id:path}/context-summary", tags=["SEARCH"])
def api_summarize_chunk_context(
    chunk_id: str,
    req: ContextSummaryRequest
):
    """
    Grabs surrounding chunks from the same regulation in SQLite and asks the LLM
    to summarize the surrounding context and its practical implications for the user's query.
    """
    try:
        ctx = get_chunk_surrounding_context(chunk_id, window=req.window)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunk context: {str(e)}")

    doc_id = ctx["document_id"]
    doc_title = ctx["document_title"]
    all_chunks = ctx["chunks"]

    # Assemble context text with clear markers
    formatted_context_parts = []
    for c in all_chunks:
        header = f"[{'FOCAL TARGET CHUNK' if c['is_target'] else c['position'].upper() + ' CONTEXT'} - {c['chunk_id']}]"
        path_str = " > ".join(c.get("section_path", []))
        if path_str:
            header += f" (Section: {path_str})"
        formatted_context_parts.append(f"{header}\n{c['text']}")

    context_body = "\n\n---\n\n".join(formatted_context_parts)

    system_prompt = (
        "You are a specialized legal compliance and safety officer for European and EASA civil aviation regulations.\n"
        "Your task is to analyze a focal regulatory provision within its immediate surrounding document context, "
        "and explain its specific relevance and implications for an operational query."
    )

    user_prompt = (
        f"USER INVESTIGATION QUERY:\n"
        f"\"{req.query}\"\n\n"
        f"DOCUMENT: {doc_title} (ID: {doc_id})\n\n"
        f"SURROUNDING REGULATORY TEXT (in document sequence):\n"
        f"================================================\n"
        f"{context_body}\n"
        f"================================================\n\n"
        f"Please provide a structured, insightful analysis with two clear sections:\n"
        f"1. **Regulatory Context**: How does this focal provision fit into the surrounding provisions (e.g., overarching principles, definitions, prerequisites, operational conditions, or cross-references)?\n"
        f"2. **Implications for the Query**: What does this surrounding context specifically mean for the user's query \"{req.query}\"? Highlight any compliance obligations, exceptions, or operational caveats revealed by the wider context."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        summary_text = call_unified_chat(
            messages=messages,
            max_tokens=1024,
            temperature=0.2,
            provider=req.provider or "local",
            gemini_api_key=req.gemini_api_key,
            gemini_model=req.gemini_model
        )
    except Exception as e:
        log_debug_info("CONTEXT_SUMMARY_LLM_FAILED", str(e))
        summary_text = f"LLM analysis temporarily unavailable ({str(e)}). Please review the surrounding provisions directly."

    return {
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "document_title": doc_title,
        "query": req.query,
        "surrounding_chunks": all_chunks,
        "summary": summary_text
    }

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
