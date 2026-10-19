"""
storage.py - SQLite Persistence for Document Consultation Sessions, Feedback Comments,
Field Mappings, and Required Text Blocks.
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


def ensure_column_exists(conn: sqlite3.Connection, table_name: str, col_name: str, col_type: str) -> None:
    """Safely adds a column to an existing SQLite table if it does not already exist."""
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    existing_cols = [row[1] for row in cur.fetchall()]
    if col_name not in existing_cols:
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type};")
        except sqlite3.OperationalError:
            pass


def init_consultation_tables(conn: sqlite3.Connection) -> None:
    """Creates consultation tables and indices if they do not exist, and runs safe migrations."""
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
            metrics_json TEXT,
            field_mapping_json TEXT,
            required_text_blocks_json TEXT,
            organisations_analysis_json TEXT
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS consultation_comments (
            comment_id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL,
            document_title TEXT,
            chapter_section TEXT,
            page TEXT,
            original_text TEXT,
            comment_text TEXT,
            comment_type TEXT,
            importance TEXT,
            proposed_text TEXT,
            stakeholder_category TEXT,
            organisation_name TEXT,
            af_cba TEXT,
            response_to_comment TEXT,
            rationale_and_changes TEXT,
            overall_id TEXT,
            stakeholder_name TEXT,
            stakeholder_group TEXT,
            target_section TEXT,
            rationale TEXT,
            themes_json TEXT,
            sentiment TEXT,
            sentiment_score REAL,
            section_score REAL,
            document_score REAL,
            weighted_score REAL,
            direction_of_travel TEXT,
            support_network_json TEXT,
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

    # Safe column migrations for existing databases
    session_columns = [
        ("field_mapping_json", "TEXT"),
        ("required_text_blocks_json", "TEXT"),
        ("organisations_analysis_json", "TEXT"),
    ]
    for col, col_type in session_columns:
        ensure_column_exists(conn, "consultation_sessions", col, col_type)

    comment_columns = [
        ("document_title", "TEXT"),
        ("chapter_section", "TEXT"),
        ("page", "TEXT"),
        ("original_text", "TEXT"),
        ("comment_type", "TEXT"),
        ("importance", "TEXT"),
        ("stakeholder_category", "TEXT"),
        ("organisation_name", "TEXT"),
        ("af_cba", "TEXT"),
        ("response_to_comment", "TEXT"),
        ("rationale_and_changes", "TEXT"),
        ("overall_id", "TEXT"),
        ("section_score", "REAL"),
        ("document_score", "REAL"),
        ("weighted_score", "REAL"),
        ("direction_of_travel", "TEXT"),
        ("support_network_json", "TEXT"),
    ]
    for col, col_type in comment_columns:
        ensure_column_exists(conn, "consultation_comments", col, col_type)

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
    metrics: Dict[str, Any],
    field_mapping: Optional[Dict[str, Any]] = None,
    required_text_blocks: Optional[List[Dict[str, Any]]] = None,
    organisations_analysis: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Inserts or replaces a consultation session, text blocks, and enriched comments."""
    db_path = get_db_path()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with sqlite3.connect(db_path) as conn:
        init_consultation_tables(conn)

        conn.execute("""
            INSERT OR REPLACE INTO consultation_sessions (
                consultation_id, title, description, domain, status, created_at, updated_at,
                documents_json, metrics_json, field_mapping_json, required_text_blocks_json, organisations_analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            consultation_id,
            title,
            description,
            domain,
            "active",
            now_iso,
            now_iso,
            json.dumps(documents, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            json.dumps(field_mapping or {}, ensure_ascii=False),
            json.dumps(required_text_blocks or [], ensure_ascii=False),
            json.dumps(organisations_analysis or [], ensure_ascii=False),
        ))

        # Insert comments
        for c in comments:
            conn.execute("""
                INSERT OR REPLACE INTO consultation_comments (
                    comment_id, consultation_id, document_title, chapter_section, page,
                    original_text, comment_text, comment_type, importance, proposed_text,
                    stakeholder_category, organisation_name, af_cba, response_to_comment,
                    rationale_and_changes, overall_id, stakeholder_name, stakeholder_group,
                    target_section, rationale, themes_json, sentiment, sentiment_score,
                    section_score, document_score, weighted_score, direction_of_travel,
                    support_network_json,
                    validity, validity_rationale, matched_section_title, matched_section_content,
                    human_review_status, human_notes, ai_assistance_notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c.get("comment_id"),
                consultation_id,
                c.get("document_title"),
                c.get("chapter_section") or c.get("target_section"),
                c.get("page"),
                c.get("original_text", ""),
                c.get("comment_text"),
                c.get("comment_type", ""),
                c.get("importance", "Medium"),
                c.get("proposed_text", ""),
                c.get("stakeholder_category") or c.get("stakeholder_group"),
                c.get("organisation_name") or c.get("stakeholder_name"),
                c.get("af_cba", ""),
                c.get("response_to_comment", ""),
                c.get("rationale_and_changes") or c.get("rationale", ""),
                c.get("overall_id") or c.get("comment_id"),
                c.get("stakeholder_name") or c.get("organisation_name"),
                c.get("stakeholder_group") or c.get("stakeholder_category"),
                c.get("target_section") or c.get("chapter_section"),
                c.get("rationale") or c.get("rationale_and_changes", ""),
                json.dumps(c.get("themes", []), ensure_ascii=False),
                c.get("sentiment"),
                c.get("sentiment_score", 0.0),
                c.get("section_score", c.get("sentiment_score", 0.0)),
                c.get("document_score", c.get("sentiment_score", 0.0)),
                c.get("weighted_score", c.get("sentiment_score", 0.0)),
                c.get("direction_of_travel", ""),
                json.dumps(c.get("support_network") or {}, ensure_ascii=False),
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
    """Retrieves full consultation session with all enriched comments, document text blocks, and metrics."""
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
                "document_title": r["document_title"] if "document_title" in r.keys() else "",
                "chapter_section": r["chapter_section"] if "chapter_section" in r.keys() else r["target_section"],
                "page": r["page"] if "page" in r.keys() else "",
                "original_text": r["original_text"] if "original_text" in r.keys() else "",
                "comment_text": r["comment_text"],
                "comment_type": r["comment_type"] if "comment_type" in r.keys() else "",
                "importance": r["importance"] if "importance" in r.keys() else "Medium",
                "proposed_text": r["proposed_text"],
                "stakeholder_category": r["stakeholder_category"] if "stakeholder_category" in r.keys() else r["stakeholder_group"],
                "organisation_name": r["organisation_name"] if "organisation_name" in r.keys() else r["stakeholder_name"],
                "af_cba": r["af_cba"] if "af_cba" in r.keys() else "",
                "response_to_comment": r["response_to_comment"] if "response_to_comment" in r.keys() else "",
                "rationale_and_changes": r["rationale_and_changes"] if "rationale_and_changes" in r.keys() else r["rationale"],
                "overall_id": r["overall_id"] if "overall_id" in r.keys() else r["comment_id"],
                "stakeholder_name": r["stakeholder_name"],
                "stakeholder_group": r["stakeholder_group"],
                "target_section": r["target_section"],
                "rationale": r["rationale"],
                "themes": json.loads(r["themes_json"] or "[]"),
                "sentiment": r["sentiment"],
                "sentiment_score": r["sentiment_score"],
                "section_score": r["section_score"] if "section_score" in r.keys() else r["sentiment_score"],
                "document_score": r["document_score"] if "document_score" in r.keys() else r["sentiment_score"],
                "weighted_score": r["weighted_score"] if "weighted_score" in r.keys() else r["sentiment_score"],
                "direction_of_travel": r["direction_of_travel"] if "direction_of_travel" in r.keys() else "",
                "support_network": json.loads(r["support_network_json"] or "{}") if "support_network_json" in r.keys() and r["support_network_json"] else None,
                "validity": r["validity"],
                "validity_rationale": r["validity_rationale"],
                "matched_section_title": r["matched_section_title"],
                "matched_section_content": r["matched_section_content"],
                "human_review_status": r["human_review_status"],
                "human_notes": r["human_notes"],
                "ai_assistance_notes": r["ai_assistance_notes"],
                "updated_at": r["updated_at"],
            })

        field_mapping = json.loads(sess_row["field_mapping_json"] or "{}") if "field_mapping_json" in sess_row.keys() else {}
        required_text_blocks = json.loads(sess_row["required_text_blocks_json"] or "[]") if "required_text_blocks_json" in sess_row.keys() else []
        organisations_analysis = json.loads(sess_row["organisations_analysis_json"] or "[]") if "organisations_analysis_json" in sess_row.keys() else []

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
            "field_mapping": field_mapping,
            "required_text_blocks": required_text_blocks,
            "organisations_analysis": organisations_analysis,
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


