import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from ingestion.core.config import settings

def get_db_path() -> Path:
    return settings.DATA_DIR / "regulations" / "sqlite" / "chunks.db"

def ensure_governance_schema(conn: sqlite3.Connection) -> None:
    """
    Ensures that the documents and chunks tables have the governance columns
    (is_active, deactivation_reason, deactivated_at, superseded_by)
    and that the governance audit log table exists.
    """
    cursor = conn.cursor()
    
    # Check documents table columns
    cursor.execute("PRAGMA table_info(documents);")
    doc_cols = {row[1] for row in cursor.fetchall()}
    
    if "is_active" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN is_active INTEGER DEFAULT 1;")
    if "deactivation_reason" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN deactivation_reason TEXT;")
    if "deactivated_at" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN deactivated_at TEXT;")
    if "superseded_by" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN superseded_by TEXT;")
        
    # Check chunks table columns
    cursor.execute("PRAGMA table_info(chunks);")
    chunk_cols = {row[1] for row in cursor.fetchall()}
    
    if "is_active" not in chunk_cols:
        cursor.execute("ALTER TABLE chunks ADD COLUMN is_active INTEGER DEFAULT 1;")
        
    # Ensure indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_active ON documents(is_active);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_active ON chunks(is_active);")
    
    # Governance audit log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_governance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            superseded_by TEXT,
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def deactivate_document(
    document_id: str, 
    reason: str, 
    superseded_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deactivates a document and all its constituent chunks.
    Records deactivation reason, timestamp, and optional superseding document reference.
    Logs the action in document_governance_logs.
    """
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        # Check document exists
        cursor.execute("SELECT document_id, title FROM documents WHERE document_id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        # Update document
        cursor.execute("""
            UPDATE documents 
            SET is_active = 0,
                deactivation_reason = ?,
                deactivated_at = datetime('now'),
                superseded_by = ?
            WHERE document_id = ?
        """, (reason.strip(), superseded_by.strip() if superseded_by else None, document_id))

        # Update all child chunks
        cursor.execute("""
            UPDATE chunks 
            SET is_active = 0 
            WHERE document_id = ?
        """, (document_id,))
        affected_chunks = cursor.rowcount

        # Log action
        cursor.execute("""
            INSERT INTO document_governance_logs (document_id, action, reason, superseded_by)
            VALUES (?, 'DEACTIVATE', ?, ?)
        """, (document_id, reason.strip(), superseded_by.strip() if superseded_by else None))

        conn.commit()

        return {
            "document_id": document_id,
            "title": doc["title"] or document_id,
            "is_active": False,
            "deactivation_reason": reason.strip(),
            "superseded_by": superseded_by.strip() if superseded_by else None,
            "affected_chunks": affected_chunks,
            "message": f"Successfully deactivated document '{document_id}' ({affected_chunks} chunks forgotten from search index)."
        }


def activate_document(document_id: str) -> Dict[str, Any]:
    """
    Reactivates a deactivated document and restores all its chunks to the active search index.
    Clears deactivation reasons and logs the restoration action.
    """
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT document_id, title FROM documents WHERE document_id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        # Update document
        cursor.execute("""
            UPDATE documents 
            SET is_active = 1,
                deactivation_reason = NULL,
                deactivated_at = NULL,
                superseded_by = NULL
            WHERE document_id = ?
        """, (document_id,))

        # Reactivate all child chunks
        cursor.execute("""
            UPDATE chunks 
            SET is_active = 1 
            WHERE document_id = ?
        """, (document_id,))
        affected_chunks = cursor.rowcount

        # Log action
        cursor.execute("""
            INSERT INTO document_governance_logs (document_id, action, reason, superseded_by)
            VALUES (?, 'ACTIVATE', 'Reactivated by user', NULL)
        """, (document_id,))

        conn.commit()

        return {
            "document_id": document_id,
            "title": doc["title"] or document_id,
            "is_active": True,
            "affected_chunks": affected_chunks,
            "message": f"Successfully reactivated document '{document_id}' ({affected_chunks} chunks restored to search index)."
        }


def resolve_document_origin(doc_id: str, title: str = "", source: str = "", metadata_json: str = "") -> str:
    """Resolves standard origin / category for a regulation or document."""
    doc_id_clean = (doc_id or "").strip()
    doc_low = ((title or "") + " " + doc_id_clean).lower()
    src = (source or "").strip()

    if src == "SKYBRARY" or doc_id_clean.startswith("SKYBRARY_"):
        return "skybrary"
    elif doc_id_clean.startswith("NOTE_") or src in ("Note", "UserNote"):
        return "note"
    elif src in ("USER", "User Supplied") or doc_id_clean.startswith("USER_"):
        return "user"
    elif src == "FAA XML" or doc_id_clean.startswith("FAA_") or "14 cfr" in doc_low:
        return "faa"
    elif src in ("Manual", "Custom") or doc_id_clean.startswith("MANUAL_"):
        return "manual"
    elif "easy access" in doc_low or "cs-" in doc_low or "amc" in doc_low:
        return "easa"
    else:
        if metadata_json:
            try:
                meta = json.loads(metadata_json)
                if meta.get("origin"):
                    return meta["origin"]
            except Exception:
                pass
        return "eu"


def batch_deactivate_documents(
    document_ids: List[str], 
    reason: str, 
    superseded_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deactivates multiple documents and all their constituent chunks in a single transaction.
    Logs each action in document_governance_logs.
    """
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    cleaned_ids = list(dict.fromkeys(d.strip() for d in document_ids if d and d.strip()))
    if not cleaned_ids:
        raise ValueError("No valid document IDs provided for batch deactivation.")

    reason_clean = (reason or "").strip()
    if len(reason_clean) < 2:
        raise ValueError("A reason of at least 2 characters is required for batch deactivation.")
    superseded_clean = superseded_by.strip() if superseded_by else None

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        total_affected_chunks = 0
        BATCH_CHUNK_SIZE = 400

        for i in range(0, len(cleaned_ids), BATCH_CHUNK_SIZE):
            chunk_slice = cleaned_ids[i:i + BATCH_CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk_slice))

            # Update documents
            cursor.execute(f"""
                UPDATE documents 
                SET is_active = 0,
                    deactivation_reason = ?,
                    deactivated_at = datetime('now'),
                    superseded_by = ?
                WHERE document_id IN ({placeholders})
            """, [reason_clean, superseded_clean] + chunk_slice)

            # Update child chunks
            cursor.execute(f"""
                UPDATE chunks 
                SET is_active = 0 
                WHERE document_id IN ({placeholders})
            """, chunk_slice)
            total_affected_chunks += cursor.rowcount

            # Log audit records
            log_entries = [
                (doc_id, 'BATCH_DEACTIVATE', reason_clean, superseded_clean)
                for doc_id in chunk_slice
            ]
            cursor.executemany("""
                INSERT INTO document_governance_logs (document_id, action, reason, superseded_by)
                VALUES (?, ?, ?, ?)
            """, log_entries)

        conn.commit()

        return {
            "deactivated_documents": len(cleaned_ids),
            "affected_chunks": total_affected_chunks,
            "reason": reason_clean,
            "superseded_by": superseded_clean,
            "message": f"Successfully deactivated {len(cleaned_ids)} documents ({total_affected_chunks} chunks forgotten from search index)."
        }


