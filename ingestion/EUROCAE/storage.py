"""
Storage layer for EUROCAE and European aviation standards in SQLite.

Manages:
- eurocae_standards table in chunks.db
- eurocae_standards_fts FTS5 full-text search table
- Querying, filtering, and retrieval for supporting standards.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

from ingestion.core.config import settings
from .models import EurocaeStandard


def get_db_path() -> Path:
    return settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"


def init_eurocae_db(conn: sqlite3.Connection):
    """
    Initializes the eurocae_standards and full-text search tables.
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eurocae_standards (
            standard_id TEXT PRIMARY KEY,
            reference TEXT NOT NULL,
            title TEXT NOT NULL,
            expanded_title TEXT,
            status TEXT NOT NULL,
            organization TEXT,
            working_group TEXT,
            working_group_desc TEXT,
            domain TEXT,
            publication_date TEXT,
            master_plan_ref TEXT,
            cps_af TEXT,
            sdm_families TEXT,
            easa_reference TEXT,
            comment TEXT,
            hyde_summary TEXT,
            unique_ardp_id TEXT,
            recognized_acronyms_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eurocae_ref ON eurocae_standards(reference);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eurocae_status ON eurocae_standards(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eurocae_domain ON eurocae_standards(domain);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eurocae_wg ON eurocae_standards(working_group);")

    # FTS5 full-text index
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS eurocae_standards_fts USING fts5(
            standard_id UNINDEXED,
            reference,
            title,
            expanded_title,
            domain,
            working_group,
            working_group_desc,
            easa_reference,
            comment,
            hyde_summary
        );
    """)
    conn.commit()


def upsert_standards(standards: List[EurocaeStandard], db_path: Optional[Path] = None) -> int:
    """
    Upserts a list of EurocaeStandard records into SQLite and refreshes FTS index.
    """
    if db_path is None:
        db_path = get_db_path()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        init_eurocae_db(conn)
        cursor = conn.cursor()

        # Delete old records to prevent stale duplicates on update
        cursor.execute("DELETE FROM eurocae_standards;")
        cursor.execute("DELETE FROM eurocae_standards_fts;")

        for std in standards:
            acronyms_json = json.dumps(std.recognized_acronyms) if std.recognized_acronyms else "{}"

            cursor.execute("""
                INSERT OR REPLACE INTO eurocae_standards (
                    standard_id, reference, title, expanded_title, status, organization,
                    working_group, working_group_desc, domain, publication_date,
                    master_plan_ref, cps_af, sdm_families, easa_reference, comment,
                    hyde_summary, unique_ardp_id, recognized_acronyms_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                std.standard_id,
                std.reference,
                std.title,
                std.expanded_title,
                std.status,
                std.organization,
                std.working_group,
                std.working_group_desc,
                std.domain,
                std.publication_date,
                std.master_plan_ref,
                std.cps_af,
                std.sdm_families,
                std.easa_reference,
                std.comment,
                std.hyde_summary,
                std.unique_ardp_id,
                acronyms_json
            ))

            # Populate FTS5 index
            cursor.execute("""
                INSERT INTO eurocae_standards_fts (
                    standard_id, reference, title, expanded_title, domain,
                    working_group, working_group_desc, easa_reference, comment, hyde_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                std.standard_id,
                std.reference,
                std.title,
                std.expanded_title,
                std.domain or "",
                std.working_group or "",
                std.working_group_desc or "",
                std.easa_reference or "",
                std.comment or "",
                std.hyde_summary or ""
            ))

        conn.commit()
        return len(standards)


def get_standard_by_reference(reference_or_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves standard details by reference or standard_id.
    """
    if db_path is None:
        db_path = get_db_path()
    if not db_path.exists():
        return None

    clean_ref = reference_or_id.strip()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM eurocae_standards
            WHERE standard_id = ? OR UPPER(reference) = UPPER(?) OR standard_id LIKE ?
            LIMIT 1
        """, (clean_ref, clean_ref, f"{clean_ref}%"))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            if d.get("recognized_acronyms_json"):
                try:
                    d["recognized_acronyms"] = json.loads(d["recognized_acronyms_json"])
                except Exception:
                    d["recognized_acronyms"] = {}
            return d
    return None


def search_standards(
    query: str, 
    top_k: int = 10, 
    domain: Optional[str] = None, 
    status: Optional[str] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Full-text search on EUROCAE standards using BM25 across titles, expanded titles,
    working groups, domains, EASA references, and HyDE summaries.
    """
    if db_path is None:
        db_path = get_db_path()
    if not db_path.exists():
        return []

    # Clean and sanitize FTS query
    sanitized = "".join(c if c.isalnum() or c in ("-", "_", " ") else " " for c in query)
    tokens = [t.strip() for t in sanitized.split() if len(t.strip()) >= 2]
    if not tokens:
        return []

    # Build match query: e.g. "ACAS" OR "Xu" OR "ED-275A"
    match_query = " OR ".join(f'"{t}"' for t in tokens)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build dynamic SQL
        where_clauses = ["eurocae_standards_fts MATCH ?"]
        params: List[Any] = [match_query]

        if domain:
            where_clauses.append("LOWER(s.domain) = LOWER(?)")
            params.append(domain)
        if status:
            where_clauses.append("LOWER(s.status) = LOWER(?)")
            params.append(status)

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT s.*, bm25(eurocae_standards_fts) as bm25_rank
            FROM eurocae_standards_fts f
            JOIN eurocae_standards s ON f.standard_id = s.standard_id
            WHERE {where_sql}
            ORDER BY bm25_rank ASC
            LIMIT ?
        """
        params.append(top_k)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback to simple LIKE search if FTS query expression syntax failed
            like_clauses = ["(s.title LIKE ? OR s.reference LIKE ? OR s.expanded_title LIKE ? OR s.domain LIKE ?)"]
            like_param = f"%{query.strip()}%"
            like_params: List[Any] = [like_param, like_param, like_param, like_param]

            if domain:
                like_clauses.append("LOWER(s.domain) = LOWER(?)")
                like_params.append(domain)
            if status:
                like_clauses.append("LOWER(s.status) = LOWER(?)")
                like_params.append(status)

            like_sql = f"""
                SELECT s.*, 0.0 as bm25_rank
                FROM eurocae_standards s
                WHERE {" AND ".join(like_clauses)}
                LIMIT ?
            """
            like_params.append(top_k)
            cursor.execute(like_sql, like_params)
            rows = cursor.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            if d.get("recognized_acronyms_json"):
                try:
                    d["recognized_acronyms"] = json.loads(d["recognized_acronyms_json"])
                except Exception:
                    d["recognized_acronyms"] = {}
            results.append(d)

        return results


def get_all_standards(
    limit: int = 500, 
    offset: int = 0, 
    domain: Optional[str] = None, 
    status: Optional[str] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Lists standards with optional filtering and pagination."""
    if db_path is None:
        db_path = get_db_path()
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where = []
        params: List[Any] = []
        if domain:
            where.append("LOWER(domain) = LOWER(?)")
            params.append(domain)
        if status:
            where.append("LOWER(status) = LOWER(?)")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"SELECT * FROM eurocae_standards {where_sql} ORDER BY status, reference LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_eurocae_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Returns summary statistics for the EUROCAE standards catalog."""
    if db_path is None:
        db_path = get_db_path()
    if not db_path.exists():
        return {"total": 0, "published": 0, "ongoing": 0, "planned": 0}

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM eurocae_standards;")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT status, COUNT(*) FROM eurocae_standards GROUP BY status;")
        status_counts = dict(cursor.fetchall())

        cursor.execute("SELECT domain, COUNT(*) FROM eurocae_standards WHERE domain IS NOT NULL GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10;")
        domain_counts = dict(cursor.fetchall())

        cursor.execute("SELECT working_group, COUNT(*) FROM eurocae_standards WHERE working_group IS NOT NULL GROUP BY working_group ORDER BY COUNT(*) DESC LIMIT 10;")
        wg_counts = dict(cursor.fetchall())

        return {
            "total_standards": total,
            "status_distribution": status_counts,
            "top_domains": domain_counts,
            "top_working_groups": wg_counts
        }
