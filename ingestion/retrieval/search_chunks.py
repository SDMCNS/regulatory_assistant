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
        response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/embeddings", json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Failed to generate query embedding: {e}")
        return []

def get_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "input": batch,
            "model": settings.EMBEDDING_MODEL_NAME
        }
        try:
            response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/embeddings", json=payload, timeout=25)
            response.raise_for_status()
            data = response.json()
            all_embeddings.extend([item["embedding"] for item in data["data"]])
        except Exception as e:
            print(f"Failed to generate batch embeddings for slice {i}-{i+len(batch)}: {e}")
            all_embeddings.extend([[] for _ in batch])
    return all_embeddings


def generate_hyde_document(query: str, timeout: Optional[int] = None) -> str:
    """
    Generates a hypothetical document (HyDE) using the local LLM.
    Guarantees safe fallback to the original query if generation is empty, truncated, or timed out.
    """
    if timeout is None:
        timeout = getattr(settings, "HYDE_TIMEOUT", 90)

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
        "max_tokens": 512
    }
    
    try:
        response = requests.post(
            f"{settings.LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            choice = data["choices"][0]["message"]
            content = (choice.get("content") or "").strip()
            # If model used internal thinking and content is sparse, fallback to reasoning content
            if not content or len(content) < 25:
                reasoning = (choice.get("reasoning_content") or "").strip()
                if reasoning and len(reasoning) >= 25:
                    content = reasoning
            if content and len(content) >= 25:
                return content
    except requests.exceptions.Timeout:
        print(f"[HyDE Warning] LLM generation timed out after {timeout}s (model may be cold loading on GPU). Falling back cleanly to direct query.")
    except Exception as e:
        print(f"HyDE generation failed: {e}")
        
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


def get_chunk_surrounding_context(chunk_id: str, window: int = 2) -> dict:
    """
    Retrieves the target chunk and its immediate preceding and following chunks
    from the same document in strict sequential order.
    """
    import json
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # 1. Fetch target chunk
        cursor.execute("""
            SELECT c.rowid, c.document_id, c.section_path, c.source_text, d.title, d.metadata_json
            FROM chunks c
            LEFT JOIN documents d ON c.document_id = d.document_id
            WHERE c.chunk_id = ?
        """, (chunk_id,))
        target_row = cursor.fetchone()
        if not target_row:
            raise ValueError(f"Chunk '{chunk_id}' not found in database.")

        t_rowid, doc_id, t_path_json, t_text, doc_title, meta_json = target_row
        t_path = json.loads(t_path_json) if t_path_json else []
        meta_dict = json.loads(meta_json) if meta_json else {}

        # 2. Fetch preceding chunks in same document
        cursor.execute("""
            SELECT rowid, chunk_id, section_path, source_text
            FROM chunks
            WHERE document_id = ? AND rowid < ?
            ORDER BY rowid DESC
            LIMIT ?
        """, (doc_id, t_rowid, window))
        before_rows = cursor.fetchall()[::-1]  # Reverse to chronological order

        # 3. Fetch subsequent chunks in same document
        cursor.execute("""
            SELECT rowid, chunk_id, section_path, source_text
            FROM chunks
            WHERE document_id = ? AND rowid > ?
            ORDER BY rowid ASC
            LIMIT ?
        """, (doc_id, t_rowid, window))
        after_rows = cursor.fetchall()

        all_chunks = []
        for r in before_rows:
            all_chunks.append({
                "chunk_id": r[1],
                "section_path": json.loads(r[2]) if r[2] else [],
                "text": r[3],
                "is_target": False,
                "position": "before"
            })

        all_chunks.append({
            "chunk_id": chunk_id,
            "section_path": t_path,
            "text": t_text,
            "is_target": True,
            "position": "target"
        })

        for r in after_rows:
            all_chunks.append({
                "chunk_id": r[1],
                "section_path": json.loads(r[2]) if r[2] else [],
                "text": r[3],
                "is_target": False,
                "position": "after"
            })

        return {
            "target_chunk_id": chunk_id,
            "document_id": doc_id,
            "document_title": doc_title or meta_dict.get("title") or doc_id,
            "window": window,
            "total_chunks": len(all_chunks),
            "chunks": all_chunks
        }


def search_semantic(
    query: str, 
    top_k: int = 5, 
    origin: str = "all", 
    use_hyde: bool = False,
    stakeholder: Optional[str] = None,
    document_id: Optional[str] = None
) -> list[dict]:
    db_path = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    if not db_path.exists():
        return []

    # 1. Semantic Search (FAISS)
    vector_index = LocalVectorIndex()
    
    if use_hyde:
        hyde_doc = generate_hyde_document(query)
        if not hyde_doc or len(hyde_doc.strip()) < 15:
            hyde_doc = query
        query_vector = get_query_embedding(hyde_doc)
    else:
        # Prepend asymmetric task prefix for query retrieval
        instruction_query = f"query: Given an EU aviation regulation search query, retrieve the authoritative articles and annexes: {query}"
        query_vector = get_query_embedding(instruction_query)
        if not query_vector:
            # Fallback to raw query
            query_vector = get_query_embedding(query)
    
    if not query_vector:
        return []
    
    # 2. Hierarchical Document-Level (ACT) Prior Search
    # Check if the ACT partition has vectors to compute regulation-level relevance
    act_scores: dict[str, float] = {}
    try:
        act_index = vector_index.indices.get(EmbeddingType.ACT.value)
        if act_index and act_index.ntotal > 0:
            act_results = vector_index.search(query_vector, EmbeddingType.ACT, top_k=25)
            for doc_id, a_score in act_results:
                act_scores[doc_id] = float(a_score)
    except Exception:
        pass
    
    # 3. Chunk-Level Search
    chunk_index = vector_index.indices.get(EmbeddingType.CHUNK.value)
    total_chunks = chunk_index.ntotal if chunk_index else 50000
    if document_id:
        # Scan entire chunk index to exhaustively rank all chunks belonging to this document
        search_k = min(total_chunks, 48000)
    else:
        search_k = top_k * 15 if origin != "all" or stakeholder else top_k * 4

    vector_results = vector_index.search(query_vector, EmbeddingType.CHUNK, top_k=max(search_k, 25))
        
    candidate_records = []
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Check if stakeholder scores table exists
        has_stakeholder_table = False
        try:
            cursor.execute("SELECT 1 FROM chunk_stakeholder_scores LIMIT 1")
            has_stakeholder_table = True
        except Exception:
            pass

        for chunk_id, raw_score in vector_results:
            cursor.execute("""
                SELECT c.document_id, c.section_path, c.source_text, d.metadata_json, d.title 
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE c.chunk_id = ?
            """, (chunk_id,))
            row = cursor.fetchone()
            
            if row:
                doc_id, section_path, source_text, meta_json, doc_title = row

                # Document ID filter
                if document_id and doc_id != document_id:
                    continue

                is_easa = '"source": "EASA XML"' in meta_json if meta_json else False
                
                if origin == "eu" and is_easa:
                    continue
                if origin == "easa" and not is_easa:
                    continue
                
                # Fetch parent title if this is an ANNEX or lacks a good title
                if not doc_title or str(doc_title).upper().startswith("ANNEX") or str(doc_title).upper().startswith("APPENDIX"):
                    prefix = doc_id.split(".")[0] + "%"
                    cursor.execute("""
                        SELECT title FROM documents 
                        WHERE document_id <= ? AND document_id LIKE ? 
                          AND title NOT LIKE 'ANNEX%' 
                          AND title NOT LIKE 'APPENDIX%'
                        ORDER BY document_id DESC LIMIT 1
                    """, (doc_id, prefix))
                    p_row = cursor.fetchone()
                    if p_row and p_row[0]:
                        doc_title = p_row[0]

                import json
                path_list = json.loads(section_path) if section_path else []
                meta_dict = json.loads(meta_json) if meta_json else {}
                if doc_title:
                    meta_dict["document_title"] = doc_title

                # Read stakeholder applicability scores if available
                stakeholder_data = {}
                primary_stk = None
                stk_bonus = 0.0

                if has_stakeholder_table:
                    cursor.execute("""
                        SELECT score_airline, score_ansp, score_airport, score_economics, score_maintenance, score_flight_crew, primary_stakeholder
                        FROM chunk_stakeholder_scores WHERE chunk_id = ?
                    """, (chunk_id,))
                    s_row = cursor.fetchone()
                    if s_row:
                        stakeholder_data = {
                            "airline": s_row[0],
                            "ansp": s_row[1],
                            "airport": s_row[2],
                            "economics": s_row[3],
                            "maintenance": s_row[4],
                            "flight_crew": s_row[5],
                        }
                        primary_stk = s_row[6]
                        meta_dict["stakeholder_scores"] = stakeholder_data
                        meta_dict["primary_stakeholder"] = primary_stk

                        if stakeholder and stakeholder.lower() in stakeholder_data:
                            target_val = stakeholder_data[stakeholder.lower()]
                            # Apply a 15% additive boost proportional to stakeholder alignment
                            stk_bonus = float(target_val) * 0.15

                # Compute combined score: Chunk Score + Act Prior Boost + Stakeholder Bonus
                base_score = float(raw_score)
                act_prior = act_scores.get(doc_id, 0.0)
                if act_prior > 0:
                    combined_score = (0.75 * base_score) + (0.25 * act_prior) + stk_bonus
                else:
                    combined_score = base_score + stk_bonus

                candidate_records.append({
                    "chunk_id": chunk_id,
                    "score": round(combined_score, 4),
                    "raw_vector_score": round(base_score, 4),
                    "act_prior_score": round(act_prior, 4) if act_prior > 0 else None,
                    "source": "EASA" if is_easa else "EU",
                    "document_id": doc_id,
                    "path": path_list,
                    "text": source_text,
                    "metadata": meta_dict,
                    "primary_stakeholder": primary_stk,
                    "stakeholder_scores": stakeholder_data
                })

    # Re-rank by combined score descending
    candidate_records.sort(key=lambda x: x["score"], reverse=True)
    return candidate_records[:top_k]


def main():
    parser = argparse.ArgumentParser(description="Search indexed chunks using FAISS and LM Studio")
    parser.add_argument("query", type=str, help="Search query")
    parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of top results to return")
    parser.add_argument("--origin", type=str, choices=["all", "eu", "easa"], default="all", help="Filter by document origin (all, eu, easa)")
    
    args = parser.parse_args()
    search(args.query, args.top_k, args.origin)

if __name__ == "__main__":
    main()
