import json
import re
from typing import List, Dict, Any, Optional, Union
from ingestion.retrieval.search_chunks import search_semantic
from ingestion.retrieval.keyword_search import search_keywords

def search_hybrid(
    query: str, 
    top_k: int = 5, 
    origin: Union[str, List[str]] = "all", 
    origins: Optional[List[str]] = None,
    rrf_k: int = 60, 
    use_hyde: bool = False,
    stakeholder: Optional[str] = None,
    document_id: Optional[str] = None,
    deep_research: bool = False,
    keyword_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Performs Reciprocal Rank Fusion (RRF) between semantic vector search
    and BM25 keyword search, with support for document source/origin filtering,
    stakeholder domain prioritization, and optional strict keyword filtering.
    """
    # Consolidate origin / origins
    effective_origin: Any = origins if origins else origin

    # We fetch more results than top_k for each to get a good intersection pool
    fetch_k = max(top_k * 3, 25)
    
    semantic_results = search_semantic(
        query, 
        fetch_k, 
        effective_origin, 
        use_hyde=use_hyde, 
        stakeholder=stakeholder, 
        document_id=document_id, 
        deep_research=deep_research,
        keyword_filter=keyword_filter
    )
    
    # Keyword search with the main query
    keyword_results = search_keywords(
        query, 
        fetch_k, 
        effective_origin, 
        use_llm_expansion=False, 
        document_id=document_id, 
        deep_research=deep_research,
        keyword_filter=keyword_filter
    )
    
    # RRF Scoring Map: chunk_id -> { "score": float, "doc": dict }
    rrf_map: Dict[str, Dict[str, Any]] = {}
    
    # Process Semantic Results
    for rank, doc in enumerate(semantic_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_map:
            rrf_map[chunk_id] = dict(doc)
            rrf_map[chunk_id]["rrf_score"] = 0.0
            rrf_map[chunk_id]["hybrid_components"] = []
            
        rrf_map[chunk_id]["rrf_score"] += 1.0 / (rrf_k + rank + 1)
        rrf_map[chunk_id]["hybrid_components"].append(f"Semantic Rank: {rank+1}")
        
    # Process Keyword Results
    for rank, doc in enumerate(keyword_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_map:
            rrf_map[chunk_id] = dict(doc)
            rrf_map[chunk_id]["rrf_score"] = 0.0
            rrf_map[chunk_id]["hybrid_components"] = []
            
        rrf_map[chunk_id]["rrf_score"] += 1.0 / (rrf_k + rank + 1)
        rrf_map[chunk_id]["hybrid_components"].append(f"Keyword Rank: {rank+1}")
        
    # If a keyword filter is specifically provided, also query FTS5 directly with it
    if keyword_filter and keyword_filter.strip():
        kf_clean = keyword_filter.strip()
        try:
            kf_results = search_keywords(
                kf_clean, 
                fetch_k, 
                effective_origin, 
                use_llm_expansion=False, 
                document_id=document_id, 
                deep_research=deep_research
            )
            for rank, doc in enumerate(kf_results):
                chunk_id = doc["chunk_id"]
                if chunk_id not in rrf_map:
                    rrf_map[chunk_id] = dict(doc)
                    rrf_map[chunk_id]["rrf_score"] = 0.0
                    rrf_map[chunk_id]["hybrid_components"] = []
                # Provide a strong RRF boost for direct keyword filter hits
                rrf_map[chunk_id]["rrf_score"] += 1.5 / (rrf_k + rank + 1)
                rrf_map[chunk_id]["hybrid_components"].append(f"Direct Keyword Filter Hit: Rank {rank+1}")
        except Exception as e:
            print(f"[HybridSearch Warning] Keyword filter retrieval error: {e}")

    # Check and prioritize chunks matching keyword_filter
    sorted_results = sorted(rrf_map.values(), key=lambda x: x["rrf_score"], reverse=True)
    
    if keyword_filter and keyword_filter.strip():
        # Extract alphanumeric words from keyword filter
        kf_terms = [t.lower() for t in re.findall(r'\b\w+\b', keyword_filter) if len(t) > 1]
        if kf_terms:
            matching_chunks = []
            for doc in sorted_results:
                text_to_check = (doc.get("text") or doc.get("source_text") or "").lower()
                doc_id_to_check = str(doc.get("document_id") or "").lower()
                raw_path = doc.get("path") or doc.get("section_path") or []
                path_to_check = " ".join([str(p) for p in raw_path]).lower() if isinstance(raw_path, list) else str(raw_path).lower()
                combined_text = f"{doc_id_to_check} {path_to_check} {text_to_check}"
                
                # Check if all terms appear in combined chunk info
                if all(term in combined_text for term in kf_terms):
                    doc["rrf_score"] += 2.0
                    if "hybrid_components" not in doc:
                        doc["hybrid_components"] = []
                    doc["hybrid_components"].append(f"Matches Keyword Filter: '{keyword_filter.strip()}'")
                    matching_chunks.append(doc)
            
            # If any chunks strictly match the keyword filter, isolate them!
            if matching_chunks:
                sorted_results = matching_chunks

    # Take the top_k
    final_results = sorted_results[:top_k]
    
    # Map back to standard schema, setting score to rrf_score
    for r in final_results:
        r["score"] = r["rrf_score"]
        if "expanded_terms" not in r:
            r["expanded_terms"] = r.get("hybrid_components", [])
            
    return final_results
