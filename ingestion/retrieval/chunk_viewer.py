import argparse
import sqlite3
import json
from pathlib import Path
import textwrap

def list_documents(db_path: Path, limit: int = 10):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT document_id, title FROM documents LIMIT ?", (limit,))
        docs = cursor.fetchall()
        print(f"--- Top {limit} Documents ---")
        for doc_id, title in docs:
            print(f"[{doc_id}]: {title[:80]}...")

def search_documents(db_path: Path, query: str):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT document_id, title FROM documents WHERE document_id LIKE ? OR title LIKE ?", (f"%{query}%", f"%{query}%"))
        docs = cursor.fetchall()
        print(f"--- Search Results for '{query}' ---")
        for doc_id, title in docs:
            print(f"[{doc_id}]: {title[:80]}...")

def view_chunks(db_path: Path, document_id: str, limit: int = None):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE document_id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            print(f"Document ID '{document_id}' not found.")
            return
            
        print("="*80)
        print(f"DOCUMENT: {doc[0]}")
        print("="*80)
        
        query = "SELECT chunk_id, chunk_type, section_path, source_text, embedding_text FROM chunks WHERE document_id = ?"
        params = [document_id]
        if limit:
            query += " LIMIT ?"
            params.append(limit)
            
        cursor.execute(query, params)
        chunks = cursor.fetchall()
        
        for chunk_id, chunk_type, section_path, source_text, embedding_text in chunks:
            print(f"\n--- Chunk ID: {chunk_id} ({chunk_type}) ---")
            path_list = json.loads(section_path)
            print(f"Section Path: {' > '.join(path_list)}")
            print("\n[Source Text]")
            print(textwrap.fill(source_text, width=80))
            print("\n[Embedding Text]")
            print(textwrap.fill(embedding_text, width=80))
            print("-" * 80)

def view_file(file_path: Path, limit: int = None):
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return
        
    with open(file_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
        
    print("="*80)
    print(f"FILE: {file_path.name}")
    print("="*80)
    
    if limit:
        chunks = chunks[:limit]
        
    for chunk in chunks:
        print(f"\n--- Chunk ID: {chunk['chunk_id']} ({chunk['chunk_type']}) ---")
        path_list = json.loads(chunk['section_path'])
        print(f"Section Path: {' > '.join(path_list)}")
        print("\n[Source Text]")
        print(textwrap.fill(chunk['source_text'], width=80))
        print("\n[Embedding Text]")
        print(textwrap.fill(chunk['embedding_text'], width=80))
        print("-" * 80)

def main():
    from ingestion.core.config import settings
    parser = argparse.ArgumentParser(description="View chunks from the ingestion pipeline")
    parser.add_argument("--db", type=str, default=str(settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"), help="Path to chunks.db")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    parser_list = subparsers.add_parser("list", help="List available documents")
    parser_list.add_argument("-l", "--limit", type=int, default=10, help="Number of documents to show")
    
    # Search command
    parser_search = subparsers.add_parser("search", help="Search for a document by ID or Title")
    parser_search.add_argument("query", type=str, help="Search term")
    
    # View command
    parser_view = subparsers.add_parser("view", help="View chunks for a specific document ID")
    parser_view.add_argument("document_id", type=str, help="The exact document ID")
    parser_view.add_argument("-l", "--limit", type=int, default=None, help="Limit number of chunks to display")
    
    # File command
    parser_file = subparsers.add_parser("file", help="View chunks from a specific .chunks.json file")
    parser_file.add_argument("file_path", type=str, help="Path to the .chunks.json file")
    parser_file.add_argument("-l", "--limit", type=int, default=None, help="Limit number of chunks to display")
    
    args = parser.parse_args()
    
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run the chunking pipeline first.")
        return
        
    if args.command == "list":
        list_documents(db_path, args.limit)
    elif args.command == "search":
        search_documents(db_path, args.query)
    elif args.command == "view":
        view_chunks(db_path, args.document_id, args.limit)
    elif args.command == "file":
        view_file(Path(args.file_path), args.limit)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
