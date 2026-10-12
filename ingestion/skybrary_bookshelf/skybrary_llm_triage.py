from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import requests


DEFAULT_DB = r"C:\Projects\Regs\ingestion\skybrary_bookshelf\skybrary.db"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "local-model"

SYSTEM_PROMPT = """You are a document triage specialist for an aviation regulatory and safety knowledge base.

Assess a SKYbrary publication using ONLY its metadata: title, category/type, author and publication date.

We are building a long-lived knowledge base focused on:
- European aviation and European aviation regulation
- global aviation where it is broadly applicable
- aviation safety
- ATM/CNS
- operational procedures
- regulatory/compliance material
- accident/incident prevention and lessons learned
- standards, guidance and technical material
- historical snapshots of aviation practice and regulation

A document does NOT need to be current to be valuable. Older material can be highly valuable as a historical snapshot, especially where it captures regulation, standards, technology, safety thinking or operational practice at a particular point in time.

Return ONLY valid JSON with these integer scores from 0 to 10:

european_aviation:
  Relevance specifically to European aviation.

global_aviation:
  Relevance to aviation internationally.

regulatory:
  Relevance to regulations, legislation, standards, compliance, policy or formal guidance.

safety:
  Relevance to aviation safety, risk management, accident/incident prevention or safety management.

atm_cns:
  Relevance to air traffic management, communications, navigation, surveillance, SWIM, CNS, etc.

operational:
  Relevance to actual aviation/ATM operational practice.

historical_snapshot:
  Likelihood that the document remains useful as a historical snapshot even if outdated or superseded.

knowledge_value:
  General long-term value to a serious aviation knowledge base.

priority:
  Overall download priority, 0 to 100.

classification:
  One of: "high", "medium", "low", "irrelevant".

reason:
  One concise sentence explaining the judgement.

Be conservative. Do not infer specific subject matter that is not reasonably indicated by the metadata.
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(publications)").fetchall()
    }

    columns = {
        "llm_score": "REAL",
        "llm_priority": "INTEGER",
        "llm_classification": "TEXT",
        "llm_reason": "TEXT",
        "llm_scores_json": "TEXT",
        "llm_model": "TEXT",
        "llm_scored_at": "TEXT",
        "llm_attempts": "INTEGER NOT NULL DEFAULT 0",
        "llm_error": "TEXT",
    }

    for name, definition in columns.items():
        if name not in existing:
            conn.execute(
                f"ALTER TABLE publications ADD COLUMN {name} {definition}"
            )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publications_llm_priority "
        "ON publications(llm_priority)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publications_llm_classification "
        "ON publications(llm_classification)"
    )
    conn.commit()


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_columns(conn)
    return conn


def build_prompt(row: sqlite3.Row) -> str:
    return f"""Assess this SKYbrary publication.

TITLE:
{row["title"] or ""}

TYPE / CATEGORY:
{row["category"] or ""}

AUTHOR:
{row["author"] or ""}

PUBLICATION DATE:
{row["publication_date"] or ""}

Return JSON only."""


def extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from clean, markdown-wrapped, or reasoning-model output."""
    if not isinstance(text, str):
        raise ValueError(f"Unexpected model content type: {type(text).__name__}")

    text = text.strip()

    # Fast path.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Remove markdown fences and retry.
    cleaned = (
        text.replace("```json", "")
        .replace("```JSON", "")
        .replace("```", "")
        .strip()
    )

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Find balanced JSON objects. This copes with reasoning/preamble
    # containing braces and avoids simply taking the last closing brace.
    for start, ch in enumerate(cleaned):
        if ch != "{":
            continue

        depth = 0
        in_string = False
        escaped = False

        for i in range(start, len(cleaned)):
            ch = cleaned[i]

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1

                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break

    preview = text[:1500].replace("\n", "\\n")
    raise ValueError(
        "Model did not return valid JSON. "
        f"Raw response starts: {preview}"
    )


def clamp_int(value: Any, minimum: int = 0, maximum: int = 10) -> int:
    try:
        return max(minimum, min(maximum, int(round(float(value)))))
    except (TypeError, ValueError):
        return minimum


def normalise_result(result: dict[str, Any]) -> dict[str, Any]:
    dimensions = [
        "european_aviation",
        "global_aviation",
        "regulatory",
        "safety",
        "atm_cns",
        "operational",
        "historical_snapshot",
        "knowledge_value",
    ]

    scores = {
        key: clamp_int(result.get(key))
        for key in dimensions
    }

    # Weighted priority.
    #
    # European aviation and regulation/safety are deliberately strongest,
    # while historical value prevents older documents being discarded simply
    # because they are no longer current.
    weighted = (
        scores["european_aviation"] * 0.20
        + scores["global_aviation"] * 0.08
        + scores["regulatory"] * 0.18
        + scores["safety"] * 0.18
        + scores["atm_cns"] * 0.12
        + scores["operational"] * 0.08
        + scores["historical_snapshot"] * 0.08
        + scores["knowledge_value"] * 0.08
    )

    priority = max(0, min(100, round(weighted * 10)))

    # Let the model classification inform the label, but derive priority
    # independently so the ranking remains consistent.
    if priority >= 75:
        classification = "high"
    elif priority >= 50:
        classification = "medium"
    elif priority >= 25:
        classification = "low"
    else:
        classification = "irrelevant"

    return {
        "scores": scores,
        "priority": priority,
        "classification": classification,
        "reason": str(result.get("reason", "")).strip()[:1000],
    }


