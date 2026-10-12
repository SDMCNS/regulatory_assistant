"""
storage.py - Storage Adapters for Skybrary Chunks (JSON & SQLite).

Supports saving chunks to individual JSON files, batch manifests, and
direct insertion into SQLite (compatible with the project's central chunks.db).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from .chunker import ChunkRecord, DocumentMetadata


def write_document_json(
    doc_meta: DocumentMetadata,
    chunks: List[ChunkRecord],
    out_path: Path,
) -> None:
    """Writes a document's metadata and chunk list to a formatted JSON file."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document": asdict(doc_meta),
        "chunk_count": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_batch_manifest(
    manifest_records: List[Dict[str, Any]],
    out_path: Path,
    total_docs: int,
    total_chunks: int,
    elapsed_seconds: float,
) -> None:
    """Writes a summary manifest JSON covering all processed documents."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "documents": manifest_records,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def save_to_sqlite(
    db_path: Path,
    doc_meta: DocumentMetadata,
    chunks: List[ChunkRecord],
    create_fts: bool = True,
) -> None:
    """
    Inserts or updates document and chunk records into SQLite matching
    the project's canonical schema.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                title TEXT,
                language TEXT,
                date TEXT,
                source TEXT,
                metadata_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT,
                chunk_type TEXT,
                section_path TEXT,
                section_numbers TEXT,
                source_text TEXT,
                embedding_text TEXT,
                parent_chunk_id TEXT,
                previous_chunk_id TEXT,
                next_chunk_id TEXT,
                structure_json TEXT,
                references_json TEXT,
                metadata_json TEXT,
                FOREIGN KEY(document_id) REFERENCES documents(document_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_prev ON chunks(previous_chunk_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_next ON chunks(next_chunk_id)")

        if create_fts:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    source_text,
                    embedding_text,
                    content='chunks',
                    content_rowid='rowid'
                )
            """)

        # Upsert document
        conn.execute("""
            INSERT INTO documents (document_id, title, language, date, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                title=excluded.title,
                date=excluded.date,
                metadata_json=excluded.metadata_json
        """, (
            doc_meta.document_id,
            doc_meta.title,
            doc_meta.language,
            doc_meta.date,
            doc_meta.source,
            json.dumps(asdict(doc_meta), ensure_ascii=False),
        ))

        # Insert chunks
        chunk_rows = []
        for c in chunks:
            chunk_rows.append((
                c.chunk_id,
                c.document_id,
                c.chunk_type,
                json.dumps(c.section_path, ensure_ascii=False),
                json.dumps(c.section_numbers, ensure_ascii=False),
                c.source_text,
                c.embedding_text,
                c.parent_chunk_id,
                c.previous_chunk_id,
                c.next_chunk_id,
                json.dumps(c.structure, ensure_ascii=False),
                json.dumps(c.references, ensure_ascii=False),
                json.dumps(c.metadata, ensure_ascii=False),
            ))

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
        """, chunk_rows)

    conn.close()
