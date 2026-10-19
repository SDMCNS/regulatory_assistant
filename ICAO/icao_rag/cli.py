"""Command-Line Interface (CLI) for ICAO Document Search and Indexing."""

import argparse
import sys
from pathlib import Path
from .config import PipelineConfig
from .models import SearchFilter
from .pipeline import ICAOPipeline


def main():
    parser = argparse.ArgumentParser(
        description="ICAO Document Intelligence CLI: Parse, Filter, Chunk, Embed, and Search ICAO Manuals."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: index
    p_index = subparsers.add_parser("index", help="Index PDF documents in a directory")
    p_index.add_argument("--dir", default=".", help="Directory containing PDF files (default: .)")
    p_index.add_argument("--force", action="store_true", help="Force reindexing from scratch")

    # Subcommand: search
    p_search = subparsers.add_parser("search", help="Execute hybrid search on indexed ICAO documents")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    p_search.add_argument("--dense-weight", type=float, default=0.65, help="Dense vector weight (default: 0.65)")
    p_search.add_argument("--bm25-weight", type=float, default=0.35, help="BM25 keyword weight (default: 0.35)")
    p_search.add_argument("--doc-id", default=None, help="Filter by doc ID (e.g., doc_9562, doc_9750)")
    p_search.add_argument("--min-page", type=int, default=None, help="Minimum page number")
    p_search.add_argument("--max-page", type=int, default=None, help="Maximum page number")
    p_search.add_argument("--chapter", default=None, help="Filter by chapter title keyword")

    # Subcommand: stats
    p_stats = subparsers.add_parser("stats", help="Show indexing statistics")

    # Subcommand: check-imports
    p_chk = subparsers.add_parser("check-imports", help="Check for new or modified PDFs in import_pdfs/")

    # Subcommand: sync
    p_sync = subparsers.add_parser("sync", help="Reparse and index any new or updated PDF files")
    p_sync.add_argument("--force", action="store_true", help="Force reindexing all documents")

    # Subcommand: serve
    p_serve = subparsers.add_parser("serve", help="Run FastAPI web server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    p_serve.add_argument("--reload", action="store_true", help="Enable live auto-reload")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "index":
        pipe = ICAOPipeline()
        print(f"\nIndexing PDF documents from: {Path(args.dir).resolve()} ...")
        stats = pipe.index_directory(directory=args.dir, force_reindex=args.force)
        print("\n--- Indexing Complete ---")
        print(f"Total Documents: {stats.total_documents}")
        print(f"Total Chunks:    {stats.total_chunks}")
        print(f"Content Pages:   {stats.total_pages_indexed}")
        print(f"Vector Store:    {stats.index_path}\n")

    elif args.command == "search":
        pipe = ICAOPipeline()
        if pipe.vector_store.total_chunks == 0:
            print("No indexed documents found. Automatically indexing directory first...")
            pipe.index_directory()

        filt = None
        if args.doc_id or args.min_page or args.max_page or args.chapter:
            filt = SearchFilter(
                doc_id=args.doc_id,
                min_page=args.min_page,
                max_page=args.max_page,
                chapter_keyword=args.chapter
            )

        resp = pipe.search(
            query=args.query,
            top_k=args.top_k,
            dense_weight=args.dense_weight,
            bm25_weight=args.bm25_weight,
            filter_criteria=filt
        )

        print(f"\nSearch Query: '{resp.query}'")
        print(f"Mode: {resp.retrieval_mode} | Time: {resp.time_taken_ms:.1f}ms | Matches: {resp.total_results}\n")

        clean_highlight = lambda s: s.replace("<mark>", "\033[1;33m").replace("</mark>", "\033[0m")

        for idx, res in enumerate(resp.results, start=1):
            print(f"[{idx}] Score: {res.score:.4f} (Dense: {res.dense_score}, BM25: {res.bm25_score})")
            print(f"    Source:  {res.doc_title} ({res.filename}) - Page {res.page_number}")
            if res.chapter:
                print(f"    Chapter: {res.chapter}")
            snippet_text = clean_highlight(res.snippet)
            print(f"    Snippet: {snippet_text}\n")

    elif args.command == "stats":
        pipe = ICAOPipeline()
        stats = pipe.get_stats()
        print("\n--- ICAO Document Index Stats ---")
        print(f"Total Documents: {stats.total_documents}")
        print(f"Total Chunks:    {stats.total_chunks}")
        print(f"Embedding Model: {stats.embedding_backend} (dim={stats.embedding_dimension})")
        print("\nIndexed Documents:")
        for doc in stats.documents:
            print(f"  * {doc.doc_id}: {doc.title} ({doc.indexed_pages}/{doc.total_pages} pages, {doc.filename})")
        print()

    elif args.command == "check-imports":
        pipe = ICAOPipeline()
        status = pipe.check_import_status()
        print(f"\n--- Import Status for: {status.import_dir} ---")
        print(f"Pending changes: {'YES' if status.has_pending_changes else 'NO'} ({status.total_pending} files)")
        if status.new_files:
            print("\nNew files (not yet indexed):")
            for f in status.new_files:
                print(f"  [+] {f.filename} ({f.size_bytes} bytes, modified: {f.last_modified})")
        if status.updated_files:
            print("\nUpdated files (modified since last index):")
            for f in status.updated_files:
                print(f"  [*] {f.filename} ({f.size_bytes} bytes, modified: {f.last_modified})")
        if status.up_to_date_files:
            print(f"\nUp-to-date files: {len(status.up_to_date_files)}")
            for f in status.up_to_date_files:
                print(f"  [=] {f.filename} (indexed)")
        print()

    elif args.command == "sync":
        pipe = ICAOPipeline()
        print("\nSyncing new or updated documents from import directory...")
        res = pipe.sync_imports(force=args.force)
        print(f"Synced {res.synced_count} documents.")
        for name in res.updated_documents:
            print(f"  * Synced: {name}")
        print(f"Total indexed chunks now: {res.stats.total_chunks}\n")

    elif args.command == "serve":
        import uvicorn
        print(f"\nStarting ICAO Search API server on http://{args.host}:{args.port}")
        print(f"Swagger API Docs: http://{args.host}:{args.port}/docs")
        print(f"Web UI Dashboard: http://{args.host}:{args.port}/\n")
        uvicorn.run("icao_rag.api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
