"""
storage.py - SQLite Persistence for Document Consultation Sessions and Feedback Comments.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from ingestion.core.config import settings


def get_db_path() -> Path:
    return settings.SQLITE_PATH


def init_consultation_tables(conn: sqlite3.Connection) -> None:
    """Creates consultation tables and indices if they do not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consultation_sessions (
            consultation_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            domain TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            documents_json TEXT,
            metrics_json TEXT
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consultation_comments (
            comment_id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL,
            stakeholder_name TEXT,
            stakeholder_group TEXT,
            target_section TEXT,
            comment_text TEXT,
            proposed_text TEXT,
            rationale TEXT,
            themes_json TEXT,
            sentiment TEXT,
            sentiment_score REAL,
            validity TEXT,
            validity_rationale TEXT,
            matched_section_title TEXT,
            matched_section_content TEXT,
            human_review_status TEXT DEFAULT 'Pending Review',
            human_notes TEXT DEFAULT '',
            ai_assistance_notes TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(consultation_id) REFERENCES consultation_sessions(consultation_id) ON DELETE CASCADE
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_consult_cmt_session ON consultation_comments(consultation_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consult_cmt_group ON consultation_comments(stakeholder_group);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consult_cmt_sentiment ON consultation_comments(sentiment);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_consult_cmt_validity ON consultation_comments(validity);")
    conn.commit()


def save_consultation_session(
    consultation_id: str,
    title: str,
    description: str,
    domain: str,
    documents: List[Dict[str, Any]],
    comments: List[Dict[str, Any]],
    metrics: Dict[str, Any]
) -> None:
    """Inserts a new consultation session and its enriched feedback comments."""
    db_path = get_db_path()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with sqlite3.connect(db_path) as conn:
        init_consultation_tables(conn)

        conn.execute("""
            INSERT OR REPLACE INTO consultation_sessions (
                consultation_id, title, description, domain, status, created_at, updated_at, documents_json, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            consultation_id,
            title,
            description,
            domain,
            "active",
            now_iso,
            now_iso,
            json.dumps(documents, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False)
        ))

        # Insert comments
        for c in comments:
            conn.execute("""
                INSERT OR REPLACE INTO consultation_comments (
                    comment_id, consultation_id, stakeholder_name, stakeholder_group,
                    target_section, comment_text, proposed_text, rationale, themes_json,
                    sentiment, sentiment_score, validity, validity_rationale,
                    matched_section_title, matched_section_content,
                    human_review_status, human_notes, ai_assistance_notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c.get("comment_id"),
                consultation_id,
                c.get("stakeholder_name"),
                c.get("stakeholder_group"),
                c.get("target_section"),
                c.get("comment_text"),
                c.get("proposed_text", ""),
                c.get("rationale", ""),
                json.dumps(c.get("themes", []), ensure_ascii=False),
                c.get("sentiment"),
                c.get("sentiment_score", 0.0),
                c.get("validity"),
                c.get("validity_rationale", ""),
                c.get("matched_section_title"),
                c.get("matched_section_content"),
                c.get("human_review_status", "Pending Review"),
                c.get("human_notes", ""),
                c.get("ai_assistance_notes"),
                now_iso
            ))

        conn.commit()


def get_consultation_session(consultation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full consultation session with all enriched comments and document excerpts."""
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        init_consultation_tables(conn)

        sess_row = conn.execute(
            "SELECT * FROM consultation_sessions WHERE consultation_id = ?",
            (consultation_id,)
        ).fetchone()

        if not sess_row:
            return None

        comment_rows = conn.execute("""
            SELECT * FROM consultation_comments 
            WHERE consultation_id = ? 
            ORDER BY comment_id ASC
        """, (consultation_id,)).fetchall()

        comments = []
        for r in comment_rows:
            comments.append({
                "comment_id": r["comment_id"],
                "consultation_id": r["consultation_id"],
                "stakeholder_name": r["stakeholder_name"],
                "stakeholder_group": r["stakeholder_group"],
                "target_section": r["target_section"],
                "comment_text": r["comment_text"],
                "proposed_text": r["proposed_text"],
                "rationale": r["rationale"],
                "themes": json.loads(r["themes_json"] or "[]"),
                "sentiment": r["sentiment"],
                "sentiment_score": r["sentiment_score"],
                "validity": r["validity"],
                "validity_rationale": r["validity_rationale"],
                "matched_section_title": r["matched_section_title"],
                "matched_section_content": r["matched_section_content"],
                "human_review_status": r["human_review_status"],
                "human_notes": r["human_notes"],
                "ai_assistance_notes": r["ai_assistance_notes"],
                "updated_at": r["updated_at"],
            })

        return {
            "consultation_id": sess_row["consultation_id"],
            "title": sess_row["title"],
            "description": sess_row["description"],
            "domain": sess_row["domain"],
            "status": sess_row["status"],
            "created_at": sess_row["created_at"],
            "updated_at": sess_row["updated_at"],
            "documents": json.loads(sess_row["documents_json"] or "[]"),
            "metrics": json.loads(sess_row["metrics_json"] or "{}"),
            "comments": comments,
        }


def list_consultation_sessions() -> List[Dict[str, Any]]:
    """Lists all consultation sessions with summary metadata."""
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        init_consultation_tables(conn)

        rows = conn.execute("""
            SELECT s.consultation_id, s.title, s.description, s.domain, s.status,
                   s.created_at, s.updated_at, s.metrics_json,
                   COUNT(c.comment_id) as comment_count
            FROM consultation_sessions s
            LEFT JOIN consultation_comments c ON s.consultation_id = c.consultation_id
            GROUP BY s.consultation_id
            ORDER BY s.updated_at DESC
        """).fetchall()

        results = []
        for r in rows:
            results.append({
                "consultation_id": r["consultation_id"],
                "title": r["title"],
                "description": r["description"],
                "domain": r["domain"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "comment_count": r["comment_count"],
                "metrics": json.loads(r["metrics_json"] or "{}"),
            })
        return results


def update_comment_review(
    comment_id: str,
    human_review_status: str,
    human_notes: str,
    ai_assistance_notes: Optional[str] = None
) -> None:
    """Updates human reviewer triage status, notes, or assistant formulation notes."""
    db_path = get_db_path()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with sqlite3.connect(db_path) as conn:
        init_consultation_tables(conn)

        if ai_assistance_notes is not None:
            conn.execute("""
                UPDATE consultation_comments
                SET human_review_status = ?, human_notes = ?, ai_assistance_notes = ?, updated_at = ?
                WHERE comment_id = ?
            """, (human_review_status, human_notes, ai_assistance_notes, now_iso, comment_id))
        else:
            conn.execute("""
                UPDATE consultation_comments
                SET human_review_status = ?, human_notes = ?, updated_at = ?
                WHERE comment_id = ?
            """, (human_review_status, human_notes, now_iso, comment_id))

        conn.commit()


def delete_consultation_session(consultation_id: str) -> bool:
    """Deletes a consultation session and all its comments."""
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        init_consultation_tables(conn)
        conn.execute("DELETE FROM consultation_comments WHERE consultation_id = ?", (consultation_id,))
        cur = conn.execute("DELETE FROM consultation_sessions WHERE consultation_id = ?", (consultation_id,))
        conn.commit()
        return cur.rowcount > 0
