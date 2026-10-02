import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import argparse
import sqlite3
import requests
import textwrap

from ingestion.core.config import settings
from ingestion.core.models import EmbeddingType
from ingestion.retrieval.faiss_index import LocalVectorIndex

def get_query_embedding(query: str) -> list[float]:
    payload = {
        "input": [query],
        "model": settings.EMBEDDING_MODEL_NAME
    }
    try:
        response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Failed to generate query embedding: {e}")
        return []

def generate_hyde_document(query: str, timeout: int = 5) -> str:
    """
    Generates a hypothetical document (HyDE) using the local LLM.
    """
    prompt = (
        f"You are an expert on aviation regulations (EASA and EU).\n"
        f"Please write a short, factual passage that directly answers the following query or contains the relevant regulatory information.\n"
        f"Query: \"{query}\"\n"
        f"Passage:"
    )
    
    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a helpful expert. Generate a direct, factual passage that answers the query as if it were an excerpt from official regulations. Do not use conversational filler."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }
    
    try:
        response = requests.post(
            f"{settings.LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"HyDE generation failed: {e}")
        pass
        
    return query

def search(query: str, top_k: int = 5, origin: str = "all"):
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}.")
        return

    vector_index = LocalVectorIndex()
    
    print(f"Generating embedding for query: '{query}'...")
    query_vector = get_query_embedding(query)
    
    if not query_vector:
        print("Could not retrieve embedding for query.")
        return
        
    print(f"Searching FAISS index...")
    # Fetch more results to allow for filtering
    search_k = top_k * 10 if origin != "all" else top_k
    results = vector_index.search(query_vector, EmbeddingType.CHUNK, top_k=search_k)
    
    if not results:
        print("No results found in FAISS index.")
        return
        
    print(f"Filtering and retrieving source text from database...\n")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        results_list = []
        valid_results_count = 0
        
        for (chunk_id, score) in results:
            if valid_results_count >= top_k:
                break
                
            cursor.execute("""
                SELECT c.document_id, c.section_path, c.source_text, d.metadata_json 
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE c.chunk_id = ?
            """, (chunk_id,))
            row = cursor.fetchone()
            
            if row:
                doc_id, section_path, source_text, meta_json = row
                
                # Check origin
                is_easa = '"source": "EASA XML"' in meta_json if meta_json else False
                
                if origin == "eu" and is_easa:
                    continue
                if origin == "easa" and not is_easa:
                    continue
                
                valid_results_count += 1
                rank = valid_results_count
                
                print("="*80)
                print(f"RANK {rank} | Score: {score:.4f} | Source: {'EASA' if is_easa else 'EU'} | Chunk ID: {chunk_id}")
                results_list.append(doc_id)
                print(f"Document: {doc_id}")
                import json
                path_list = json.loads(section_path)
                print(f"Path: {' > '.join(path_list)}")
                print("-" * 80)
                print(textwrap.fill(source_text, width=80))
                print("="*80 + "\n")
            else:
                pass
                
        if valid_results_count == 0:
            print(f"No results found matching origin: {origin}")

    print("-" * 80)
    choice = input("Enter a result Rank (e.g., 1) to view its full document, or press Enter to exit: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(results_list) and results_list[idx]:
            doc_id = results_list[idx]
            print(f"\nRetrieving full document for {doc_id}...\n")
            import subprocess
            import sys
            subprocess.run([sys.executable, "-m", "ingestion.parsers.json_to_doc", doc_id])
        else:
            print("Invalid rank.")


def search_semantic(query: str, top_k: int = 5, origin: str = "all", use_hyde: bool = False) -> list[dict]:
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        return []

    # 1. Semantic Search (FAISS)
    vector_index = LocalVectorIndex()
    
    if use_hyde:
        hyde_doc = generate_hyde_document(query)
        print(f"HyDE Document generated: {hyde_doc}")
        query_vector = get_query_embedding(hyde_doc)
    else:
        query_vector = get_query_embedding(query)
    
    search_k = top_k * 10 if origin != "all" else top_k
    vector_results = []
    if query_vector:
        vector_results = vector_index.search(query_vector, EmbeddingType.CHUNK, top_k=search_k)
        
    final_results = []
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        for chunk_id, score in vector_results:
            if len(final_results) >= top_k:
                break
                
            cursor.execute("""
                SELECT c.document_id, c.section_path, c.source_text, d.metadata_json 
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE c.chunk_id = ?
            """, (chunk_id,))
            row = cursor.fetchone()
            
            if row:
                doc_id, section_path, source_text, meta_json = row
                is_easa = '"source": "EASA XML"' in meta_json if meta_json else False
                
                if origin == "eu" and is_easa:
                    continue
                if origin == "easa" and not is_easa:
                    continue
                
                import json
                path_list = json.loads(section_path)
                final_results.append({
                    "chunk_id": chunk_id,
                    "score": float(score),
                    "source": "EASA" if is_easa else "EU",
                    "document_id": doc_id,
                    "path": path_list,
                    "text": source_text,
                    "metadata": json.loads(meta_json) if meta_json else {}
                })
                
    return final_results


def main():
    parser = argparse.ArgumentParser(description="Search indexed chunks using FAISS and LM Studio")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of top results to return")
    parser.add_argument("--origin", type=str, choices=["all", "eu", "easa"], default="all", help="Filter by document origin (all, eu, easa)")
    
    args = parser.parse_args()
    search(args.query, args.top_k, args.origin)

if __name__ == "__main__":
    main()
