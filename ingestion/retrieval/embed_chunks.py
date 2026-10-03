import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import sqlite3
import requests
import hashlib
from typing import List, Dict, Any, Optional
import json
import numpy as np
import faiss

from ingestion.core.config import settings
from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.retrieval.faiss_index import LocalVectorIndex

# Authoritative Domain / Stakeholder Reference Anchors for Aviation Regulations
STAKEHOLDER_ANCHORS: Dict[str, str] = {
    "airline": (
        "Commercial air transport, air operators, aircraft operations, flight operations, "
        "flight crew, cabin crew, AOC air operator certificate, flight duty period limitations, "
        "flight time specifications, Part-CAT commercial air transport, Part-ORO organisation requirements, "
        "fuel management, dangerous goods carriage, passenger safety, in-flight procedures."
    ),
    "ansp": (
        "Air navigation service providers, air traffic management, air traffic control, ATCO licensing, "
        "air traffic flow management, airspace design, flight information regions, separation minima, "
        "communication navigation surveillance, radar, Single European Sky, ATM/ANS common requirements, "
        "aeronautical information services, aeronautical meteorological services."
    ),
    "airport": (
        "Aerodrome operators, airport operations, runways, taxiways, apron management, "
        "ground handling services, obstacle limitation surfaces, rescue and firefighting services, "
        "bird and wildlife hazard management, aerodrome certificate, ADR aerodrome requirements, "
        "surface movement guidance, airport safety management system."
    ),
    "economics": (
        "Economic regulation of air services, operating licenses, airline ownership and effective control, "
        "air route charges, terminal charges, airport charges, performance scheme, capacity targets, "
        "cost-efficiency, slot allocation, traffic rights, air services agreements, leasing and wet-leasing, "
        "state aid, insurance requirements."
    ),
    "maintenance": (
        "Continuing airworthiness, aircraft maintenance, Part-M continuing airworthiness requirements, "
        "Part-145 maintenance organisation approval, Part-CAMO continuing airworthiness management organisations, "
        "certifying staff, airworthiness directives, maintenance release, aircraft maintenance programs, "
        "components maintenance, defect rectification."
    ),
    "flight_crew": (
        "Flight crew licensing, commercial pilot licenses, airline transport pilot license, "
        "instrument rating, class rating, type rating, flight instructors, examiner certificates, "
        "Part-FCL flight crew licensing, pilot training organisations, simulator flight training, "
        "aero-medical fitness, pilot language proficiency."
    ),
}

STAKEHOLDER_KEYS = list(STAKEHOLDER_ANCHORS.keys())