def batch_activate_documents(document_ids: List[str]) -> Dict[str, Any]:
    """
    Reactivates multiple documents and restores their constituent chunks in a single transaction.
    """
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    cleaned_ids = list(dict.fromkeys(d.strip() for d in document_ids if d and d.strip()))
    if not cleaned_ids:
        raise ValueError("No valid document IDs provided for batch activation.")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        total_affected_chunks = 0
        BATCH_CHUNK_SIZE = 400

        for i in range(0, len(cleaned_ids), BATCH_CHUNK_SIZE):
            chunk_slice = cleaned_ids[i:i + BATCH_CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk_slice))

            # Reactivate documents
            cursor.execute(f"""
                UPDATE documents 
                SET is_active = 1,
                    deactivation_reason = NULL,
                    deactivated_at = NULL,
                    superseded_by = NULL
                WHERE document_id IN ({placeholders})
            """, chunk_slice)

            # Reactivate child chunks
            cursor.execute(f"""
                UPDATE chunks 
                SET is_active = 1 
                WHERE document_id IN ({placeholders})
            """, chunk_slice)
            total_affected_chunks += cursor.rowcount

            # Log audit records
            log_entries = [
                (doc_id, 'BATCH_ACTIVATE', 'Reactivated via batch operation', None)
                for doc_id in chunk_slice
            ]
            cursor.executemany("""
                INSERT INTO document_governance_logs (document_id, action, reason, superseded_by)
                VALUES (?, ?, ?, ?)
            """, log_entries)

        conn.commit()

        return {
            "reactivated_documents": len(cleaned_ids),
            "affected_chunks": total_affected_chunks,
            "message": f"Successfully reactivated {len(cleaned_ids)} documents ({total_affected_chunks} chunks restored to search index)."
        }


