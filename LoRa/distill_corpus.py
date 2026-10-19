#!/usr/bin/env python3
"""
Aviation Corpus Non-LLM Distillation Engine
============================================
Fast algorithmic extraction that distills 330,000 raw chunks down to the 
highest-value "Golden Dataset" of authoritative aviation regulatory, 
operational, and investigation findings.

Execution time: ~30-45 seconds across all 6,792 documents.
No LLM tokens required.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("distill_corpus")

# High-salience normative, operational, and regulatory terms
REGULATORY_DIRECTIVES = [
    r"\bshall\b", r"\bmust\b", r"\brequired\b", r"\brequirement[s]?\b",
    r"\bprohibited\b", r"\bmandatory\b", r"\bstipulate[ds]?\b",
    r"\bcompl(?:y|iance|ies)\b", r"\baccordance\b", r"\bstandard[s]?\b",
    r"\bprocedure[s]?\b", r"\bregulation[s]?\b", r"\bdirective[s]?\b",
    r"\bprovisions?\b", r"\bexempt(?:ion)?\b", r"\bapproved?\b",
    r"\bauthorized?\b", r"\bcertifi(?:ed|cate|cation)\b", r"\boperating limits?\b"
]

OPERATIONAL_SAFETY_TERMS = [
    r"\bcontingency\b", r"\bemergency\b", r"\babnormal\b", r"\bgo-around\b",
    r"\bapproach\b", r"\bseparation\b", r"\bclearance\b", r"\baltitude\b",
    r"\bairspace\b", r"\bairworthiness\b", r"\bincident\b", r"\baccident\b",
    r"\binvestigation\b", r"\brecommendation[s]?\b", r"\bcausal factor[s]?\b",
    r"\bfailure[s]?\b", r"\bhazard[s]?\b", r"\brisk mitigation\b",
    r"\bsafety management\b", r"\bflight crew\b", r"\bair traffic\b",
    r"\bstandard operating procedure[s]?\b", r"\bcrm\b", r"\bcrew resource\b",
    r"\bterrain\b", r"\bminimums?\b", r"\bdecision altitude\b", r"\bflight data\b"
]

AUTHORITY_TERMS = [
    r"\bicao\b", r"\beasa\b", r"\bfaa\b", r"\baib\b", r"\baaib\b",
    r"\bntsb\b", r"\batsb\b", r"\beurocontrol\b", r"\bannex \d+\b",
    r"\bpart \d+\b", r"\bcs-\d+\b", r"\bdoc \d+\b"
]

RE_DIRECTIVES = re.compile("|".join(REGULATORY_DIRECTIVES), re.IGNORECASE)
RE_OPERATIONAL = re.compile("|".join(OPERATIONAL_SAFETY_TERMS), re.IGNORECASE)
RE_AUTHORITY = re.compile("|".join(AUTHORITY_TERMS), re.IGNORECASE)

# Patterns that indicate boilerplate, indexes, or footnotes
RE_FOOTNOTE_START = re.compile(r"^\s*(\d{1,3}\s+[A-Z]|See\s+\d+|Ibid\b|Footnote\b|Figure\s+\d+|Table\s+\d+)", re.IGNORECASE)
RE_TOC_LINE = re.compile(r"(\.{4,}\s*\d+|\bpage\s+\d+\b|\bchapter\s+\d+\b)", re.IGNORECASE)
RE_SIGNATURE_BLOCK = re.compile(r"(respectfully submitted|issued at|signed this|for the board:)", re.IGNORECASE)


@dataclass
class GoldenChunk:
    chunk_id: str
    document_id: str
    title: str
    category: str
    author: str
    section_path: str
    file_path: str
    page_start: int
    word_count: int
    char_count: int
    salience_score: float
    directive_count: int
    operational_count: int
    authority_count: int
    text: str


def score_chunk_salience(text: str, metadata: Dict[str, Any]) -> Tuple[float, int, int, int]:
    """
    Computes an authoritative salience score without using an LLM.
    Returns (total_score, directive_hits, operational_hits, authority_hits).
    """
    s = text.strip()
    words = s.split()
    w_len = len(words)

    # 1. Length constraints: ideal operational chunk is 100 to 650 words
    if w_len < 75 or w_len > 700:
        return 0.0, 0, 0, 0

    # 2. Footnotes, figure captions, or tables of contents
    if RE_FOOTNOTE_START.match(s):
        return 0.0, 0, 0, 0

    if s.count(".") > 18 and RE_TOC_LINE.search(s):
        return 0.0, 0, 0, 0

    if RE_SIGNATURE_BLOCK.search(s) and w_len < 120:
        return 0.0, 0, 0, 0

    # 3. Alphabetical ratio (reject pure data logs, ascii art, numbers)
    alpha_chars = sum(c.isalpha() for c in s)
    if alpha_chars / max(1, len(s)) < 0.65:
        return 0.0, 0, 0, 0

    # 4. Standard disclaimers
    lower = s.lower()
    if "all rights reserved" in lower and w_len < 150:
        return 0.0, 0, 0, 0
    if "published by eurocontrol for information purposes" in lower and w_len < 150:
        return 0.0, 0, 0, 0

    # 5. Salience keyword matching
    directive_hits = len(RE_DIRECTIVES.findall(s))
    operational_hits = len(RE_OPERATIONAL.findall(s))
    authority_hits = len(RE_AUTHORITY.findall(s))

    # Weighting:
    # Directives (mandates, prohibitions) = 3.0 pts
    # Operational safety mechanisms = 2.0 pts
    # Authorities & standards citations = 2.5 pts
    raw_score = (directive_hits * 3.0) + (operational_hits * 2.0) + (authority_hits * 2.5)

    # Penalize if it has zero directives or operational context
    if directive_hits == 0 and operational_hits == 0:
        return 0.0, 0, 0, 0

    # Normalization bonus for optimal length (200 - 450 words)
    length_bonus = 1.2 if (180 <= w_len <= 450) else 1.0
    final_score = raw_score * length_bonus

    return final_score, directive_hits, operational_hits, authority_hits


def distill_corpus(
    chunks_dir: Path,
    out_file: Path,
    max_chunks_per_doc: int = 4,
    min_score_threshold: float = 6.0
) -> Dict[str, Any]:
    """Distills the entire chunks directory into a golden JSONL corpus."""
    logger.info(f"Scanning chunk files from: {chunks_dir}")
    chunk_files = list(chunks_dir.rglob("*.chunks.json"))
    logger.info(f"Found {len(chunk_files)} chunk files across all directories.")

    start_t = time.time()
    total_raw_chunks = 0
    golden_chunks: List[GoldenChunk] = []
    category_counts: Dict[str, int] = defaultdict(int)

    for idx, cf in enumerate(chunk_files, 1):
        if idx % 1000 == 0:
            logger.info(f"Analyzed {idx}/{len(chunk_files)} documents | Kept {len(golden_chunks)} golden chunks so far...")

        try:
            with open(cf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        doc_meta = data.get("document", {})
        doc_id = doc_meta.get("document_id") or cf.stem
        title = doc_meta.get("title") or ""
        category = doc_meta.get("category") or cf.parent.name
        author = doc_meta.get("author") or ""

        candidates: List[Tuple[float, int, int, int, Dict[str, Any]]] = []

        for ch in data.get("chunks", []):
            total_raw_chunks += 1
            src_text = ch.get("source_text") or ch.get("embedding_text") or ""
            score, d_hits, o_hits, a_hits = score_chunk_salience(src_text, ch.get("metadata", {}))

            if score >= min_score_threshold:
                candidates.append((score, d_hits, o_hits, a_hits, ch))

        # Sort candidate chunks in this document by score descending
        candidates.sort(key=lambda x: x[0], reverse=True)

        # Select the top N highest-scoring chunks from this document
        for score, d_hits, o_hits, a_hits, ch in candidates[:max_chunks_per_doc]:
            src_text = ch.get("source_text") or ch.get("embedding_text") or ""
            sec_path = " > ".join(str(p) for p in (ch.get("section_path") or []))
            ch_meta = ch.get("metadata", {})

            g_chunk = GoldenChunk(
                chunk_id=ch.get("chunk_id", ""),
                document_id=doc_id,
                title=title,
                category=category,
                author=author,
                section_path=sec_path,
                file_path=str(cf),
                page_start=ch_meta.get("page_start", 1),
                word_count=len(src_text.split()),
                char_count=len(src_text),
                salience_score=round(score, 2),
                directive_count=d_hits,
                operational_count=o_hits,
                authority_count=a_hits,
                text=src_text.strip()
            )
            golden_chunks.append(g_chunk)
            category_counts[category] += 1

    elapsed = time.time() - start_t
    logger.info(f"Distillation complete in {elapsed:.2f} seconds.")
    logger.info(f"Total raw chunks inspected: {total_raw_chunks}")
    logger.info(f"Golden chunks extracted:   {len(golden_chunks)} ({len(golden_chunks)/max(1, total_raw_chunks)*100:.1f}%)")
    logger.info(f"Distinct categories:       {len(category_counts)}")

    # Write out golden dataset
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f_out:
        for gc in golden_chunks:
            f_out.write(json.dumps(asdict(gc), ensure_ascii=False) + "\n")

    logger.info(f"Saved golden dataset to: {out_file.resolve()}")

    # Summary report
    summary = {
        "total_documents": len(chunk_files),
        "total_raw_chunks": total_raw_chunks,
        "golden_chunks_extracted": len(golden_chunks),
        "categories_count": len(category_counts),
        "category_distribution": dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)),
        "generation_time_seconds": round(elapsed, 2)
    }

    summary_file = out_file.parent / "golden_corpus_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f_sum:
        json.dump(summary, f_sum, indent=2)

    logger.info(f"Saved summary to: {summary_file.resolve()}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Distill 330k chunks into golden aviation dataset.")
    parser.add_argument("--chunks-dir", type=Path, default=Path("chunks"), help="Path to chunks directory")
    parser.add_argument("--out-file", type=Path, default=Path("golden_chunks.jsonl"), help="Output golden jsonl")
    parser.add_argument("--max-per-doc", type=int, default=4, help="Max top-scoring chunks per document (default: 4)")
    parser.add_argument("--min-score", type=float, default=6.0, help="Minimum salience threshold (default: 6.0)")
    args = parser.parse_args()

    distill_corpus(
        chunks_dir=args.chunks_dir,
        out_file=args.out_file,
        max_chunks_per_doc=args.max_per_doc,
        min_score_threshold=args.min_score
    )


if __name__ == "__main__":
    main()
