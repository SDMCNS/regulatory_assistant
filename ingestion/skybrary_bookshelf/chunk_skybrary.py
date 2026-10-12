#!/usr/bin/env python3
"""
chunk_skybrary.py - Skybrary Bookshelf Chunker & Ingestion CLI.

CLI entrypoint utilizing the modular Skybrary library (ingestion.skybrary_bookshelf.lib).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add bookshelf directory to sys.path so lib can be imported directly
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lib import SkybraryPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chunk extracted Skybrary text files and link with skybrary.db metadata."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=HERE / "skybrary.db",
        help="Path to skybrary.db (default: skybrary_bookshelf/skybrary.db)",
    )
    parser.add_argument(
        "--text-dir",
        type=Path,
        default=HERE / "text",
        help="Directory containing extracted .txt files (default: skybrary_bookshelf/text)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=HERE / "chunks",
        help="Directory to save JSON chunk files (default: skybrary_bookshelf/chunks)",
    )
    parser.add_argument(
        "--sqlite-out",
        type=Path,
        default=None,
        help="Optional SQLite database path to store documents and chunks tables.",
    )
    parser.add_argument(
        "--target-words",
        type=int,
        default=350,
        help="Target word count per chunk (default: 350).",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=600,
        help="Maximum word count per chunk before splitting (default: 600).",
    )
    args = parser.parse_args()

    db_path: Path = args.db.resolve()
    text_dir: Path = args.text_dir.resolve()
    out_dir: Path = args.out_dir.resolve()
    sqlite_db: Path | None = args.sqlite_out.resolve() if args.sqlite_out else None

    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    if not text_dir.exists():
        print(f"ERROR: Text directory not found: {text_dir}", file=sys.stderr)
        return 1

    print(f"Connecting to database: {db_path.name}")
    pipeline = SkybraryPipeline(
        db_path=db_path,
        target_words=args.target_words,
        max_words=args.max_words,
    )
    print(f"Indexed {len(pipeline.linker.records_by_id)} publications from DB.")
    print(f"Processing text files from: {text_dir}")
    print(f"Output directory          : {out_dir}")
    if sqlite_db:
        print(f"SQLite output             : {sqlite_db}")
    print()

    summary = pipeline.process_all_texts(
        text_dir=text_dir,
        out_dir=out_dir,
        sqlite_db=sqlite_db,
    )

    print()
    print("=" * 72)
    print("SKYBRARY CHUNKING & LINKING SUMMARY")
    print("=" * 72)
    print(f"Total Text Files Processed : {summary['total_files']}")
    print(f"Linked with DB Record      : {summary['matched']}")
    print(f"Unmatched Files            : {summary['unmatched']}")
    print(f"Total Chunks Generated     : {summary['total_chunks']}")
    print(f"Elapsed Time               : {summary['elapsed_seconds']}s")
    print(f"Manifest Written To        : {summary['manifest_path']}")
    print("=" * 72)

    return 0 if summary["unmatched"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
