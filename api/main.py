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
from ingestion.retrieval.reranker import RerankerService, rerank_candidate_chunks
from ingestion.parsers.json_to_doc import render_document, find_json_file, parse_document_sections
from ingestion.core.config import settings

# Shared API utilities
from api.utils import log_debug_info, call_lm_studio_chat, call_unified_chat, cosine_similarity, get_document_metadata
from api import research
from api import regulations
from api import upload
from api import consultation

tags_metadata = [
    {
        "name": "CONSULTATION",
        "description": "Document Consultation Workspace for stakeholder feedback review, common themes, sentiment analysis, and comment validity assessment."
    },
    {
        "name": "REGULATIONS",
        "description": "Regulation catalog, multi-select download, and workspace FTS cross-document overlap analysis."
    },
    {
        "name": "DOCUMENTS",
        "description": "User document upload, duplicate/update comparison, executive superseding/suppression, and multi-format ingestion."
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
app.include_router(consultation.router, prefix="/consultation", tags=["CONSULTATION"])
app.include_router(research.router, prefix="/research", tags=["RESEARCH"])
app.include_router(regulations.router, prefix="/regulations", tags=["REGULATIONS"])
app.include_router(upload.router, prefix="/documents", tags=["DOCUMENTS"])
app.include_router(upload.router, prefix="/regulations/upload", tags=["REGULATIONS"])
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
    rerank_score: Optional[float] = None
    rerank_rank: Optional[int] = None
    original_rank: Optional[int] = None

class SearchDocResponse(SearchResponse):
    markdown_doc: str

class KeywordSearchResponse(SearchResponse):
    expanded_terms: Optional[List[str]] = Field(
        default=None,
        description="Keywords and acronyms suggested by the LLM for query expansion, if enabled"
    )

class ChatMessageInput(BaseModel):
    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")

class LLMAskRequest(BaseModel):
    prompt: Optional[str] = Field(None, description="Current user prompt (single-turn or latest inquiry)")
    messages: Optional[List[ChatMessageInput]] = Field(None, description="Full conversation history for multi-turn chat")
    chunk_ids: Optional[List[str]] = Field(None, description="Explicitly targeted chunk IDs to focus context on")
    context_sections: Optional[List[Dict[str, Any]]] = Field(None, description="User bookmarked sections or manual notes")
    deep_research: bool = Field(False, description="Whether to prioritize internal project notes and operational logs")
    
    # Advanced search & scoping parameters
    origin: Optional[str] = Field("all", description="Regulatory origin filter: 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', 'note', 'user'")
    origins: Optional[List[str]] = Field(None, description="Optional list of document origins/sources to filter by: 'easa', 'eu', 'faa', 'skybrary', 'manual', 'note', 'user'")
    keyword_filter: Optional[str] = Field(None, description="Optional keyword or phrase to strictly filter and prioritize candidate chunks")
    domain: Optional[str] = Field(None, description="Operational domain or origin filter: 'all', 'flight_ops', 'airworthiness', 'atm', 'aerodromes', 'licensing', 'sms', 'easa', 'faa', 'eu', 'skybrary', 'manual', 'note', 'user'")
    domains: Optional[List[str]] = Field(None, description="Optional list of domains to filter by")
    stakeholder: Optional[str] = Field(None, description="Stakeholder domain persona: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'")
    document_ids: Optional[List[str]] = Field(None, description="Optional list of document IDs to restrict search to")
    top_k: int = Field(5, ge=1, le=15, description="Number of candidate regulatory clauses to retrieve")
    use_hyde: bool = Field(False, description="Enable Hypothetical Document Embeddings for query expansion")
    context_window: int = Field(1, ge=0, le=4, description="Sequential surrounding context window (±N provisions)")
    include_deactivated: bool = Field(False, description="Whether to include deactivated / superseded documents")
    rerank: Optional[bool] = Field(None, description="Whether to apply neural cross-encoder reranking to retrieved chunks")
    reranker_model: Optional[str] = Field(None, description="Neural reranker model name (e.g. 'text-embedding-baai-bge-reranker-v2-m3-m3')")
    
    # Provider & model parameters
    provider: Optional[str] = Field("local", description="LLM provider: 'local' (LM Studio) or 'gemini'")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API key if provider is 'gemini'")
    gemini_model: Optional[str] = Field(None, description="Gemini model name (e.g. 'gemini-3.5-flash')")
    temperature: float = Field(0.2, ge=0.0, le=1.0, description="Model generation temperature")

class LLMAskResponse(BaseModel):
    answer: str
    referenced_chunks: List[Dict[str, Any]] = []
    suggested_followups: Optional[List[str]] = None
    provider_info: Optional[Dict[str, Any]] = None

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
        return regulations.get_document_markdown_content(document_id)
    try:
        return render_document(json_path)
    except Exception as e:
        print(f"Failed to render document {document_id}: {e}")
        return regulations.get_document_markdown_content(document_id)


@app.get("/search", response_model=List[SearchResponse], tags=["SEARCH"])
def api_search(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', 'note', or 'user'"),
    use_hyde: bool = Query(False, description="Use Hypothetical Document Embeddings (HyDE)"),
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation"),
    deep_research: bool = Query(False, description="Enable deep research mode to prioritize notes"),
    rerank: bool = Query(False, description="Enable neural cross-encoder reranking"),
    reranker_model: Optional[str] = Query(None, description="Optional neural reranker model name")
):
    fetch_k = max(top_k * 6, getattr(settings, "RERANKER_CANDIDATE_POOL", 40)) if rerank else top_k
    results = search_semantic(query, fetch_k, origin, use_hyde=use_hyde, stakeholder=stakeholder, document_id=document_id, deep_research=deep_research)
    if rerank and results:
        results = rerank_candidate_chunks(query, results, model_name=reranker_model, top_k=top_k)
    return results

@app.get("/search/docs", response_model=List[SearchDocResponse], tags=["SEARCH"])
def api_search_docs(
    query: str = Query(..., description="The text to search for"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', or 'note'"),
    use_hyde: bool = Query(False, description="Use Hypothetical Document Embeddings (HyDE)"),
    stakeholder: Optional[str] = Query(None, description="Prioritize or filter by stakeholder domain: 'airline', 'ansp', 'airport', 'economics', 'maintenance', 'flight_crew'"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation"),
    deep_research: bool = Query(False, description="Enable deep research mode to prioritize notes"),
    rerank: bool = Query(False, description="Enable neural cross-encoder reranking"),
    reranker_model: Optional[str] = Query(None, description="Optional neural reranker model name")
):
    results = search_hybrid(
        query, 
        top_k, 
        origin, 
        use_hyde=use_hyde, 
        stakeholder=stakeholder, 
        document_id=document_id, 
        deep_research=deep_research,
        rerank=rerank,
        reranker_model=reranker_model
    )
    
    enriched_results = []
    for r in results:
        r_dict = dict(r)
        r_dict["markdown_doc"] = get_markdown_for_doc(r_dict["document_id"])
        enriched_results.append(r_dict)
        
    return enriched_results


@app.get("/search/docs/{document_id:path}/sections", tags=["SEARCH"])
def api_get_doc_sections(document_id: str):
    """
    Retrieve structured parsed sections for a specific regulation document.
    Returns a list of sections with metadata (id, title, type) and individual markdown text.
    """
    json_path = find_json_file(document_id)
    if json_path:
        md_text = render_document(json_path)
    else:
        md_text = regulations.get_document_markdown_content(document_id)
        if not md_text:
            raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    sections = parse_document_sections(md_text)
    return {
        "document_id": document_id,
        "total_sections": len(sections),
        "sections": sections
    }


@app.get("/search/docs/{document_id:path}", tags=["SEARCH"])
def api_get_doc_markdown(
    document_id: str, 
    query: str = Query(None, description="Optional search query to semantically score sections")
):
    """
    Retrieve full markdown document and optionally semantic scores for its sections.
    """
    json_path = find_json_file(document_id)
    if json_path:
        md_text = render_document(json_path)
    else:
        md_text = regulations.get_document_markdown_content(document_id)
        if not md_text:
            raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    
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

@app.get("/search/keyword", response_model=List[KeywordSearchResponse], tags=["SEARCH"])
def api_search_keyword(
    query: str = Query(..., description="Keywords, acronyms, or search terms to match"),
    top_k: int = Query(5, description="Number of results to return"),
    origin: str = Query("all", description="Filter by 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', or 'note'"),
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
    origin: str = Query("all", description="Filter by 'all', 'eu', 'easa', 'faa', 'manual', 'skybrary', or 'note'"),
    use_hyde: bool = Query(False, description="Use HyDE for the semantic component"),
    document_id: Optional[str] = Query(None, description="Optional document ID to restrict search to a single regulation"),
    deep_research: bool = Query(False, description="Enable deep research mode to prioritize notes"),
    rerank: bool = Query(False, description="Enable neural cross-encoder reranking"),
    reranker_model: Optional[str] = Query(None, description="Optional neural reranker model name")
):
    """
    Perform Reciprocal Rank Fusion (RRF) between semantic vector search and BM25 keyword search,
    with optional neural cross-encoder reranking.
    """
    results = search_hybrid(
        query=query, 
        top_k=top_k, 
        origin=origin, 
        use_hyde=use_hyde, 
        document_id=document_id, 
        deep_research=deep_research,
        rerank=rerank,
        reranker_model=reranker_model
    )
    return results

@app.post("/search/rerank/test", tags=["SEARCH"])
def api_test_reranker(
    payload: Dict[str, Any] = Body(default={})
):
    """
    Test status and latency of the neural reranker model.
    """
    model_name = payload.get("model_name") or settings.RERANKER_MODEL_NAME
    service = RerankerService.get_instance()
    return service.test_status(model_name=model_name)

@app.get("/search/origin-options", tags=["SEARCH"])
def api_get_origin_options():
    """Returns the list of supported document origins for filtering."""
    return [
        {"id": "all", "label": "All Sources", "description": "Search across all regulations, notes, and bookshelf documents"},
        {"id": "easa", "label": "EASA", "description": "EASA Easy Access Rules and Certification Specifications"},
        {"id": "eu", "label": "EU", "description": "European Union Formex Aviation Regulations"},
        {"id": "faa", "label": "FAA", "description": "FAA Title 14 CFR Regulations"},
        {"id": "skybrary", "label": "SKYbrary Bookshelf", "description": "SKYbrary safety reports, investigation reviews, and guidance"},
        {"id": "manual", "label": "Internal Manuals", "description": "Custom user-authored operating manuals and SOPs"},
        {"id": "note", "label": "Notes & Journals", "description": "User-generated documentation, meeting minutes, and project logs"},
    ]

@app.get("/search/skybrary", response_model=regulations.SkybrarySearchResponse, tags=["SEARCH"])
def api_search_skybrary_main(
    query: str = Query(..., description="Keywords or phrases to search in SKYbrary Bookshelf"),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. 'Accident Investigation')"),
    author: Optional[str] = Query(None, description="Optional publishing organization (e.g. 'EASA', 'FAA', 'UK AAIB', 'NTSB')"),
    top_k: int = Query(10, ge=1, le=100, description="Max results to return"),
    sort_by: str = Query("relevance", description="Sort order: 'relevance' or 'date'")
):
    """
    Dedicated high-speed search across 228,000+ SKYbrary Bookshelf chunks with metadata filtering.
    """
    return regulations.api_search_skybrary(
        query=query,
        category=category,
        author=author,
        top_k=top_k,
        sort_by=sort_by
    )

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

@app.post("/llm/ask", tags=["LLM"], response_model=LLMAskResponse)
def api_llm_ask(request: LLMAskRequest):
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        raise HTTPException(status_code=500, detail="Database not found")
        
    # 1. Resolve active user query from multi-turn messages or single prompt
    active_query = ""
    prior_messages = []
    
    if request.messages and len(request.messages) > 0:
        # Find last user message
        for msg in reversed(request.messages):
            if msg.role.lower() == "user" and msg.content.strip():
                active_query = msg.content.strip()
                break
        # Keep earlier turns as conversation history (up to last 8 turns)
        history_msgs = request.messages[:-1] if request.messages[-1].role.lower() == "user" else request.messages
        prior_messages = [
            {"role": m.role.lower(), "content": m.content}
            for m in history_msgs[-8:]
            if m.role.lower() in ("user", "assistant")
        ]
        
    if not active_query and request.prompt:
        active_query = request.prompt.strip()
        
    if not active_query:
        raise HTTPException(status_code=400, detail="A user prompt or conversation message is required.")

    # 2. Resolve target chunks (explicit or via hybrid RAG retrieval)
    active_chunk_ids = request.chunk_ids or []
    if active_chunk_ids == ["string"]:
        active_chunk_ids = []
        
    candidate_results: List[Dict[str, Any]] = []
    
    # Restrict to single document_id if provided
    target_doc_id = request.document_ids[0] if (request.document_ids and len(request.document_ids) == 1) else None

    # Resolve source/origin filter
    resolved_origin: Any = request.origins if (request.origins and len(request.origins) > 0) else (request.origin or "all")
    resolved_stakeholder = request.stakeholder

    domain_candidate = request.domain or (request.domains[0] if (request.domains and len(request.domains) > 0) else None)
    if domain_candidate and domain_candidate.lower() != "all":
        d_lower = domain_candidate.lower().strip()
        if d_lower in ("easa", "eu", "faa", "skybrary", "manual", "note"):
            resolved_origin = d_lower
        elif d_lower in ("airline", "ansp", "airport", "economics", "maintenance", "flight_crew"):
            resolved_stakeholder = d_lower
        elif d_lower in ("flight_ops", "operations", "ops"):
            resolved_stakeholder = "airline"
        elif d_lower in ("atm", "ans", "atc"):
            resolved_stakeholder = "ansp"
        elif d_lower in ("aerodromes", "aerodrome", "airport"):
            resolved_stakeholder = "airport"
        elif d_lower in ("airworthiness", "mro", "maintenance"):
            resolved_stakeholder = "maintenance"
        elif d_lower in ("licensing", "crew", "fcl", "flight_crew"):
            resolved_stakeholder = "flight_crew"

    if not active_chunk_ids:
        should_rerank = request.rerank if request.rerank is not None else getattr(settings, "RERANKER_ENABLED", True)
        log_debug_info("API /llm/ask - EXECUTING HYBRID RETRIEVAL", {
            "query": active_query,
            "origin": resolved_origin,
            "origins": request.origins,
            "domain": domain_candidate,
            "stakeholder": resolved_stakeholder,
            "keyword_filter": request.keyword_filter,
            "top_k": request.top_k,
            "use_hyde": request.use_hyde,
            "document_id": target_doc_id,
            "rerank": should_rerank,
            "reranker_model": request.reranker_model
        })
        
        search_results = search_hybrid(
            query=active_query,
            top_k=request.top_k,
            origin=resolved_origin,
            use_hyde=request.use_hyde,
            stakeholder=resolved_stakeholder,
            document_id=target_doc_id,
            deep_research=request.deep_research,
            keyword_filter=request.keyword_filter,
            rerank=should_rerank,
            reranker_model=request.reranker_model
        )
        
        # If multiple document_ids requested, filter candidates locally
        if request.document_ids and len(request.document_ids) > 1:
            allowed_docs = set(request.document_ids)
            search_results = [r for r in search_results if r.get("document_id") in allowed_docs]
            
        candidate_results = search_results
        active_chunk_ids = [res["chunk_id"] for res in search_results]

    log_debug_info("API /llm/ask - RESOLVED CHUNK IDs", active_chunk_ids)

    candidate_meta_map = {res["chunk_id"]: res for res in candidate_results}

    # 3. Retrieve chunks with surrounding context expansion and metadata
    referenced_chunks = []
    context_blocks = []
    
    for cid in active_chunk_ids:
        try:
            cand_meta = candidate_meta_map.get(cid, {})
            surrounding_info = get_chunk_surrounding_context(cid, window=request.context_window)
            doc_id = surrounding_info.get("document_id", "Unknown")
            doc_title = surrounding_info.get("document_title", doc_id)
            chunks_list = surrounding_info.get("chunks", [])
            is_active = surrounding_info.get("is_active", True)
            deact_reason = surrounding_info.get("deactivation_reason")
            supers_by = surrounding_info.get("superseded_by")
            
            # Extract target chunk details
            target_chunk = next((c for c in chunks_list if c.get("is_target")), chunks_list[0] if chunks_list else None)
            path_list = target_chunk.get("section_path", []) if target_chunk else []
            section_breadcrumbs = " > ".join(path_list) if path_list else "General Provision"
            target_text = target_chunk.get("text", "") if target_chunk else ""
            
            referenced_chunks.append({
                "chunk_id": cid,
                "document_id": doc_id,
                "title": doc_title,
                "path": path_list,
                "source": "database",
                "text": target_text[:300] + ("..." if len(target_text) > 300 else ""),
                "is_active": is_active,
                "deactivation_reason": deact_reason,
                "superseded_by": supers_by,
                "skybrary_weight": cand_meta.get("skybrary_weight"),
                "skybrary_explanation": cand_meta.get("skybrary_explanation"),
                "rerank_score": cand_meta.get("rerank_score"),
                "rerank_rank": cand_meta.get("rerank_rank"),
                "original_rank": cand_meta.get("original_rank")
            })
            
            # Combine surrounding text into unified block
            block_parts = []
            for sc in chunks_list:
                pos = sc.get("position", "")
                prefix = f"[{pos.upper()} PROVISION]" if pos != "target" else "[RELEVANT PROVISION]"
                block_parts.append(f"{prefix} (ID: {sc.get('chunk_id')}):\n{sc.get('text', '')}")
                
            combined_chunk_text = "\n\n".join(block_parts)
            
            superseded_notice = ""
            if not is_active or supers_by:
                superseded_notice = f" [NOTICE: THIS PROVISION IS FROM A SUPERSEDED/DEACTIVATED INSTRUMENT. Superseded by: {supers_by or 'Unknown'}, Reason: {deact_reason or 'Superseded'}]"

            context_blocks.append(
                f"=== REGULATORY CONTEXT [{cid}]{superseded_notice} ===\n"
                f"Document: {doc_title} ({doc_id})\n"
                f"Section: {section_breadcrumbs}\n\n"
                f"{combined_chunk_text}"
            )
        except Exception as err:
            log_debug_info("API /llm/ask - SURROUNDING CONTEXT ERROR", f"Chunk {cid}: {err}")
            # Fallback direct lookup
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.document_id, c.section_path, c.source_text, d.title
                    FROM chunks c
                    LEFT JOIN documents d ON c.document_id = d.document_id
                    WHERE c.chunk_id = ?
                """, (cid,))
                row = cursor.fetchone()
                if row:
                    doc_id, path_json, s_text, d_title = row
                    p_list = json.loads(path_json) if path_json else []
                    doc_title = d_title or doc_id
                    referenced_chunks.append({
                        "chunk_id": cid,
                        "document_id": doc_id,
                        "title": doc_title,
                        "path": p_list,
                        "source": "database",
                        "text": s_text[:300] + ("..." if len(s_text) > 300 else "")
                    })
                    context_blocks.append(
                        f"=== REGULATORY CONTEXT [{cid}] ===\n"
                        f"Document: {doc_title} ({doc_id})\n"
                        f"Section: {' > '.join(p_list)}\n\n"
                        f"{s_text}"
                    )

    # 4. Process user supplied bookmarks/sections if available
    user_notes_block = ""
    if request.context_sections and len(request.context_sections) > 0:
        active_sections = [s for s in request.context_sections if s.get("enabled", True)]
        if active_sections:
            user_notes_block = "=== USER BOOKMARKED SECTIONS & WORKSPACE NOTES ===\n" + "\n\n".join([
                f"[Section: {sec.get('title', 'User Note')}]\n{sec.get('markdown', '')}"
                for sec in active_sections
            ])

    # Combine full regulatory context
    full_context_parts = []
    if user_notes_block:
        full_context_parts.append(user_notes_block)
    if context_blocks:
        full_context_parts.append("\n\n".join(context_blocks))
    full_context_str = "\n\n".join(full_context_parts) if full_context_parts else "No specific regulatory clauses retrieved."

    # 5. Build System Prompt & Instructions
    if request.deep_research:
        sys_prompt = (
            "You are a specialized Aviation Regulatory Compliance Project Manager and Senior Legal Auditor.\n"
            "Synthesize actionable, highly structured compliance advice prioritizing operational safety, project logs, and user notes.\n"
            "Ground every conclusion directly in the referenced regulatory articles and standards.\n"
            "Format your answer with clear markdown headings, bullet points, and inline citations."
        )
    else:
        sys_prompt = (
            "You are AeroLex Assistant, an authoritative AI specialist in European and international aviation regulations (EASA, EU, FAA, ICAO).\n"
            "Your goal is to answer the user's regulatory query with clarity, legal precision, and practical compliance guidance.\n\n"
            "Guidelines:\n"
            "1. Ground your explanations directly in the provided regulatory context documents and articles.\n"
            "2. Whenever citing a rule or article, mention the document title/CELEX and specific provision (e.g. 'Regulation (EU) 2018/1139, Article 14(2)').\n"
            "3. If any referenced provisions are tagged as SUPERSEDED or DEACTIVATED, state clearly and prominently that these provisions are obsolete/superseded and advise verifying against current active consolidated instruments.\n"
            "4. If the context does not contain sufficient details to definitively settle a question, state this clearly and outline standard industry compliance practice.\n"
            "5. At the very end of your response, provide 2 to 3 logical follow-up questions the user might ask next, formatted inside a `<followups>` block, e.g.:\n"
            "<followups>\n"
            "- What are the specific training requirements under AMC1?\n"
            "- How does this compare with FAA Part 121 equivalents?\n"
            "</followups>"
        )

    # 6. Assemble Chat Messages for Unified Provider
    chat_payload_messages = [{"role": "system", "content": sys_prompt}]
    
    # Append prior conversation history
    for m in prior_messages:
        chat_payload_messages.append({"role": m["role"], "content": m["content"]})
        
    # Append latest user prompt with injected context
    user_turn_content = (
        f"--- RELEVANT REGULATORY PROVISIONS & CONTEXT ---\n"
        f"{full_context_str}\n\n"
        f"--- USER INQUIRY ---\n"
        f"{active_query}"
    )
    chat_payload_messages.append({"role": "user", "content": user_turn_content})

    # 7. Execute Call via Unified LLM Provider Router
    raw_answer = call_unified_chat(
        messages=chat_payload_messages,
        max_tokens=4096,
        temperature=request.temperature,
        provider=request.provider or "local",
        gemini_api_key=request.gemini_api_key,
        gemini_model=request.gemini_model
    )

    # 8. Extract Follow-Up Suggestions
    suggested_followups: List[str] = []
    clean_answer = raw_answer
    
    if "<followups>" in raw_answer and "</followups>" in raw_answer:
        parts = raw_answer.split("<followups>")
        clean_answer = parts[0].strip()
        followups_section = parts[1].split("</followups>")[0].strip()
        for line in followups_section.split("\n"):
            line = line.strip().lstrip("-*•0123456789. ")
            if line and len(line) > 5:
                suggested_followups.append(line)

    # Prepend warning banner if answer was derived from superseded / suppressed fallback records
    has_suppressed = any(not rc.get("is_active", True) or bool(rc.get("superseded_by")) for rc in referenced_chunks)
    all_suppressed = bool(referenced_chunks and all(not rc.get("is_active", True) or bool(rc.get("superseded_by")) for rc in referenced_chunks))
    if all_suppressed:
        notice_banner = (
            "> ⚠️ **Regulatory Status Warning:** No active regulations matched your query. "
            "The retrieved provisions originate from **superseded or deactivated instruments** (included via 0.1x fallback weight). "
            "Verify against current active consolidated amendments before applying.\n\n"
        )
        if not clean_answer.startswith("> ⚠️"):
            clean_answer = notice_banner + clean_answer
    elif has_suppressed:
        notice_banner = (
            "> ℹ️ **Regulatory Notice:** Some referenced provisions originate from **superseded or deactivated instruments** (included via 0.1x fallback weight).\n\n"
        )
        if not clean_answer.startswith("> ℹ️") and not clean_answer.startswith("> ⚠️"):
            clean_answer = notice_banner + clean_answer

    # Fallback follow-ups if model omitted tag
    if not suggested_followups and referenced_chunks:
        doc_names = list({rc["title"] for rc in referenced_chunks[:2] if rc.get("title")})
        first_doc = doc_names[0] if doc_names else "this regulation"
        suggested_followups = [
            f"What are the compliance deadlines associated with {first_doc}?",
            f"Are there any Acceptable Means of Compliance (AMC) or Guidance Material (GM) for these articles?",
            f"How does this impact stakeholder operational manuals?"
        ]

    return LLMAskResponse(
        answer=clean_answer,
        referenced_chunks=referenced_chunks,
        suggested_followups=suggested_followups,
        provider_info={
            "provider": request.provider or "local",
            "model": request.gemini_model if request.provider == "gemini" else "local-lm-studio",
            "chunks_retrieved": len(referenced_chunks),
            "origin_filter": request.origin
        }
    )

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
