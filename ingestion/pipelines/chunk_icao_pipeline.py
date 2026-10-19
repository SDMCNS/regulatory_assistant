"""
ICAO Technical Documentation Ingestion Pipeline.

Processes official ICAO documentation (Conventions, Annexes 1-19, Manuals, and PANS),
extracts clean text and structural hierarchy using PyMuPDF and ICAO RAG parsing,
generates canonical SQLite-aligned chunks with context prefixes and sequential linking,
and updates SQLite (documents, chunks) and the FTS5 full-text search index.

Usage:
    python -m ingestion.pipelines.chunk_icao_pipeline
    python -m ingestion.pipelines.chunk_icao_pipeline --limit 5
    python -m ingestion.pipelines.chunk_icao_pipeline --reset
"""

import sys
import os
import json
import sqlite3
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.parsers.icao_parser import parse_icao_pdf
from ingestion.retrieval.rebuild_fts import rebuild_fts
from ingestion.core.config import settings


class ICAOPipeline:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or settings.SQLITE_PATH)
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    title TEXT,
                    language TEXT,
                    date TEXT,
                    source TEXT,
                    metadata_json TEXT,
                    is_active INTEGER DEFAULT 1,
                    superseded_by TEXT,
                    deactivation_reason TEXT
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
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_prev ON chunks(previous_chunk_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_next ON chunks(next_chunk_id)")

    def reset_icao_data(self):
        """Cleans out existing ICAO documents and chunks from SQLite."""
        print("Resetting existing ICAO records from SQLite...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Select ICAO docs
            cursor.execute("SELECT document_id FROM documents WHERE source = 'ICAO PDF' OR document_id LIKE 'ICAO_%'")
            doc_ids = [r[0] for r in cursor.fetchall()]
            if doc_ids:
                placeholders = ",".join("?" for _ in doc_ids)
                cursor.execute(f"DELETE FROM chunks WHERE document_id IN ({placeholders})", doc_ids)
                cursor.execute(f"DELETE FROM documents WHERE document_id IN ({placeholders})", doc_ids)
                conn.commit()
                print(f"Removed {len(doc_ids)} ICAO documents and their associated chunks.")
            else:
                print("No existing ICAO documents found to remove.")

    def process_pdf(self, pdf_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Parses a single ICAO PDF and returns canonical (doc_dict, chunks_list)."""
        return parse_icao_pdf(pdf_path)

    def insert_document_and_chunks(self, doc: Dict[str, Any], chunks: List[Dict[str, Any]]):
        """Inserts or replaces document and its chunks in SQLite."""
        doc_id = doc["document_id"]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Remove previous chunks for this document if re-ingesting
            cursor.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))

            # Insert document
            cursor.execute("""
                INSERT OR REPLACE INTO documents (
                    document_id, title, language, date, source, metadata_json, is_active, superseded_by, deactivation_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["document_id"],
                doc["title"],
                doc.get("language", "en"),
                doc.get("date", ""),
                doc.get("source", "ICAO PDF"),
                doc.get("metadata_json", "{}"),
                doc.get("is_active", 1),
                doc.get("superseded_by"),
                doc.get("deactivation_reason")
            ))

            # Batch insert chunks
            chunk_rows = [
                (
                    c["chunk_id"],
                    c["document_id"],
                    c["chunk_type"],
                    c["section_path"],
                    c["section_numbers"],
                    c["source_text"],
                    c["embedding_text"],
                    c["parent_chunk_id"],
                    c["previous_chunk_id"],
                    c["next_chunk_id"],
                    c["structure_json"],
                    c["references_json"],
                    c["metadata_json"],
                    c.get("is_active", 1)
                )
                for c in chunks
            ]

            cursor.executemany("""
                INSERT OR REPLACE INTO chunks (
                    chunk_id, document_id, chunk_type, section_path, section_numbers,
                    source_text, embedding_text, parent_chunk_id, previous_chunk_id, next_chunk_id,
                    structure_json, references_json, metadata_json, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, chunk_rows)

            conn.commit()

    def run(
        self,
        pdf_dir: Optional[Path] = None,
        limit: Optional[int] = None,
        reset: bool = False,
        rebuild_search_index: bool = True
    ) -> Dict[str, Any]:
        """Runs the end-to-end ICAO ingestion pipeline over targeted directory."""
        if reset:
            self.reset_icao_data()

        base_import_dir = pdf_dir or (_project_root / "ICAO" / "import_pdfs")
        root_icao_dir = _project_root / "ICAO"

        # Collect candidate PDF files
        pdf_files: List[Path] = []
        seen_stems: Set[str] = set()

        # 1. Primary import directory
        if base_import_dir.exists():
            for p in sorted(base_import_dir.glob("*.pdf")):
                if p.is_file():
                    pdf_files.append(p)
                    seen_stems.add(p.stem.lower())

        # 2. Secondary root ICAO directory (avoiding duplicate names)
        if root_icao_dir.exists():
            for p in sorted(root_icao_dir.glob("*.pdf")):
                if p.is_file() and p.stem.lower() not in seen_stems:
                    pdf_files.append(p)
                    seen_stems.add(p.stem.lower())

        if limit:
            pdf_files = pdf_files[:limit]

        total_files = len(pdf_files)
        print("\n" + "=" * 80)
        print(f"ICAO INGESTION PIPELINE: Found {total_files} PDF documents to process")
        print("=" * 80)

        ingested_docs = 0
        total_chunks = 0
        start_time = time.time()

        for idx, pdf_path in enumerate(pdf_files, 1):
            t0 = time.time()
            try:
                doc, chunks = self.process_pdf(pdf_path)
                self.insert_document_and_chunks(doc, chunks)
                elapsed = time.time() - t0
                ingested_docs += 1
                total_chunks += len(chunks)
                print(f"[{idx:02d}/{total_files:02d}] Ingested {doc['document_id']:25} | {len(chunks):4d} chunks ({elapsed:5.2f}s) - {pdf_path.name}")
            except Exception as e:
                print(f"[{idx:02d}/{total_files:02d}] ERROR ingesting {pdf_path.name}: {e}")

        total_time = time.time() - start_time
        print("\n" + "=" * 80)
        print(f"ICAO INGESTION COMPLETE: {ingested_docs}/{total_files} documents ({total_chunks} chunks) in {total_time:.2f}s")
        print("=" * 80)

        if rebuild_search_index and total_chunks > 0:
            print("\nRebuilding SQLite FTS5 Full-Text Search index...")
            rebuild_fts()

        return {
            "ingested_docs": ingested_docs,
            "total_chunks": total_chunks,
            "elapsed_seconds": total_time
        }


def main():
    parser = argparse.ArgumentParser(description="Ingest ICAO documentation into SQLite and FTS5 search index.")
    parser.add_argument("--pdf_dir", type=str, default=None, help="Directory containing ICAO PDF files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PDFs to process")
    parser.add_argument("--reset", action="store_true", help="Reset existing ICAO documents before ingestion")
    parser.add_argument("--skip_fts", action="store_true", help="Skip rebuilding FTS5 index after ingestion")
    args = parser.parse_args()

    pipeline = ICAOPipeline()
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else None
    pipeline.run(
        pdf_dir=pdf_dir,
        limit=args.limit,
        reset=args.reset,
        rebuild_search_index=not args.skip_fts
    )


if __name__ == "__main__":
    main()
