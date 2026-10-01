import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

class ChunkerPipeline:
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
        # Extract metadata
        metadata = data.get("metadata", {})
        title = data.get("title", "")
        main_title = metadata.get("title") or title
        
        # Save to DB
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents (document_id, title, language, date, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (document_id, title, metadata.get("language"), metadata.get("date"), json.dumps(metadata))
            )
            
        chunks = []
        
        # We need to walk the tree. 
        # For simplicity, let's define a recursive function.
        def walk(node, context_path, context_numbers, parent_id=None):
            if isinstance(node, list):
                for child in node:
                    walk(child, context_path, context_numbers, parent_id)
                return

            if not isinstance(node, dict):
                return
                
            node_type = node.get("type")
            text = node.get("text", "").strip()
            
            # Build context
            new_path = list(context_path)
            new_numbers = list(context_numbers)
            
            if node_type == "article":
                num = node.get("number")
                if num:
                    new_numbers.append(num)
                    new_path.append(f"Article {num}")
            elif node_type == "section":
                num = node.get("number")
                node_title = node.get("title")
                if num:
                    new_numbers.append(num)
                if node_title:
                    new_path.append(node_title)
            elif node_type == "item":
                num = node.get("number")
                if num:
                    new_numbers.append(num)
                    new_path.append(num)
            
            struct_loc = ":".join(new_numbers) if new_numbers else "0"
            chunk_id = f"{document_id}:{struct_loc}:{len(chunks)}"
            
            if text and node_type in ["paragraph", "item", "article", "text", "definition_list"]:
                # Construct embedding text
                embedding_text = f"Document: {main_title}\n"
                if new_path:
                    embedding_text += "Context:\n" + "\n".join([f"- {p}" for p in new_path]) + "\n\n"
                embedding_text += f"{text}"
                
                chunk = {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "chunk_type": node_type,
                    "section_path": json.dumps(new_path),
                    "section_numbers": json.dumps(new_numbers),
                    "source_text": text,
                    "embedding_text": embedding_text,
                    "parent_chunk_id": parent_id,
                    "structure_json": json.dumps({"node_type": node_type}),
                    "references_json": "[]",
                    "metadata_json": "{}"
                }
                chunks.append(chunk)
                current_id = chunk_id
            else:
                current_id = parent_id
                
            # Recurse
            if "content" in node:
                walk(node["content"], new_path, new_numbers, current_id)
            if "items" in node:
                walk(node["items"], new_path, new_numbers, current_id)
            if "children" in node:
                walk(node["children"], new_path, new_numbers, current_id)

        # Walk preamble
        if "preamble" in data:
            walk(data["preamble"].get("recitals", []), ["Preamble", "Recitals"], [], None)
            
        # Walk body
        if "body" in data:
            walk(data["body"], ["Body"], [], None)
            
        # Post-process: merge lists for clarity
        # If a chunk ends with ':', merge it with its logical child items
        merged_chunks = []
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            
            # Can merge if it's text, paragraph, or item ending in colon
            if chunk["chunk_type"] in ["text", "paragraph", "item"] and chunk["source_text"].strip().endswith(":"):
                j = i + 1
                items_to_merge = []
                base_numbers = json.loads(chunk["section_numbers"])
                
                while j < len(chunks) and chunks[j]["chunk_type"] == "item":
                    next_chunk = chunks[j]
                    next_numbers = json.loads(next_chunk["section_numbers"])
                    
                    # If the current chunk is an item, only consume strictly nested sub-items
                    if chunk["chunk_type"] == "item":
                        # Must be longer and share the same prefix
                        if len(next_numbers) > len(base_numbers) and next_numbers[:len(base_numbers)] == base_numbers:
                            items_to_merge.append(next_chunk)
                        else:
                            break # hit a sibling or higher-level item
                    else:
                        # If it's a text/paragraph, consume contiguous items
                        items_to_merge.append(next_chunk)
                        
                    j += 1
                
                if items_to_merge:
                    # Construct combined text
                    combined_source = chunk["source_text"]
                    for item in items_to_merge:
                        item_nums = json.loads(item["section_numbers"])
                        num_str = item_nums[-1] if item_nums else "-"
                        combined_source += f"\n{num_str} {item['source_text']}"
                    
                    # Safely rebuild embedding_text
                    original_source = chunk["source_text"]
                    if chunk["embedding_text"].endswith(original_source):
                        prefix = chunk["embedding_text"][:-len(original_source)]
                        chunk["embedding_text"] = prefix + combined_source
                    else:
                        chunk["embedding_text"] = chunk["embedding_text"] + "\n" + combined_source
                        
                    chunk["source_text"] = combined_source
                    chunk["chunk_type"] = "merged_list"
                    
                    merged_chunks.append(chunk)
                    i = j
                    continue
            
            merged_chunks.append(chunk)
            i += 1
            
        chunks = merged_chunks
            
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
    p = Path(input_dir)
    if p.is_file():
        db_path = str(p.parent / "sqlite" / "chunks.db")
    else:
        db_path = str(p / "sqlite" / "chunks.db")
        
    pipeline = ChunkerPipeline(db_path)
    
    total_docs = 0
    total_chunks = 0
    total_sections = 0
    total_definitions = 0
    total_lists = 0
    total_quotes = 0
    total_footnotes = 0
    chunk_sizes = []
    
    if p.is_file():
        files_to_process = [p]
    else:
        files_to_process = []
        for root, _, files in os.walk(input_dir):
            for file in files:
                if file.endswith(".json") and not file.endswith(".chunks.json") and file != "regulations_index.json":
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
            if c["chunk_type"] == "section": total_sections += 1
            if c["chunk_type"] == "definition_list": total_definitions += 1
            if c["chunk_type"] == "item": total_lists += 1
            if c["chunk_type"] == "quote": total_quotes += 1
            if "E0" in c["source_text"]: total_footnotes += 1
            
    print("-" * 40)
    print("Documents processed:", total_docs)
    print("Chunks created:", total_chunks)
    if chunk_sizes:
        print("Average chunk size (words):", sum(chunk_sizes) // len(chunk_sizes))
        print("Median chunk size (words):", sorted(chunk_sizes)[len(chunk_sizes)//2])
        print("Largest chunk (words):", max(chunk_sizes))
    print("Sections processed:", total_sections)
    print("Definitions:", total_definitions)
    print("List items:", total_lists)
    print("Quotes:", total_quotes)
    print("Footnotes referenced:", total_footnotes)
    print("-" * 40)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str, help="Directory containing JSON files")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Limit number of processed files")
    args = parser.parse_args()
    run(args.input_dir, args.limit)