def update_session_text_block(
    consultation_id: str,
    block_id: str,
    new_content: str
) -> Optional[Dict[str, Any]]:
    """Updates the content of a required text block and updates matching in consultation comments."""
    db_path = get_db_path()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        init_consultation_tables(conn)

        sess_row = conn.execute(
            "SELECT * FROM consultation_sessions WHERE consultation_id = ?",
            (consultation_id,)
        ).fetchone()

        if not sess_row:
            return None

        blocks = json.loads(sess_row["required_text_blocks_json"] or "[]")
        target_block = None

        for b in blocks:
            if b.get("block_id") == block_id:
                b["content"] = new_content
                b["status"] = "provided" if new_content.strip() else "missing"
                b["action_required"] = "None (Text Available)" if new_content.strip() else "User must provide / paste document text block"
                target_block = b
                break

        if not target_block:
            return None

        # Update matching in comments referencing this block
        affected_comment_ids = target_block.get("comment_ids", [])
        for cid in affected_comment_ids:
            conn.execute("""
                UPDATE consultation_comments
                SET matched_section_title = ?, matched_section_content = ?, updated_at = ?
                WHERE comment_id = ? AND consultation_id = ?
            """, (
                target_block.get("chapter_section"),
                new_content[:2500],
                now_iso,
                cid,
                consultation_id
            ))

        # Save updated blocks JSON
        conn.execute("""
            UPDATE consultation_sessions
            SET required_text_blocks_json = ?, updated_at = ?
            WHERE consultation_id = ?
        """, (json.dumps(blocks, ensure_ascii=False), now_iso, consultation_id))

        conn.commit()
        return target_block


def delete_consultation_session(consultation_id: str) -> bool:
    """Deletes a consultation session and all its comments."""
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        init_consultation_tables(conn)
        conn.execute("DELETE FROM consultation_comments WHERE consultation_id = ?", (consultation_id,))
        cur = conn.execute("DELETE FROM consultation_sessions WHERE consultation_id = ?", (consultation_id,))
        conn.commit()
        return cur.rowcount > 0
