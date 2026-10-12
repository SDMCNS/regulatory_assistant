#!/usr/bin/env python3
"""
import_to_main_db.py - Import Skybrary Bookshelf chunks into central chunks.db.

Reads all generated JSON chunk files from chunks/ and batch-inserts documents
and chunks into ingestion/data/regulations/sqlite/chunks.db, followed by an
FTS5 rebuild and optimize pass.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.core.config import settings
from ingestion.retrieval.rebuild_fts import rebuild_fts


def import_chunks(
    chunks_dir: Path,
    target_db: Path,
    batch_size: int = 200,
    rebuild_fts_index: bool = True,
) -> dict:
    chunks_dir = Path(chunks_dir)
    target_db = Path(target_db)

    if not chunks_dir.exists():
        raise FileNotFoundError(f"Chunks directory not found: {chunks_dir}")
    if not target_db.exists():
        raise FileNotFoundError(f"Target DB not found: {target_db}")

    json_files = sorted(
        p for p in chunks_dir.rglob("*.chunks.json")
        if p.is_file() and not p.name.startswith("_")
    )
    print(f"Found {len(json_files)} chunk files to import into {target_db.name}")

    conn = sqlite3.connect(target_db)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")

    total_docs = 0
    total_chunks = 0
    t0 = time.time()

    doc_batch = []
    chunk_batch = []

    def flush_batches():
        nonlocal doc_batch, chunk_batch
        if not doc_batch and not chunk_batch:
            return

        with conn:
            if doc_batch:
                conn.executemany("""
                    INSERT INTO documents (document_id, title, language, date, source, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(document_id) DO UPDATE SET
                        title=excluded.title,
                        date=excluded.date,
                        source=excluded.source,
                        metadata_json=excluded.metadata_json
                """, doc_batch)

            if chunk_batch:
                conn.executemany("""
                    INSERT INTO chunks (
                        chunk_id, document_id, chunk_type, section_path, section_numbers,
                        source_text, embedding_text, parent_chunk_id, previous_chunk_id,
                        next_chunk_id, structure_json, references_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        source_text=excluded.source_text,
                        embedding_text=excluded.embedding_text,
                        metadata_json=excluded.metadata_json
                """, chunk_batch)

        doc_batch = []
        chunk_batch = []

    for idx, jf in enumerate(json_files, 1):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {jf.name}: {e}")
            continue

        doc = data.get("document", {})
        chunks = data.get("chunks", [])

        doc_batch.append((
            doc.get("document_id"),
            doc.get("title"),
            doc.get("language", "en"),
            doc.get("date", ""),
            "SKYBRARY",
            json.dumps(doc, ensure_ascii=False),
        ))
        total_docs += 1

        for c in chunks:
            chunk_batch.append((
                c.get("chunk_id"),
                c.get("document_id"),
                c.get("chunk_type", "paragraph"),
                json.dumps(c.get("section_path", []), ensure_ascii=False),
                json.dumps(c.get("section_numbers", []), ensure_ascii=False),
                c.get("source_text", ""),
                c.get("embedding_text", ""),
                c.get("parent_chunk_id"),
                c.get("previous_chunk_id"),
                c.get("next_chunk_id"),
                json.dumps(c.get("structure", {}), ensure_ascii=False),
                json.dumps(c.get("references", []), ensure_ascii=False),
                json.dumps(c.get("metadata", {}), ensure_ascii=False),
            ))
            total_chunks += 1

        if len(doc_batch) >= batch_size:
            flush_batches()
            if idx % 500 == 0 or idx == len(json_files):
                print(f"[{idx}/{len(json_files)}] Committed {total_docs} docs, {total_chunks} chunks...", flush=True)

    flush_batches()
    conn.close()

    elapsed = round(time.time() - t0, 2)
    print(f"\nSuccessfully imported {total_docs} documents and {total_chunks} chunks in {elapsed}s.")

    if rebuild_fts_index:
        print("\nRebuilding FTS5 full-text index...")
        rebuild_fts(target_db)

    return {
        "documents": total_docs,
        "chunks": total_chunks,
        "elapsed_seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Import Skybrary chunks into central SQLite DB")
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "chunks",
        help="Path to chunks/ directory",
    )
    parser.add_argument(
        "--target-db",
        type=Path,
        default=settings.SQLITE_PATH,
        help="Path to target chunks.db",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Batch commit size (docs)",
    )
    parser.add_argument(
        "--skip-fts",
        action="store_true",
        help="Skip rebuilding FTS index",
    )
    args = parser.parse_args()

    import_chunks(
        chunks_dir=args.chunks_dir,
        target_db=args.target_db,
        batch_size=args.batch_size,
        rebuild_fts_index=not args.skip_fts,
    )


if __name__ == "__main__":
    main()
