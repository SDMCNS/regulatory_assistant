import sys
import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

class EASAIChunkerPipeline:
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
            
    def process_file(self, file_path: Path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        document_id = file_path.stem
        main_title = document_id
        
        # Save to DB
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents (document_id, title, language, date, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (document_id, main_title, "en", "", json.dumps({"source": "EASA XML"}))
            )
            
        chunks = []
        current_heading = None
        
        for idx, item in enumerate(data):
            meta = item.get("meta", {})
            text = item.get("text", "").strip()
            
            t_type = meta.get("type", "")
            t_title = meta.get("title", "")
            t_id = meta.get("id", "")
            
            if t_type == "heading":
                current_heading = t_title
                
            chunk_type = t_type if t_type else "text"
            section_path = []
            if current_heading and t_title != current_heading:
                section_path.append(current_heading)
            section_path.append(t_title)
            
            # Create embedding text
            embedding_text = f"Document: {main_title}\n"
            if current_heading and t_title != current_heading:
                embedding_text += f"Context: {current_heading}\n"
            if t_title:
                embedding_text += f"Section: {t_title}\n"
            embedding_text += f"\n{text}"
            
            chunk_id = f"{document_id}:{t_id if t_id else idx}"
            
            chunk = {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "chunk_type": chunk_type,
                "section_path": json.dumps(section_path),
                "section_numbers": json.dumps([]),  # Could parse out numbers from title if needed
                "source_text": text,
                "embedding_text": embedding_text,
                "parent_chunk_id": current_heading, # Just using heading string as conceptual parent
                "structure_json": json.dumps({"title": t_title}),
                "references_json": "[]",
                "metadata_json": json.dumps(meta)
            }
            chunks.append(chunk)
            
        # Write chunks to DB
        with sqlite3.connect(self.db_path) as conn:
            for i, chunk in enumerate(chunks):
                # Set previous and next
                prev_id = chunks[i-1]["chunk_id"] if i > 0 else None
                next_id = chunks[i+1]["chunk_id"] if i < len(chunks) - 1 else None
                
                conn.execute("""
                    INSERT OR REPLACE INTO chunks (
                        chunk_id, document_id, chunk_type, section_path, section_numbers,
                        source_text, embedding_text, parent_chunk_id, previous_chunk_id, next_chunk_id,
                        structure_json, references_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk["chunk_id"], chunk["document_id"], chunk["chunk_type"],
                    chunk["section_path"], chunk["section_numbers"], chunk["source_text"],
                    chunk["embedding_text"], chunk["parent_chunk_id"], prev_id, next_id,
                    chunk["structure_json"], chunk["references_json"], chunk["metadata_json"]
                ))
                
        # Write chunks to json
        out_path = file_path.with_name(f"{file_path.stem}.chunks.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2)
            
        print(f"Processed {file_path.name}: {len(chunks)} chunks.")
        return chunks

def run(input_dir: str, limit: int = None):
    from ingestion.core.config import settings
    
    p = Path(input_dir)
    db_path = str(settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db")
        
    pipeline = EASAIChunkerPipeline(db_path)
    
    total_docs = 0
    total_chunks = 0
    chunk_sizes = []
    
    if p.is_file():
        files_to_process = [p]
    else:
        files_to_process = []
        for root, _, files in os.walk(input_dir):
            for file in files:
                if file.endswith(".json") and not file.endswith(".chunks.json"):
                    files_to_process.append(Path(root) / file)
                    
    for file_path in files_to_process:
        if limit and total_docs >= limit:
            break
        
        chunks = pipeline.process_file(file_path)
        total_docs += 1
        total_chunks += len(chunks)
        for c in chunks:
            size = len(c["source_text"].split()) # simple token estimate
            chunk_sizes.append(size)
            
    print("-" * 40)
    print("Documents processed:", total_docs)
    print("Chunks created:", total_chunks)
    if chunk_sizes:
        print("Average chunk size (words):", sum(chunk_sizes) // len(chunk_sizes))
        print("Median chunk size (words):", sorted(chunk_sizes)[len(chunk_sizes)//2])
        print("Largest chunk (words):", max(chunk_sizes))
    print("-" * 40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str, help="Directory containing JSON files")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Limit number of processed files")
    args = parser.parse_args()
    run(args.input_dir, args.limit)