def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_lm_studio_available() -> bool:
    try:
        r = requests.get(f"{settings.LM_STUDIO_BASE_URL}/models", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
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


def embed_chunks_partition(target_db: Path, vector_index: LocalVectorIndex, batch_size: int = 50) -> int:
    """Embeds all unindexed chunks into the CHUNK partition in FAISS."""
    etype_str = EmbeddingType.CHUNK.value
    embedded_ids = set(vector_index.id_maps.get(etype_str, []))
    print(f"[Chunks] Found {len(embedded_ids)} already embedded chunks in FAISS index.")

    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chunk_id, embedding_text FROM chunks")
        all_chunks = cursor.fetchall()

    chunks_to_embed = [(c_id, text) for c_id, text in all_chunks if c_id not in embedded_ids]
    if not chunks_to_embed:
        print("[Chunks] All chunks have already been embedded.")
        return 0

    print(f"[Chunks] Total chunks to embed: {len(chunks_to_embed)}")
    total_batches = (len(chunks_to_embed) + batch_size - 1) // batch_size
    embedded_count = 0

    for i in range(0, len(chunks_to_embed), batch_size):
        batch = chunks_to_embed[i:i + batch_size]
        batch_ids = [c[0] for c in batch]
        # Prepend asymmetric task prefix for passage retrieval
        batch_texts = [f"passage: {c[1]}" for c in batch]

        print(f"[Chunks] Processing batch {i // batch_size + 1}/{total_batches} ({len(batch)} chunks)...")
        vectors = generate_embeddings(batch_texts)

        if not vectors or len(vectors) != len(batch):
            print(f"[Chunks] Failed batch {i // batch_size + 1}. Skipping.")
            continue

        records = []
        for c_id, (raw_id, raw_text), vec in zip(batch_ids, batch, vectors):
            record = EmbeddingRecord(
                embedding_id=c_id,
                fragment_id=c_id,
                embedding_type=EmbeddingType.CHUNK,
                model=settings.EMBEDDING_MODEL_NAME,
                dimensions=len(vec),
                vector=vec,
                text_hash=get_text_hash(raw_text)
            )
            records.append(record)

        vector_index.add_records(records)
        vector_index.save()
        embedded_count += len(records)

    print(f"[Chunks] Finished embedding {embedded_count} chunks.")
    return embedded_count


def embed_documents_partition(target_db: Path, vector_index: LocalVectorIndex, batch_size: int = 50) -> int:
    """
    Embeds each authoritative regulation (ACT level) using its title and scope snippet.
    This enables hierarchical 2-stage retrieval (Act-level scoping + Chunk-level precision).
    """
    etype_str = EmbeddingType.ACT.value
    embedded_ids = set(vector_index.id_maps.get(etype_str, []))
    print(f"[Acts] Found {len(embedded_ids)} already embedded documents in ACT index.")

    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT document_id, title, metadata_json FROM documents")
        all_docs = cursor.fetchall()

    docs_to_embed = [d for d in all_docs if d[0] not in embedded_ids]
    if not docs_to_embed:
        print("[Acts] All documents have already been embedded in ACT index.")
        return 0

    print(f"[Acts] Embedding {len(docs_to_embed)} documents into ACT partition...")

    # Fetch scope/preamble context for each document from initial chunks
    doc_contexts: Dict[str, str] = {}
    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        for doc_id, title, meta_json in docs_to_embed:
            cursor.execute(
                "SELECT source_text FROM chunks WHERE document_id = ? ORDER BY rowid LIMIT 4",
                (doc_id,)
            )
            rows = cursor.fetchall()
            snippet = " ".join([r[0] for r in rows])[:1500] if rows else ""
            doc_contexts[doc_id] = snippet

    total_batches = (len(docs_to_embed) + batch_size - 1) // batch_size
    embedded_count = 0

    for i in range(0, len(docs_to_embed), batch_size):
        batch = docs_to_embed[i:i + batch_size]
        batch_ids = [d[0] for d in batch]
        
        # Build passage text: Title + Scope/Recitals snippet
        batch_texts = []
        for doc_id, title, meta_json in batch:
            scope = doc_contexts.get(doc_id, "")
            text = f"passage: [EU Aviation Regulation {doc_id}] {title}. Scope & Summary: {scope}"
            batch_texts.append(text)

        print(f"[Acts] Processing batch {i // batch_size + 1}/{total_batches} ({len(batch)} acts)...")
        vectors = generate_embeddings(batch_texts)

        if not vectors or len(vectors) != len(batch):
            print(f"[Acts] Failed batch {i // batch_size + 1}. Skipping.")
            continue

        records = []
        for doc_id, text, vec in zip(batch_ids, batch_texts, vectors):
            record = EmbeddingRecord(
                embedding_id=doc_id,
                fragment_id=doc_id,
                embedding_type=EmbeddingType.ACT,
                model=settings.EMBEDDING_MODEL_NAME,
                dimensions=len(vec),
                vector=vec,
                text_hash=get_text_hash(text)
            )
            records.append(record)

        vector_index.add_records(records)
        vector_index.save()
        embedded_count += len(records)

    print(f"[Acts] Finished embedding {embedded_count} documents in ACT partition.")
    return embedded_count


def compute_stakeholder_scores(target_db: Path, vector_index: LocalVectorIndex) -> None:
    """
    Computes Concept Anchor cosine similarity across all 47k chunks against the 6
    stakeholder reference vectors (Airlines, ANSP, Airports, Economics, Maintenance, Flight Crew).
    Stores results in `chunk_stakeholder_scores` and aggregates into `document_stakeholder_scores`.
    """
    print("[Stakeholders] Computing domain applicability scores via Concept Anchors...")
    chunk_index = vector_index.indices.get(EmbeddingType.CHUNK.value)
    chunk_ids = vector_index.id_maps.get(EmbeddingType.CHUNK.value, [])

    if not chunk_index or chunk_index.ntotal == 0 or not chunk_ids:
        print("[Stakeholders] No chunk vectors available in FAISS. Skipping.")
        return

    # 1. Embed Stakeholder Reference Anchors
    anchor_texts = [f"passage: {STAKEHOLDER_ANCHORS[k]}" for k in STAKEHOLDER_KEYS]
    anchor_vectors = generate_embeddings(anchor_texts)
    if not anchor_vectors or len(anchor_vectors) != len(STAKEHOLDER_KEYS):
        print("[Stakeholders] Failed to generate anchor vectors. Skipping.")
        return

    anchor_mat = np.array(anchor_vectors, dtype=np.float32)
    faiss.normalize_L2(anchor_mat)  # (6, 3840)

    # 2. Reconstruct all chunk vectors from FAISS in batches
    n_chunks = chunk_index.ntotal
    print(f"[Stakeholders] Projecting {n_chunks} chunk vectors against {len(STAKEHOLDER_KEYS)} domain anchors...")

    # Set up SQLite tables
    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_stakeholder_scores (
                chunk_id TEXT PRIMARY KEY,
                score_airline REAL,
                score_ansp REAL,
                score_airport REAL,
                score_economics REAL,
                score_maintenance REAL,
                score_flight_crew REAL,
                primary_stakeholder TEXT,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunk_stakeholder ON chunk_stakeholder_scores(primary_stakeholder);")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_stakeholder_scores (
                document_id TEXT PRIMARY KEY,
                score_airline REAL,
                score_ansp REAL,
                score_airport REAL,
                score_economics REAL,
                score_maintenance REAL,
                score_flight_crew REAL,
                primary_stakeholder TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(document_id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_stakeholder ON document_stakeholder_scores(primary_stakeholder);")
        conn.commit()

        # Batch process projection to avoid excessive memory spikes
        batch_size = 5000
        total_batches = (n_chunks + batch_size - 1) // batch_size
        chunk_score_rows = []

        for b_idx in range(total_batches):
            start = b_idx * batch_size
            length = min(batch_size, n_chunks - start)
            
            chunk_mat = chunk_index.reconstruct_n(start, length)  # (length, 3840)
            scores = np.dot(chunk_mat, anchor_mat.T)  # (length, 6)

            for i in range(length):
                c_id = chunk_ids[start + i]
                row_scores = [float(s) for s in scores[i]]
                primary_idx = int(np.argmax(scores[i]))
                primary = STAKEHOLDER_KEYS[primary_idx]
                chunk_score_rows.append((
                    c_id,
                    round(row_scores[0], 4),  # airline
                    round(row_scores[1], 4),  # ansp
                    round(row_scores[2], 4),  # airport
                    round(row_scores[3], 4),  # economics
                    round(row_scores[4], 4),  # maintenance
                    round(row_scores[5], 4),  # flight_crew
                    primary
                ))

        cursor.executemany("""
            INSERT OR REPLACE INTO chunk_stakeholder_scores
            (chunk_id, score_airline, score_ansp, score_airport, score_economics, score_maintenance, score_flight_crew, primary_stakeholder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, chunk_score_rows)
        conn.commit()
        print(f"[Stakeholders] Stored stakeholder scores for {len(chunk_score_rows)} chunks.")

        # 3. Aggregate mean scores per document
        cursor.execute("""
            INSERT OR REPLACE INTO document_stakeholder_scores
            (document_id, score_airline, score_ansp, score_airport, score_economics, score_maintenance, score_flight_crew, primary_stakeholder)
            SELECT 
                c.document_id,
                ROUND(AVG(s.score_airline), 4) as score_airline,
                ROUND(AVG(s.score_ansp), 4) as score_ansp,
                ROUND(AVG(s.score_airport), 4) as score_airport,
                ROUND(AVG(s.score_economics), 4) as score_economics,
                ROUND(AVG(s.score_maintenance), 4) as score_maintenance,
                ROUND(AVG(s.score_flight_crew), 4) as score_flight_crew,
                'pending' as primary_stakeholder
            FROM chunk_stakeholder_scores s
            JOIN chunks c ON s.chunk_id = c.chunk_id
            GROUP BY c.document_id;
        """)
        
        # Calculate primary stakeholder for each document based on max average score
        cursor.execute("SELECT document_id, score_airline, score_ansp, score_airport, score_economics, score_maintenance, score_flight_crew FROM document_stakeholder_scores")
        doc_rows = cursor.fetchall()
        doc_updates = []
        for d in doc_rows:
            d_id = d[0]
            scores_list = list(d[1:])
            best_idx = int(np.argmax(scores_list))
            doc_updates.append((STAKEHOLDER_KEYS[best_idx], d_id))

        cursor.executemany(
            "UPDATE document_stakeholder_scores SET primary_stakeholder = ? WHERE document_id = ?",
            doc_updates
        )
        conn.commit()
        print(f"[Stakeholders] Aggregated and indexed domain profiles for {len(doc_updates)} regulations.")


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

    # Step 1: Embed remaining chunks into CHUNK partition
    embed_chunks_partition(target_db, vector_index)

    # Step 2: Embed regulations into ACT partition (Hierarchical Retrieval)
    embed_documents_partition(target_db, vector_index)

    # Step 3: Compute Concept Anchor Stakeholder Scores
    compute_stakeholder_scores(target_db, vector_index)

    print("\n[Embeddings] All vector embeddings and domain profiles generated successfully!")


if __name__ == "__main__":
    run_embedding_pipeline()