def call_llm(
    session: requests.Session,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    response = session.post(
        base_url.rstrip("/") + "/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=180,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return extract_json(content)


def score_row(
    conn: sqlite3.Connection,
    session: requests.Session,
    row: sqlite3.Row,
    args: argparse.Namespace,
) -> bool:
    now = utc_now()

    conn.execute(
        "UPDATE publications SET llm_attempts = COALESCE(llm_attempts, 0) + 1, "
        "llm_error = NULL WHERE id = ?",
        (row["id"],),
    )
    conn.commit()

    try:
        raw = call_llm(
            session,
            args.base_url,
            args.model,
            build_prompt(row),
            args.temperature,
            args.max_tokens,
        )
        result = normalise_result(raw)

        conn.execute(
            """
            UPDATE publications
            SET llm_score = ?,
                llm_priority = ?,
                llm_classification = ?,
                llm_reason = ?,
                llm_scores_json = ?,
                llm_model = ?,
                llm_scored_at = ?,
                llm_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                result["priority"] / 10.0,
                result["priority"],
                result["classification"],
                result["reason"],
                json.dumps(result["scores"], ensure_ascii=False),
                args.model,
                now,
                now,
                row["id"],
            ),
        )
        conn.commit()
        return True

    except Exception as exc:
        conn.execute(
            "UPDATE publications SET llm_error = ?, updated_at = ? WHERE id = ?",
            (f"{type(exc).__name__}: {exc}", now, row["id"]),
        )
        conn.commit()
        return False


def get_rows(conn: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    where = []
    params: list[Any] = []

    if not args.rescore:
        where.append("llm_priority IS NULL")

    if args.only_with_pdf:
        where.append("pdf_url IS NOT NULL")

    if args.limit:
        limit = f" LIMIT {int(args.limit)}"
    else:
        limit = ""

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT id, title, category, author, publication_date
        FROM publications
        {where_sql}
        ORDER BY id
        {limit}
    """

    return conn.execute(sql, params).fetchall()


def show_ranking(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = conn.execute(
        """
        SELECT id, title, category, publication_date,
               llm_priority, llm_classification, llm_reason
        FROM publications
        WHERE llm_priority IS NOT NULL
        ORDER BY llm_priority DESC, id
        LIMIT ?
        """,
        (args.top,),
    ).fetchall()

    print()
    print("=" * 110)
    print(f"TOP {args.top} DOWNLOAD PRIORITIES")
    print("=" * 110)

    for row in rows:
        print(
            f'{row["llm_priority"]:3}  '
            f'{row["llm_classification"]:<11} '
            f'#{row["id"]:<6} '
            f'{(row["title"] or "")[:65]}'
        )
        if row["llm_reason"]:
            print(f'     {row["llm_reason"][:95]}')


def export_queue(conn: sqlite3.Connection, path: str) -> None:
    rows = conn.execute(
        """
        SELECT id, title, category, author, publication_date,
               summary_url, pdf_url, llm_priority,
               llm_classification, llm_reason, llm_scores_json
        FROM publications
        WHERE llm_priority IS NOT NULL
        ORDER BY llm_priority DESC, id
        """
    ).fetchall()

    data = [dict(row) for row in rows]
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Exported {len(data):,} scored records to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Use a local LLM to triage SKYbrary publications for download priority."
    )
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rescore", action="store_true")
    parser.add_argument("--only-with-pdf", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--export", help="Export scored queue to JSON")
    parser.add_argument("--show-ranking", action="store_true")
    args = parser.parse_args()

    conn = open_db(args.db)
    session = requests.Session()

    # LM Studio's OpenAI-compatible endpoint usually does not require auth.
    session.headers.update({"Content-Type": "application/json"})

    rows = get_rows(conn, args)

    print(f"Database : {args.db}")
    print(f"LLM      : {args.base_url}")
    print(f"Model    : {args.model}")
    print(f"To score : {len(rows):,}")
    print()

    if not rows:
        print("Nothing needs scoring.")
    else:
        good = 0
        bad = 0

        for number, row in enumerate(rows, 1):
            title = (row["title"] or "(untitled)").strip()

            print(
                f"[{number:,}/{len(rows):,}] "
                f"#{row['id']}  {title[:90]}",
                flush=True,
            )

            if score_row(conn, session, row, args):
                good += 1

                scored = conn.execute(
                    "SELECT llm_priority, llm_classification "
                    "FROM publications WHERE id = ?",
                    (row["id"],),
                ).fetchone()

                print(
                    f"    -> priority {scored['llm_priority']:3} "
                    f"({scored['llm_classification']})",
                    flush=True,
                )
            else:
                bad += 1
                err = conn.execute(
                    "SELECT llm_error FROM publications WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                print(f"    -> ERROR: {err['llm_error']}", flush=True)

            if args.delay:
                time.sleep(args.delay)

        print()
        print(f"Completed : {good:,}")
        print(f"Errors    : {bad:,}")

    if args.show_ranking or args.export:
        show_ranking(conn, args)

    if args.export:
        export_queue(conn, args.export)

    conn.close()


if __name__ == "__main__":
    main()
