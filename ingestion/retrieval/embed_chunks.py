import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import sqlite3
import requests
import hashlib
from typing import List, Dict, Any
import json

from ingestion.core.config import settings
from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.retrieval.faiss_index import LocalVectorIndex

def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def is_lm_studio_available() -> bool:
    try:
        r = requests.get(f"{settings.LM_STUDIO_BASE_URL}/models", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    payload = {
        "input": texts,
        "model": settings.EMBEDDING_MODEL_NAME
    }
    try:
        response = requests.post(f"{settings.LM_STUDIO_BASE_URL}/embeddings", json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        # Sort data['data'] by index to ensure order matches input
        embeddings_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings_data]
    except Exception as e:
        print(f"Failed to generate embeddings: {e}")
        return []

def run_embedding_pipeline(db_path: Optional[Path] = None):
    if db_path is None:
        target_db = settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    else:
        target_db = Path(db_path)
    
    if not target_db.exists():
        print(f"Database not found at {target_db}. Please run chunking pipeline first.")
        return

    if not is_lm_studio_available():
        print(f"[Embeddings] LM Studio is offline at {settings.LM_STUDIO_BASE_URL}. Vector generation skipped.")
        return

    vector_index = LocalVectorIndex()
    
    # Check which chunks are already embedded in the CHUNK partition
    etype_str = EmbeddingType.CHUNK.value
    embedded_ids = set(vector_index.id_maps.get(etype_str, []))
    print(f"Found {len(embedded_ids)} already embedded chunks in FAISS index.")

    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chunk_id, embedding_text FROM chunks")
        all_chunks = cursor.fetchall()
        
    chunks_to_embed = [(c_id, text) for c_id, text in all_chunks if c_id not in embedded_ids]
    
    if not chunks_to_embed:
        print("All chunks have already been embedded.")
        return
        
    print(f"Total chunks to embed: {len(chunks_to_embed)}")
    
    batch_size = 50
    total_batches = (len(chunks_to_embed) + batch_size - 1) // batch_size
    
    for i in range(0, len(chunks_to_embed), batch_size):
        batch = chunks_to_embed[i:i+batch_size]
        batch_ids = [c[0] for c in batch]
        batch_texts = [c[1] for c in batch]
        
        print(f"Processing batch {i//batch_size + 1}/{total_batches}...")
        
        vectors = generate_embeddings(batch_texts)
        
        if not vectors or len(vectors) != len(batch):
            print(f"Failed to get correct number of embeddings for batch {i//batch_size + 1}. Skipping.")
            continue
            
        records = []
        for c_id, text, vec in zip(batch_ids, batch_texts, vectors):
            record = EmbeddingRecord(
                embedding_id=c_id,  # Use chunk_id as embedding_id
                fragment_id=c_id,
                embedding_type=EmbeddingType.CHUNK,
                model=settings.EMBEDDING_MODEL_NAME,
                dimensions=len(vec),
                vector=vec,
                text_hash=get_text_hash(text)
            )
            records.append(record)
            
        vector_index.add_records(records)
        vector_index.save()

    print("Embedding process complete!")

if __name__ == "__main__":
    run_embedding_pipeline()
