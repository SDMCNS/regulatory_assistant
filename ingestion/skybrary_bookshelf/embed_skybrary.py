#!/usr/bin/env python3
"""
embed_skybrary.py - Embed Skybrary Bookshelf Documents & Chunks into FAISS Vector Store.

Supports:
1. Embedding publications into the ACT partition (fast, enables regulation-level prior).
2. Progressively embedding chunks into the CHUNK partition in batches, saving after every batch.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.core.config import settings
from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.retrieval.embed_chunks import (
    generate_embeddings,
    get_text_hash,
    is_lm_studio_available,
)
from ingestion.retrieval.faiss_index import LocalVectorIndex


def embed_skybrary_documents(
    target_db: Path,
    vector_index: LocalVectorIndex,
    batch_size: int = 32,
    limit: Optional[int] = None,
) -> int:
    """Embeds Skybrary publications into the ACT partition."""
    etype_str = EmbeddingType.ACT.value
    embedded_ids = set(vector_index.id_maps.get(etype_str, []))
    print(f"[Documents] Found {len(embedded_ids)} already embedded documents in ACT index.")

    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT document_id, title, metadata_json 
            FROM documents 
            WHERE source = 'SKYBRARY'
        """)
        all_docs = cursor.fetchall()

    docs_to_embed = [d for d in all_docs if d[0] not in embedded_ids]
    if limit:
        docs_to_embed = docs_to_embed[:limit]

    if not docs_to_embed:
        print("[Documents] All targeted Skybrary documents are already embedded.")
        return 0

    print(f"[Documents] Embedding {len(docs_to_embed)} Skybrary documents into ACT partition...")
    total_batches = (len(docs_to_embed) + batch_size - 1) // batch_size
    embedded_count = 0

    for i in range(0, len(docs_to_embed), batch_size):
        batch = docs_to_embed[i:i + batch_size]
        texts = []
        doc_ids = []

        for doc_id, title, meta_json in batch:
            doc_ids.append(doc_id)
            meta = json.loads(meta_json) if meta_json else {}
            cat = meta.get("category", "")
            author = meta.get("author", "")
            snippet = f"Skybrary Bookshelf Publication: {title}. Category: {cat}. Published by: {author}."
            texts.append(f"passage: {snippet}")

        vectors = generate_embeddings(texts)
        if not vectors or len(vectors) != len(batch):
            print(f"[Documents] Failed batch {i // batch_size + 1}. Skipping.")
            continue

        records = []
        for doc_id, (raw_doc_id, raw_title, _), vec in zip(doc_ids, batch, vectors):
            record = EmbeddingRecord(
                embedding_id=doc_id,
                fragment_id=doc_id,
                embedding_type=EmbeddingType.ACT,
                model=settings.EMBEDDING_MODEL_NAME,
                dimensions=len(vec),
                vector=vec,
                text_hash=get_text_hash(raw_title or doc_id),
            )
            records.append(record)

        vector_index.add_records(records)
        embedded_count += len(records)
        print(f"[Documents] Batch {i // batch_size + 1}/{total_batches} done ({embedded_count}/{len(docs_to_embed)} docs).", flush=True)

    print(f"[Documents] Successfully embedded {embedded_count} Skybrary documents into ACT index.")
    return embedded_count


def embed_skybrary_chunks(
    target_db: Path,
    vector_index: LocalVectorIndex,
    batch_size: int = 32,
    limit: Optional[int] = None,
) -> int:
    """Progressively embeds Skybrary chunks into the CHUNK partition."""
    etype_str = EmbeddingType.CHUNK.value
    embedded_ids = set(vector_index.id_maps.get(etype_str, []))
    print(f"[Chunks] Found {len(embedded_ids)} total already embedded chunks in FAISS index.")

    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chunk_id, embedding_text 
            FROM chunks 
            WHERE document_id LIKE 'SKYBRARY_%'
        """)
        all_chunks = cursor.fetchall()

    chunks_to_embed = [(c_id, text) for c_id, text in all_chunks if c_id not in embedded_ids]
    if limit:
        chunks_to_embed = chunks_to_embed[:limit]

    if not chunks_to_embed:
        print("[Chunks] All targeted Skybrary chunks are already embedded.")
        return 0

    print(f"[Chunks] Total Skybrary chunks to embed: {len(chunks_to_embed)}")
    total_batches = (len(chunks_to_embed) + batch_size - 1) // batch_size
    embedded_count = 0

    for i in range(0, len(chunks_to_embed), batch_size):
        batch = chunks_to_embed[i:i + batch_size]
        batch_ids = [c[0] for c in batch]
        batch_texts = [f"passage: {c[1]}" for c in batch]

        vectors = generate_embeddings(batch_texts)
        if not vectors or len(vectors) != len(batch):
            print(f"[Chunks] Failed batch {i // batch_size + 1}. Retrying next batch.")
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
                text_hash=get_text_hash(raw_text),
            )
            records.append(record)

        vector_index.add_records(records)
        embedded_count += len(records)

        if (i // batch_size + 1) % 10 == 0 or (i // batch_size + 1) == total_batches:
            print(
                f"[Chunks] Batch {i // batch_size + 1}/{total_batches}: "
                f"Embedded {embedded_count}/{len(chunks_to_embed)} chunks...",
                flush=True,
            )

    print(f"[Chunks] Finished embedding {embedded_count} Skybrary chunks.")
    return embedded_count


def main():
    parser = argparse.ArgumentParser(description="Embed Skybrary publications and chunks into FAISS")
    parser.add_argument("--db", type=Path, default=settings.SQLITE_PATH, help="Path to chunks.db")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    parser.add_argument("--docs-only", action="store_true", help="Embed publication titles into ACT index only")
    parser.add_argument("--chunks-only", action="store_true", help="Embed chunks only")
    parser.add_argument("--limit-docs", type=int, default=None, help="Limit number of documents to embed")
    parser.add_argument("--limit-chunks", type=int, default=None, help="Limit number of chunks to embed")
    args = parser.parse_args()

    if not is_lm_studio_available():
        print(f"ERROR: LM Studio is not reachable at {settings.LM_STUDIO_BASE_URL}", file=sys.stderr)
        return 1

    print(f"Connecting to FAISS Vector Index at {settings.EMBEDDINGS_DIR}...")
    vector_index = LocalVectorIndex(settings.EMBEDDINGS_DIR, settings.EMBEDDING_DIMENSIONS)

    if not args.chunks_only:
        embed_skybrary_documents(
            target_db=args.db,
            vector_index=vector_index,
            batch_size=args.batch_size,
            limit=args.limit_docs,
        )

    if not args.docs_only:
        embed_skybrary_chunks(
            target_db=args.db,
            vector_index=vector_index,
            batch_size=args.batch_size,
            limit=args.limit_chunks,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
