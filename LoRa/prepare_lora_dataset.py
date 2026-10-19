#!/usr/bin/env python3
"""
LoRA Dataset Preparation & Splitter Tool
=======================================
Processes synthetic Q&A JSONL files, performs data cleaning, deduplication,
splits data into Train / Validation / Test sets (with document-level isolation
to prevent evaluation leakage), and produces summary statistics.

Compatible with:
- Hugging Face datasets / trl SFTTrainer
- train_lora.py.py and training.py.py
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("DatasetPrep")

def load_and_deduplicate(input_files: List[Path], min_answer_words: int = 4) -> List[Dict[str, Any]]:
    """Loads records from JSONL files, removing invalid or duplicate questions."""
    seen_questions: Set[str] = set()
    cleaned_records: List[Dict[str, Any]] = []

    for path in input_files:
        if not path.exists():
            logger.warning(f"File not found: {path}")
            continue

        logger.info(f"Loading {path.name}...")
        with open(path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    messages = record.get("messages", [])
                    if len(messages) < 2:
                        continue

                    # Extract user question and assistant answer
                    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                    asst_msg = next((m["content"] for m in messages if m["role"] == "assistant"), "")

                    if not user_msg or not asst_msg:
                        continue

                    # Clean checks
                    q_key = user_msg.strip().lower()
                    if q_key in seen_questions:
                        continue

                    if len(asst_msg.split()) < min_answer_words:
                        continue

                    # Filter out any lingering ephemeral contact details
                    full_text = f"{user_msg} {asst_msg}".lower()
                    if any(re.search(pat, full_text) for pat in [
                        r"\bcontact\s+(person|point|officer|details|number|information|email)\b",
                        r"\bpoint\s+of\s+contact\b",
                        r"\binquiries\s+(can|should|may)\s+be\s+directed\b",
                        r"\bcall\s+(or\s+email\s+)?(\+?\d[\d\s-]{6,}|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)",
                        r"\bfocal\s+point\b",
                        r"\bwhom\s+should\s+(a\s+)?(pilot|operator|member|user)\s+(contact|direct)\b"
                    ]):
                        logger.info(f"Dropping ephemeral contact item: '{user_msg[:60]}...'")
                        continue

                    seen_questions.add(q_key)
                    cleaned_records.append(record)

                except json.JSONDecodeError:
                    logger.debug(f"Skipping malformed line {line_idx} in {path.name}")

    logger.info(f"Loaded {len(cleaned_records)} valid, unique records.")
    return cleaned_records


def split_by_document(
    records: List[Dict[str, Any]],
    train_ratio: float = 0.85,
    val_ratio: float = 0.10,
    test_ratio: float = 0.05,
    seed: int = 42
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Splits records into train, val, and test partitions by Document ID.
    Document-level partitioning guarantees that evaluation sets test generalization
    on unseen regulatory documents, preventing data leakage.
    """
    random.seed(seed)

    # Group by document_id
    doc_to_records = defaultdict(list)
    for rec in records:
        doc_id = rec.get("document_id") or "UNKNOWN_DOC"
        doc_to_records[doc_id].append(rec)

    all_docs = list(doc_to_records.keys())
    random.shuffle(all_docs)

    n_docs = len(all_docs)
    n_train = max(1, int(n_docs * train_ratio))
    n_val = max(1, int(n_docs * val_ratio)) if val_ratio > 0 else 0

    train_docs = set(all_docs[:n_train])
    val_docs = set(all_docs[n_train:n_train + n_val])
    test_docs = set(all_docs[n_train + n_val:])

    # If test set is empty due to small doc count, rebalance
    if not test_docs and len(val_docs) > 1:
        test_docs.add(val_docs.pop())

    splits: Dict[str, List[Dict[str, Any]]] = {
        "train": [],
        "validation": [],
        "test": []
    }

    for doc_id, recs in doc_to_records.items():
        if doc_id in train_docs:
            splits["train"].extend(recs)
        elif doc_id in val_docs:
            splits["validation"].extend(recs)
        else:
            splits["test"].extend(recs)

    # Shuffle each split
    for split_name in splits:
        random.shuffle(splits[split_name])

    return splits


def write_jsonl(records: List[Dict[str, Any]], output_path: Path):
    """Writes records to a JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info(f"Wrote {len(records)} records to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="LoRA Dataset Preparation & Document-Isolated Splitter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--inputs", nargs="+", default=["aviation_qa_lora.jsonl"],
                        help="Input JSONL file(s) to process")
    parser.add_argument("--out-dir", type=str, default="dataset_splits",
                        help="Output directory for train/val/test splits")
    parser.add_argument("--train-ratio", type=float, default=0.85, help="Train ratio")
    parser.add_argument("--val-ratio", type=float, default=0.10, help="Validation ratio")
    parser.add_argument("--test-ratio", type=float, default=0.05, help="Test ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting")
    parser.add_argument("--report", type=str, default="qa_dataset_summary.json",
                        help="Path to output statistics JSON report")

    args = parser.parse_args()

    input_paths = [Path(p) for p in args.inputs]
    records = load_and_deduplicate(input_paths)

    if not records:
        logger.error("No valid records found to split.")
        return

    splits = split_by_document(
        records,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed
    )

    out_dir = Path(args.out_dir)
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "validation.jsonl"
    test_path = out_dir / "test.jsonl"

    write_jsonl(splits["train"], train_path)
    write_jsonl(splits["validation"], val_path)
    write_jsonl(splits["test"], test_path)

    # Calculate statistics
    categories = Counter(r.get("category", "General") for r in records)
    total_words_a = sum(len(next((m["content"] for m in r.get("messages", []) if m["role"] == "assistant"), "").split()) for r in records)
    avg_words_a = round(total_words_a / max(1, len(records)), 1)

    summary = {
        "total_records": len(records),
        "split_counts": {
            "train": len(splits["train"]),
            "validation": len(splits["validation"]),
            "test": len(splits["test"])
        },
        "unique_documents": len(set(r.get("document_id", "") for r in records)),
        "categories_distribution": dict(categories.most_common(15)),
        "average_answer_words": avg_words_a,
        "files_generated": {
            "train": str(train_path),
            "validation": str(val_path),
            "test": str(test_path)
        }
    }

    report_path = Path(args.report)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 60)
    logger.info(f"Dataset split complete! Train: {len(splits['train'])} | Val: {len(splits['validation'])} | Test: {len(splits['test'])}")
    logger.info(f"Summary report saved to: {report_path}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
