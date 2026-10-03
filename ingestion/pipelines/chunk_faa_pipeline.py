"""
FAA CFR Title 14 Ingestion Pipeline.

Processes GPO CFR XML files for Title 14 (Aeronautics and Space),
splits volumes into discrete Part documents, extracts clean sections and appendices,
generates SQLite-aligned chunks with hierarchical paths and embedding text,
and updates the SQLite database (documents and chunks tables) and FTS5 search index.

Usage:
    python -m ingestion.pipelines.chunk_faa_pipeline
    python -m ingestion.pipelines.chunk_faa_pipeline ./ingestion/data/FAA --reset
"""

import sys
import os
import json
import sqlite3
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.parsers.faa_cfr_parser import parse_cfr_volume
from ingestion.retrieval.rebuild_fts import rebuild_fts
from ingestion.core.config import settings


class FAACFRChunkerPipeline:
    def __init__(self, db_path: str):
        self.db_path = db_path
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

    def process_volume_file(self, xml_file: Path) -> List[Dict[str, Any]]:
        """Parses a full CFR XML volume and inserts all Parts and Chunks into SQLite."""
        print(f"\nParsing FAA volume: {xml_file.name}...")
        t0 = time.time()
        results = parse_cfr_volume(xml_file)
        parse_elapsed = time.time() - t0
        
        total_parts = len(results)
        total_chunks = sum(len(c) for _, c in results)
        print(f"Extracted {total_parts} Parts and {total_chunks} chunks in {parse_elapsed:.2f}s.")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for doc, chunks in results:
                doc_id = doc["document_id"]
                title = doc["title"]
                revised_date = doc.get("date", "2025-01-01")
                
                doc_meta = {
                    "source": "FAA XML",
                    "agency": "Federal Aviation Administration",
                    "cfr_title": 14,
                    "part": doc["part_number"],
                    "volume": doc["volume"],
                    "authority": doc.get("authority", ""),
                    "source_note": doc.get("source_note", ""),
                    "sections_count": doc.get("sections_count", 0),
                    "chunk_count": len(chunks),
                }
                
                # 1. Insert or Replace Document
                cursor.execute("""
                    INSERT OR REPLACE INTO documents (
                        document_id, title, language, date, source, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    doc_id,
                    title,
                    "en",
                    revised_date,
                    "FAA XML",
                    json.dumps(doc_meta)
                ))
                
                # 2. Insert or Replace Chunks
                for chunk in chunks:
                    cursor.execute("""
                        INSERT OR REPLACE INTO chunks (
                            chunk_id, document_id, chunk_type, section_path, section_numbers,
                            source_text, embedding_text, parent_chunk_id, previous_chunk_id,
                            next_chunk_id, structure_json, references_json, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        chunk["chunk_id"],
                        chunk["document_id"],
                        chunk["chunk_type"],
                        chunk["section_path"],
                        chunk["section_numbers"],
                        chunk["source_text"],
                        chunk["embedding_text"],
                        chunk["parent_chunk_id"],
                        chunk["previous_chunk_id"],
                        chunk["next_chunk_id"],
                        chunk["structure_json"],
                        chunk["references_json"],
                        chunk["metadata_json"]
                    ))
                    
            conn.commit()
            
        print(f"Successfully persisted {total_parts} documents and {total_chunks} chunks to database.")
        return results


def run_faa_ingestion(
    input_dir: Optional[str] = None,
    db_path: Optional[str] = None,
    rebuild_search_index: bool = True
):
    """Orchestrates FAA Title 14 ingestion across all volumes in input_dir."""
    if not input_dir:
        input_dir = str(settings.DATA_DIR / "FAA")
    if not db_path:
        db_path = str(settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db")
        
    p_dir = Path(input_dir)
    if not p_dir.exists():
        print(f"Error: FAA input directory not found: {input_dir}")
        return
        
    xml_files = sorted(p_dir.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {input_dir}")
        return
        
    pipeline = FAACFRChunkerPipeline(db_path)
    
    total_docs = 0
    total_chunks = 0
    start_time = time.time()
    
    for f in xml_files:
        results = pipeline.process_volume_file(f)
        total_docs += len(results)
        total_chunks += sum(len(c) for _, c in results)
        
    elapsed = time.time() - start_time
    print(f"\n=======================================================")
    print(f"FAA CFR Title 14 Ingestion Complete!")
    print(f"Processed {len(xml_files)} volume files.")
    print(f"Total FAA Regulations Ingested: {total_docs}")
    print(f"Total FAA Chunks Generated: {total_chunks}")
    print(f"Total Ingestion Time: {elapsed:.2f}s")
    print(f"=======================================================")
    
    if rebuild_search_index:
        print("\nRebuilding FTS5 full-text search index...")
        rebuild_fts()
        print("FTS5 search index rebuilt successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest FAA CFR Title 14 XML files into SQLite")
    parser.add_argument("input_dir", nargs="?", default=None, help="Directory containing FAA XML files")
    parser.add_argument("--db-path", default=None, help="Path to SQLite chunks.db")
    parser.add_argument("--no-fts", action="store_true", help="Skip rebuilding FTS5 index")
    args = parser.parse_args()
    
    run_faa_ingestion(
        input_dir=args.input_dir,
        db_path=args.db_path,
        rebuild_search_index=not args.no_fts
    )
