"""
EUROCAE Standards Ingestion Pipeline.

Parses EUROCAE published standards and upcoming publications tracker,
expands aviation acronyms, generates HyDE summaries for semantic embedding,
and stores the catalog into SQLite with full-text search indexing.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from ingestion.core.config import settings
from .parser import (
    parse_published_standards,
    parse_upcoming_tracker,
    harmonize_standards
)
from .hyde import generate_hyde_embedding_text
from .storage import upsert_standards, get_eurocae_stats


def run_eurocae_pipeline(
    eurocae_dir: Optional[Path] = None,
    use_llm: bool = False
) -> int:
    """
    Executes the complete EUROCAE parsing, HyDE generation, and database ingestion pipeline.
    """
    if eurocae_dir is None:
        eurocae_dir = Path(__file__).resolve().parent

    pub_csv = eurocae_dir / "List_of_published_standards.csv"
    upcoming_csv = eurocae_dir / "ARDP_upcomming_publicationsw tracker.csv"

    print("=" * 80)
    print("EUROCAE & European Aviation Standards Ingestion Pipeline")
    print(f"Source Directory: {eurocae_dir}")
    print(f"HyDE Generation Mode: {'LLM-assisted' if use_llm else 'Domain-heuristic (Fast, offline)'}")
    print("=" * 80)

    start_time = time.time()

    # 1. Parse Published Standards
    print(f"Reading published standards from {pub_csv.name}...")
    published = parse_published_standards(pub_csv)
    print(f"Parsed {len(published)} published standards.")

    # 2. Parse Upcoming Tracker
    print(f"Reading upcoming publications tracker from {upcoming_csv.name}...")
    upcoming = parse_upcoming_tracker(upcoming_csv)
    print(f"Parsed {len(upcoming)} upcoming / ongoing standards.")

    # 3. Harmonize Standards
    print("Harmonizing standards and resolving overlaps...")
    standards = harmonize_standards(published, upcoming)
    print(f"Total harmonized standards in catalog: {len(standards)}")

    # 4. Generate HyDE Embedding Summaries
    print("\nGenerating HyDE summaries for semantic embedding representation...")
    for idx, std in enumerate(standards, 1):
        if idx % 50 == 0 or idx == len(standards):
            print(f"  Processed HyDE summaries for {idx}/{len(standards)} standards...")
        std.hyde_summary = generate_hyde_embedding_text(std, use_llm=use_llm)

    # 5. Ingest into SQLite and build FTS5 index
    print("\nUpserting standards into SQLite chunks.db and synchronizing FTS5 index...")
    count = upsert_standards(standards)
    elapsed = time.time() - start_time
    print(f"Successfully stored {count} EUROCAE standards in {elapsed:.2f} seconds.")

    # 6. Display Statistics
    stats = get_eurocae_stats()
    print("\n" + "=" * 80)
    print("EUROCAE Catalog Summary:")
    print(f"  Total Standards: {stats.get('total_standards')}")
    print("  Status Distribution:")
    for status, cnt in stats.get("status_distribution", {}).items():
        print(f"    - {status}: {cnt}")
    print("  Top Technical Domains:")
    for domain, cnt in list(stats.get("top_domains", {}).items())[:6]:
        print(f"    - {domain}: {cnt}")
    print("=" * 80)

    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest EUROCAE standards into SQLite chunks.db")
    parser.add_argument("--eurocae_dir", type=str, default=None, help="Directory containing EUROCAE CSV files")
    parser.add_argument("--use_llm", action="store_true", help="Use local LLM to generate HyDE summaries")
    args = parser.parse_args()

    dir_path = Path(args.eurocae_dir) if args.eurocae_dir else None
    run_eurocae_pipeline(dir_path, use_llm=args.use_llm)