def get_document_ids_by_category(category: str) -> List[str]:
    """Finds all document IDs belonging to a specific origin / category."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    cat_target = category.strip().lower()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT document_id, title, source, metadata_json FROM documents")
        matched = []
        for row in cursor.fetchall():
            orig = resolve_document_origin(row["document_id"], row["title"], row["source"], row["metadata_json"])
            if orig.lower() == cat_target:
                matched.append(row["document_id"])
        return matched


def deactivate_category(
    category: str, 
    reason: str, 
    superseded_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deactivates an entire category/origin of documents and their chunks.
    """
    cat_target = category.strip().lower()
    doc_ids = get_document_ids_by_category(cat_target)
    if not doc_ids:
        raise ValueError(f"No documents found for category '{category}'.")

    reason_text = reason.strip() if reason and reason.strip() else f"Category-level suppression of '{cat_target.upper()}'"
    res = batch_deactivate_documents(
        document_ids=doc_ids,
        reason=reason_text,
        superseded_by=superseded_by
    )
    return {
        "category": cat_target,
        "deactivated_documents": res["deactivated_documents"],
        "affected_chunks": res["affected_chunks"],
        "reason": res["reason"],
        "superseded_by": res["superseded_by"],
        "message": f"Successfully suppressed entire '{cat_target.upper()}' category ({res['deactivated_documents']} documents, {res['affected_chunks']} chunks forgotten)."
    }


def activate_category(category: str) -> Dict[str, Any]:
    """
    Activates an entire category/origin of documents and restores their chunks.
    """
    cat_target = category.strip().lower()
    doc_ids = get_document_ids_by_category(cat_target)
    if not doc_ids:
        raise ValueError(f"No documents found for category '{category}'.")

    res = batch_activate_documents(document_ids=doc_ids)
    return {
        "category": cat_target,
        "reactivated_documents": res["reactivated_documents"],
        "affected_chunks": res["affected_chunks"],
        "message": f"Successfully reactivated entire '{cat_target.upper()}' category ({res['reactivated_documents']} documents, {res['affected_chunks']} chunks restored)."
    }


def get_governance_stats() -> Dict[str, Any]:
    """
    Calculates overall knowledge governance statistics including category breakdown.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return {
            "total_documents": 0,
            "active_documents": 0,
            "deactivated_documents": 0,
            "total_chunks": 0,
            "active_chunks": 0,
            "forgotten_chunks": 0,
            "category_stats": {},
            "recent_logs": []
        }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                COUNT(*) as total_docs,
                SUM(CASE WHEN COALESCE(is_active, 1) = 1 THEN 1 ELSE 0 END) as active_docs,
                SUM(CASE WHEN COALESCE(is_active, 1) = 0 THEN 1 ELSE 0 END) as deactivated_docs
            FROM documents
        """)
        doc_stats = cursor.fetchone()

        cursor.execute("""
            SELECT 
                COUNT(*) as total_chunks,
                SUM(CASE WHEN COALESCE(is_active, 1) = 1 THEN 1 ELSE 0 END) as active_chunks,
                SUM(CASE WHEN COALESCE(is_active, 1) = 0 THEN 1 ELSE 0 END) as forgotten_chunks
            FROM chunks
        """)
        chunk_stats = cursor.fetchone()

        # Category breakdown
        category_stats: Dict[str, Dict[str, int]] = {
            "easa": {"total": 0, "active": 0, "deactivated": 0},
            "faa": {"total": 0, "active": 0, "deactivated": 0},
            "eu": {"total": 0, "active": 0, "deactivated": 0},
            "skybrary": {"total": 0, "active": 0, "deactivated": 0},
            "manual": {"total": 0, "active": 0, "deactivated": 0},
            "note": {"total": 0, "active": 0, "deactivated": 0},
            "user": {"total": 0, "active": 0, "deactivated": 0},
        }

        cursor.execute("SELECT document_id, title, source, metadata_json, COALESCE(is_active, 1) as is_act FROM documents")
        for row in cursor.fetchall():
            orig = resolve_document_origin(row["document_id"], row["title"], row["source"], row["metadata_json"])
            if orig not in category_stats:
                category_stats[orig] = {"total": 0, "active": 0, "deactivated": 0}
            category_stats[orig]["total"] += 1
            if row["is_act"]:
                category_stats[orig]["active"] += 1
            else:
                category_stats[orig]["deactivated"] += 1

        cursor.execute("""
            SELECT id, document_id, action, reason, superseded_by, performed_at
            FROM document_governance_logs
            ORDER BY id DESC
            LIMIT 25
        """)
        recent_logs = [dict(r) for r in cursor.fetchall()]

        return {
            "total_documents": doc_stats["total_docs"] or 0,
            "active_documents": doc_stats["active_docs"] or 0,
            "deactivated_documents": doc_stats["deactivated_docs"] or 0,
            "total_chunks": chunk_stats["total_chunks"] or 0,
            "active_chunks": chunk_stats["active_chunks"] or 0,
            "forgotten_chunks": chunk_stats["forgotten_chunks"] or 0,
            "category_stats": category_stats,
            "recent_logs": recent_logs
        }


