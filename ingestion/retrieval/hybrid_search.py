import json
from typing import List, Dict, Any, Optional
from ingestion.retrieval.search_chunks import search_semantic
from ingestion.retrieval.keyword_search import search_keywords

def search_hybrid(
    query: str, 
    top_k: int = 5, 
    origin: str = "all", 
    rrf_k: int = 60, 
    use_hyde: bool = False,
    stakeholder: Optional[str] = None,
    document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Performs Reciprocal Rank Fusion (RRF) between semantic vector search
    and BM25 keyword search, with optional stakeholder domain prioritization
    and optional document_id restriction.
    """
    # Run both searches (in a real prod environment we'd use asyncio for this, but synchronous is fine here)
    # We fetch more results than top_k for each to get a good intersection pool
    fetch_k = max(top_k * 2, 20)
    
    semantic_results = search_semantic(query, fetch_k, origin, use_hyde=use_hyde, stakeholder=stakeholder, document_id=document_id)
    # Disable LLM expansion for hybrid inner search to keep it fast, or keep it if desired
    keyword_results = search_keywords(query, fetch_k, origin, use_llm_expansion=False, document_id=document_id)
    
    # RRF Scoring Map: chunk_id -> { "score": float, "doc": dict }
    rrf_map: Dict[str, Dict[str, Any]] = {}
    
    # Process Semantic Results
    for rank, doc in enumerate(semantic_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_map:
            # Deep copy to avoid mutating the original dict, though shallow dict cast is fine since we modify score
            rrf_map[chunk_id] = dict(doc)
            rrf_map[chunk_id]["rrf_score"] = 0.0
            rrf_map[chunk_id]["hybrid_components"] = []
            
        rrf_map[chunk_id]["rrf_score"] += 1.0 / (rrf_k + rank + 1)
        rrf_map[chunk_id]["hybrid_components"].append(f"Semantic Rank: {rank+1}")
        
    # Process Keyword Results
    for rank, doc in enumerate(keyword_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_map:
            # Using the dict structure from keyword search
            rrf_map[chunk_id] = dict(doc)
            rrf_map[chunk_id]["rrf_score"] = 0.0
            rrf_map[chunk_id]["hybrid_components"] = []
            
        rrf_map[chunk_id]["rrf_score"] += 1.0 / (rrf_k + rank + 1)
        rrf_map[chunk_id]["hybrid_components"].append(f"Keyword Rank: {rank+1}")
        
    # Sort by accumulated RRF score descending
    sorted_results = sorted(rrf_map.values(), key=lambda x: x["rrf_score"], reverse=True)
    
    # Take the top_k
    final_results = sorted_results[:top_k]
    
    # Map back to standard schema, setting the `score` to the `rrf_score` 
    # so the frontend displays it
    for r in final_results:
        r["score"] = r["rrf_score"]
        # Make sure expanded_terms exists so frontend typing doesn't break
        if "expanded_terms" not in r:
            r["expanded_terms"] = r.get("hybrid_components", [])
            
    return final_results
