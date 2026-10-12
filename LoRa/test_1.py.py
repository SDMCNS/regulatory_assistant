from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


MODAL_PATTERNS = [
    (r"\bshall not\b", "mandatory_prohibition"),
    (r"\bmust not\b", "mandatory_prohibition"),
    (r"\bmay not\b", "prohibition"),
    (r"\bshall\b", "mandatory"),
    (r"\bmust\b", "mandatory"),
    (r"\bis required to\b", "mandatory"),
    (r"\bare required to\b", "mandatory"),
    (r"\bmay\b", "permissive"),
    (r"\bcan\b", "capability_or_permission"),
    (r"\bshould\b", "recommendation"),
]

RESPONSIBLE_PARTY_PATTERNS = [
    r"\bthe aircraft operator\b",
    r"\bthe operator\b",
    r"\bthe air operator\b",
    r"\bthe competent authority\b",
    r"\bthe aerodrome operator\b",
    r"\bthe air navigation service provider\b",
    r"\bthe service provider\b",
    r"\bthe applicant\b",
    r"\bthe organisation\b",
    r"\bthe organisation concerned\b",
    r"\bthe Member States?\b",
    r"\bEASA\b",
    r"\bthe Agency\b",
]


def log(message: str) -> None:
    """Print a timestamped progress message."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def elapsed(start_time: float) -> str:
    """Return elapsed time as a human-readable string."""
    seconds = time.perf_counter() - start_time

    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    remaining = seconds % 60

    if minutes < 60:
        return f"{minutes}m {remaining:.1f}s"

    hours = int(minutes // 60)
    minutes = minutes % 60
    return f"{hours}h {minutes}m {remaining:.1f}s"


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalise_path(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(x) for x in value if clean_text(x)]
    return []


def stable_id(*parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def split_documents(
    document_ids: list[str],
    seed: int,
    train_ratio: float,
    validation_ratio: float,
) -> dict[str, str]:

    ids = sorted(set(document_ids))

    log(f"Creating document-level train/validation/test split...")
    log(f"  Unique eligible documents: {len(ids)}")
    log(f"  Random seed: {seed}")
    log(f"  Train ratio: {train_ratio:.2%}")
    log(f"  Validation ratio: {validation_ratio:.2%}")
    log(f"  Test ratio: {1 - train_ratio - validation_ratio:.2%}")

    rng = random.Random(seed)
    rng.shuffle(ids)

    n = len(ids)
    n_train = round(n * train_ratio)
    n_val = round(n * validation_ratio)

    # Guarantee all three sets exist when there are enough documents.
    n_train = min(max(n_train, 1), n - 2)
    n_val = min(max(n_val, 1), n - n_train - 1)

    result: dict[str, str] = {}

    for doc_id in ids[:n_train]:
        result[doc_id] = "train"

    for doc_id in ids[n_train:n_train + n_val]:
        result[doc_id] = "validation"

    for doc_id in ids[n_train + n_val:]:
        result[doc_id] = "test"

    log(
        f"Document split complete: "
        f"train={n_train}, validation={n_val}, "
        f"test={n - n_train - n_val}"
    )

    return result


def extract_modal_sentences(text: str) -> list[dict[str, str]]:
    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9(])",
        text.strip()
    )

    found = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        lowered = sentence.lower()

        for pattern, modality in MODAL_PATTERNS:
            match = re.search(pattern, lowered)

            if match:
                found.append({
                    "text": sentence,
                    "modality": modality,
                    "trigger": match.group(0),
                })
                break

    return found


def extract_responsible_party(text: str) -> str | None:
    for pattern in RESPONSIBLE_PARTY_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(0)

    return None


def base_message(
    system: str,
    user: str,
    assistant: str,
    task: str,
    chunk_id: str,
    document_id: str,
) -> dict[str, Any]:

    return {
        "id": stable_id(task, chunk_id),
        "task": task,
        "chunk_id": chunk_id,
        "document_id": document_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
    }


SYSTEM = (
    "You are a regulatory analysis assistant. "
    "Answer using only the regulatory information supplied in the prompt. "
    "Do not invent legal requirements, authorities, relationships, or facts."
)


def make_examples(
    row: sqlite3.Row,
    doc: sqlite3.Row,
) -> Iterable[dict[str, Any]]:

    chunk_id = clean_text(row["chunk_id"])
    document_id = clean_text(row["document_id"])
    source_text = clean_text(row["source_text"])

    if not chunk_id or not document_id or not source_text:
        return

    section_path = normalise_path(
        json_load(row["section_path"], [])
    )

    section_numbers = normalise_path(
        json_load(row["section_numbers"], [])
    )

    structure = json_load(
        row["structure_json"],
        {}
    )

    references = json_load(
        row["references_json"],
        []
    )

    metadata = json_load(
        row["metadata_json"],
        {}
    )

    doc_metadata = json_load(
        doc["metadata_json"],
        {}
    )

    title = clean_text(doc["title"])
    language = clean_text(doc["language"])
    date = clean_text(doc["date"])
    chunk_type = clean_text(row["chunk_type"])

    # 1. Document identification
    yield base_message(
        SYSTEM,
        f"Which regulatory document contains this provision?\n\n"
        f"Provision:\n{source_text}",
        json.dumps({
            "document_id": document_id,
            "title": title,
            "language": language,
            "date": date,
        }, ensure_ascii=False),
        "document_identification",
        chunk_id,
        document_id,
    )

    # 2. Structural location
    yield base_message(
        SYSTEM,
        f"Where does this provision occur within its document?\n\n"
        f"Provision:\n{source_text}",
        json.dumps({
            "section_path": section_path,
            "section_numbers": section_numbers,
            "chunk_type": chunk_type,
        }, ensure_ascii=False),
        "structural_location",
        chunk_id,
        document_id,
    )

    # 3. Regulatory text classification
    yield base_message(
        SYSTEM,
        f"Classify the type of regulatory node represented by this text.\n\n"
        f"Text:\n{source_text}",
        json.dumps({
            "chunk_type": chunk_type,
            "node_type": (
                structure.get("node_type")
                if isinstance(structure, dict)
                else None
            ),
        }, ensure_ascii=False),
        "chunk_classification",
        chunk_id,
        document_id,
    )

    # 4. Cross-reference extraction
    if references:
        yield base_message(
            SYSTEM,
            f"Extract the explicit regulatory references recorded "
            f"for this provision. "
            f"Return them without adding any references not present "
            f"in the supplied data.\n\n"
            f"Provision:\n{source_text}",
            json.dumps(references, ensure_ascii=False),
            "reference_extraction",
            chunk_id,
            document_id,
        )

    # 5. Regulatory obligation/modal examples
    modal_sentences = extract_modal_sentences(source_text)

    for idx, item in enumerate(modal_sentences[:3]):
        party = extract_responsible_party(item["text"])

        target = {
            "text": item["text"],
            "modality": item["modality"],
            "trigger": item["trigger"],
        }

        if party:
            target["candidate_responsible_party"] = party

        yield base_message(
            SYSTEM,
            "Identify the explicit modal/obligation statement "
            "in this provision. "
            "Do not infer obligations beyond the supplied sentence.\n\n"
            f"Provision:\n{source_text}",
            json.dumps(target, ensure_ascii=False),
            f"modal_extraction_{idx}",
            chunk_id,
            document_id,
        )

    # 6. Document-level regulatory metadata
    relationship_fields = {}

    for key in (
        "status",
        "doc_number",
        "amends_regs",
        "repeals_regs",
        "eea_relevance",
        "annex_count",
    ):
        if key in doc_metadata:
            relationship_fields[key] = doc_metadata[key]

    if relationship_fields:
        yield base_message(
            SYSTEM,
            f"What document-level regulatory metadata is available "
            f"for the document containing this provision?\n\n"
            f"Provision:\n{source_text}",
            json.dumps(
                relationship_fields,
                ensure_ascii=False
            ),
            "document_metadata",
            chunk_id,
            document_id,
        )

    # 7. Context reconstruction
    if section_path:
        context = " > ".join(section_path)

        yield base_message(
            SYSTEM,
            f"Place the following provision in its structural context.\n\n"
            f"Provision:\n{source_text}",
            f"{title}\n"
            f"Section: {context}\n"
            f"Provision: {source_text}",
            "context_reconstruction",
            chunk_id,
            document_id,
        )


def main() -> None:

    start_time = time.perf_counter()

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        required=True,
        help="Path to SQLite database"
    )

    parser.add_argument(
        "--out",
        required=True,
        help="Output directory"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42
    )

    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.80
    )

    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.10
    )

    parser.add_argument(
        "--min-source-chars",
        type=int,
        default=30
    )

    parser.add_argument(
        "--max-source-chars",
        type=int,
        default=12000
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # START
    # ------------------------------------------------------------------

    log("=" * 70)
    log("REGULATORY TRAINING DATASET BUILDER")
    log("=" * 70)

    log("Configuration:")
    log(f"  Database: {args.db}")
    log(f"  Output:   {args.out}")
    log(f"  Seed:     {args.seed}")
    log(f"  Minimum source characters: {args.min_source_chars}")
    log(f"  Maximum source characters: {args.max_source_chars}")
    log("")

    # ------------------------------------------------------------------
    # OUTPUT DIRECTORY
    # ------------------------------------------------------------------

    log("STEP 1/8 - Preparing output directory")

    out_dir = Path(args.out)
    out_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    log(f"  Output directory ready: {out_dir.resolve()}")
    log("")

    # ------------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------------

    log("STEP 2/8 - Opening SQLite database")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    log("  Database connection established")

    # ------------------------------------------------------------------
    # TABLE VALIDATION
    # ------------------------------------------------------------------

    log("STEP 3/8 - Validating database structure")

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    log(f"  Tables found: {', '.join(sorted(tables))}")

    required = {
        "chunks",
        "documents",
    }

    missing = required - tables

    if missing:
        log(
            f"ERROR: Missing required tables: "
            f"{sorted(missing)}"
        )
        raise RuntimeError(
            f"Missing required tables: {sorted(missing)}"
        )

    log("  Required tables present")
    log("")

    # ------------------------------------------------------------------
    # LOAD DOCUMENTS
    # ------------------------------------------------------------------

    log("STEP 4/8 - Loading documents")

    documents = {
        row["document_id"]: row
        for row in conn.execute(
            "SELECT * FROM documents"
        )
    }

    log(
        f"  Documents loaded: {len(documents):,}"
    )

    # ------------------------------------------------------------------
    # LOAD ELIGIBLE CHUNKS
    # ------------------------------------------------------------------

    log("STEP 5/8 - Scanning chunks")

    log(
        f"  Filtering source length: "
        f"{args.min_source_chars:,} - "
        f"{args.max_source_chars:,} characters"
    )

    chunk_rows = []
    eligible_docs = []

    query = """
        SELECT *
        FROM chunks
        WHERE source_text IS NOT NULL
          AND length(trim(source_text)) >= ?
          AND length(source_text) <= ?
        ORDER BY document_id, chunk_id
    """

    scanned = 0

    for row in conn.execute(
        query,
        (
            args.min_source_chars,
            args.max_source_chars,
        ),
    ):

        scanned += 1

        doc_id = clean_text(
            row["document_id"]
        )

        if doc_id not in documents:
            continue

        chunk_rows.append(row)
        eligible_docs.append(doc_id)

        if scanned % 10000 == 0:
            log(
                f"  Scanned {scanned:,} eligible database rows..."
            )

    log(
        f"  Chunk scan complete: "
        f"{len(chunk_rows):,} eligible chunks"
    )

    log(
        f"  Unique eligible documents: "
        f"{len(set(eligible_docs)):,}"
    )

    log("")

    # ------------------------------------------------------------------
    # SPLIT
    # ------------------------------------------------------------------

    log("STEP 6/8 - Creating train/validation/test split")

    assignments = split_documents(
        eligible_docs,
        args.seed,
        args.train_ratio,
        args.validation_ratio,
    )

    split_doc_counts = Counter(
        assignments.values()
    )

    log(
        f"  Train documents:      "
        f"{split_doc_counts['train']:,}"
    )

    log(
        f"  Validation documents: "
        f"{split_doc_counts['validation']:,}"
    )

    log(
        f"  Test documents:       "
        f"{split_doc_counts['test']:,}"
    )

    log("")

    # ------------------------------------------------------------------
    # OPEN OUTPUT FILES
    # ------------------------------------------------------------------

    log("STEP 7/8 - Opening output files")

    handles = {}

    for split in (
        "train",
        "validation",
        "test",
    ):

        path = out_dir / f"{split}.jsonl"

        log(
            f"  Opening {split}: {path}"
        )

        handles[split] = path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        )

    log("  Output files ready")
    log("")

    # ------------------------------------------------------------------
    # PROCESS CHUNKS
    # ------------------------------------------------------------------

    log("STEP 8/8 - Generating training examples")
    log(
        f"  Processing {len(chunk_rows):,} chunks..."
    )
    log("")

    counts = Counter()
    task_counts = Counter()
    chunk_counts = Counter()
    skipped = Counter()

    processed = 0
    total_examples = 0

    try:

        seen_example_ids: set[str] = set()

        total_chunks = len(chunk_rows)

        for row in chunk_rows:

            processed += 1

            chunk_id = clean_text(
                row["chunk_id"]
            )

            doc_id = clean_text(
                row["document_id"]
            )

            split = assignments[doc_id]

            examples = make_examples(
                row,
                documents[doc_id],
            )

            made = 0

            for example in examples:

                if len(
                    example["messages"][-1]["content"]
                ) == 0:

                    skipped[
                        "empty_target"
                    ] += 1

                    continue

                if example["id"] in seen_example_ids:

                    skipped[
                        "duplicate_example_id"
                    ] += 1

                    continue

                seen_example_ids.add(
                    example["id"]
                )

                handles[split].write(
                    json.dumps(
                        example,
                        ensure_ascii=False
                    ) + "\n"
                )

                counts[split] += 1

                task_counts[
                    example["task"]
                ] += 1

                made += 1
                total_examples += 1

            if made:
                chunk_counts[split] += 1

            # ----------------------------------------------------------
            # PROGRESS OUTPUT
            # ----------------------------------------------------------

            if processed % 500 == 0 or processed == total_chunks:

                percentage = (
                    processed / total_chunks * 100
                    if total_chunks
                    else 100
                )

                log(
                    f"  Progress: "
                    f"{processed:,}/{total_chunks:,} "
                    f"({percentage:6.2f}%) | "
                    f"examples={total_examples:,} | "
                    f"train={counts['train']:,} | "
                    f"val={counts['validation']:,} | "
                    f"test={counts['test']:,}"
                )

    finally:

        log("")
        log("Closing output files...")

        for handle in handles.values():
            handle.close()

        log("Output files closed")

        log("Closing database connection...")

        conn.close()

        log("Database connection closed")

    # ------------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------------

    log("")
    log("Generating dataset report...")

    report = {
        "database": str(
            Path(args.db).resolve()
        ),
        "seed": args.seed,
        "ratios": {
            "train": args.train_ratio,
            "validation": args.validation_ratio,
            "test": round(
                1
                - args.train_ratio
                - args.validation_ratio,
                6,
            ),
        },
        "source": {
            "documents_total": len(documents),
            "chunks_eligible": len(chunk_rows),
            "min_source_chars": args.min_source_chars,
            "max_source_chars": args.max_source_chars,
        },
        "splits": {
            split: {
                "documents": split_doc_counts[split],
                "chunks_with_examples": chunk_counts[split],
                "examples": counts[split],
            }
            for split in (
                "train",
                "validation",
                "test",
            )
        },
        "examples_by_task": dict(task_counts),
        "skipped": dict(skipped),
    }

    report_path = (
        out_dir / "dataset_report.json"
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log(
        f"Dataset report written to: "
        f"{report_path}"
    )

    # ------------------------------------------------------------------
    # FINAL SUMMARY
    # ------------------------------------------------------------------

    log("")
    log("=" * 70)
    log("DATASET BUILD COMPLETE")
    log("=" * 70)

    log(
        f"Documents:       {len(documents):,}"
    )

    log(
        f"Eligible chunks: {len(chunk_rows):,}"
    )

    log(
        f"Examples:        {total_examples:,}"
    )

    log("")

    log("Examples by split:")

    for split in (
        "train",
        "validation",
        "test",
    ):

        log(
            f"  {split:<12} "
            f"{counts[split]:,}"
        )

    log("")

    log("Examples by task:")

    for task, count in sorted(
        task_counts.items()
    ):

        log(
            f"  {task:<30} "
            f"{count:,}"
        )

    if skipped:

        log("")

        log("Skipped:")

        for reason, count in sorted(
            skipped.items()
        ):

            log(
                f"  {reason:<30} "
                f"{count:,}"
            )

    log("")
    log(
        f"Elapsed time: {elapsed(start_time)}"
    )

    log(
        f"Output directory: "
        f"{out_dir.resolve()}"
    )

    log("=" * 70)

    # Keep the original JSON report on stdout as well.
    print("")
    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("")
        log("INTERRUPTED BY USER")
        raise

    except Exception as exc:
        print("")
        log("ERROR: Dataset build failed")
        log(f"  {type(exc).__name__}: {exc}")
        raise