def get_skybrary_topics_stats() -> List[Dict[str, Any]]:
    """
    Returns aggregated statistics for all sub-topics/categories within the SKYbrary library.
    Each item contains: topic, total, active, deactivated.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_governance_schema(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT document_id, title, source, metadata_json, COALESCE(is_active, 1) as is_act
            FROM documents
        """)
        rows = cursor.fetchall()

        topics: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            if resolve_document_origin(r["document_id"], r["title"], r["source"], r["metadata_json"]) != "skybrary":
                continue

            topic = "Uncategorized"
            if r["metadata_json"]:
                try:
                    m = json.loads(r["metadata_json"])
                    topic = (m.get("category") or "").strip() or "Uncategorized"
                except Exception:
                    pass

            if topic not in topics:
                topics[topic] = {
                    "topic": topic,
                    "total": 0,
                    "active": 0,
                    "deactivated": 0
                }
            topics[topic]["total"] += 1
            if r["is_act"] == 1:
                topics[topic]["active"] += 1
            else:
                topics[topic]["deactivated"] += 1

        # Sort descending by total documents
        return sorted(topics.values(), key=lambda x: -x["total"])


def get_skybrary_document_ids_by_topic(topic: str) -> List[str]:
    """
    Returns all document IDs in SKYbrary that match the specified subtopic/category.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return []

    target_clean = topic.strip().lower()
    doc_ids = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT document_id, title, source, metadata_json FROM documents")
        for r in cursor.fetchall():
            if resolve_document_origin(r["document_id"], r["title"], r["source"], r["metadata_json"]) != "skybrary":
                continue

            t = "Uncategorized"
            if r["metadata_json"]:
                try:
                    m = json.loads(r["metadata_json"])
                    t = (m.get("category") or "").strip() or "Uncategorized"
                except Exception:
                    pass

            if t.lower() == target_clean:
                doc_ids.append(r["document_id"])

    return doc_ids


def deactivate_skybrary_topic(
    topic: str,
    reason: str,
    superseded_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    Batch deactivates all documents under a given SKYbrary subtopic.
    """
    doc_ids = get_skybrary_document_ids_by_topic(topic)
    if not doc_ids:
        return {
            "topic": topic,
            "deactivated_documents": 0,
            "affected_chunks": 0,
            "message": f"No SKYbrary documents found for subtopic '{topic}'."
        }

    res = batch_deactivate_documents(doc_ids, reason, superseded_by)
    return {
        "topic": topic,
        "deactivated_documents": res["deactivated_documents"],
        "affected_chunks": res["affected_chunks"],
        "reason": reason,
        "superseded_by": superseded_by,
        "message": f"Successfully suppressed SKYbrary subtopic '{topic}' ({res['deactivated_documents']} documents, {res['affected_chunks']} chunks forgotten)."
    }


def activate_skybrary_topic(topic: str) -> Dict[str, Any]:
    """
    Batch reactivates all documents under a given SKYbrary subtopic.
    """
    doc_ids = get_skybrary_document_ids_by_topic(topic)
    if not doc_ids:
        return {
            "topic": topic,
            "reactivated_documents": 0,
            "affected_chunks": 0,
            "message": f"No SKYbrary documents found for subtopic '{topic}'."
        }

    res = batch_activate_documents(doc_ids)
    return {
        "topic": topic,
        "reactivated_documents": res["reactivated_documents"],
        "affected_chunks": res["affected_chunks"],
        "message": f"Successfully reactivated SKYbrary subtopic '{topic}' ({res['reactivated_documents']} documents, {res['affected_chunks']} chunks restored)."
    }
