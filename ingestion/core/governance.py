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


def get_governance_stats() -> Dict[str, Any]:
    """
    Calculates overall knowledge governance statistics.
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

        cursor.execute("""
            SELECT id, document_id, action, reason, superseded_by, performed_at
            FROM document_governance_logs
            ORDER BY id DESC
            LIMIT 20
        """)
        recent_logs = [dict(r) for r in cursor.fetchall()]

        return {
            "total_documents": doc_stats["total_docs"] or 0,
            "active_documents": doc_stats["active_docs"] or 0,
            "deactivated_documents": doc_stats["deactivated_docs"] or 0,
            "total_chunks": chunk_stats["total_chunks"] or 0,
            "active_chunks": chunk_stats["active_chunks"] or 0,
            "forgotten_chunks": chunk_stats["forgotten_chunks"] or 0,
            "recent_logs": recent_logs
        }
