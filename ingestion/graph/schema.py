"""
schema.py - Kùzu Database Schema Definition for EASA Regulatory Knowledge Graph.

Defines Node and Relationship tables representing the EASA regulatory ontology:
- Document -> Annex -> Provision (IR / AMC / GM / CS)
- Concept (Ontological topics: Fuel Scheme, SMS, EDTO, etc.)
- Stakeholder (Operator, PIC, Authority, CAMO)
- Relationships: CONTAINS_ANNEX, BELONGS_TO_ANNEX, SATISFIES (AMC->IR),
  EXPLAINS (GM->IR/AMC), CROSS_REFERENCES, GOVERNS_CONCEPT, APPLIES_TO, SIMILAR_TO
"""

from pathlib import Path
import kuzu
from ingestion.core.config import settings


def init_schema(conn: kuzu.Connection) -> None:
    """Initializes node and relationship tables in Kùzu."""

    # 1. Node Tables
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS RegulationDocument (
            id STRING,
            title STRING,
            source STRING,
            total_topics INT64,
            PRIMARY KEY (id)
        );
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Annex (
            id STRING,
            code STRING,
            name STRING,
            PRIMARY KEY (id)
        );
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Provision (
            id STRING,
            code STRING,
            base_code STRING,
            title STRING,
            content_type STRING,
            legal_force STRING,
            subject STRING,
            text STRING,
            word_count INT64,
            PRIMARY KEY (id)
        );
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Concept (
            id STRING,
            name STRING,
            category STRING,
            PRIMARY KEY (id)
        );
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Stakeholder (
            id STRING,
            name STRING,
            role_type STRING,
            PRIMARY KEY (id)
        );
    """)

    # 2. Relationship Tables
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS CONTAINS_ANNEX (
            FROM RegulationDocument TO Annex
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS BELONGS_TO_ANNEX (
            FROM Provision TO Annex
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS SATISFIES (
            FROM Provision TO Provision
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS EXPLAINS (
            FROM Provision TO Provision
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS CROSS_REFERENCES (
            FROM Provision TO Provision
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS GOVERNS_CONCEPT (
            FROM Provision TO Concept,
            relevance STRING
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS APPLIES_TO (
            FROM Provision TO Stakeholder,
            obligation STRING
        );
    """)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS SIMILAR_TO (
            FROM Provision TO Provision,
            score DOUBLE,
            method STRING,
            reason STRING
        );
    """)


def get_connection(db_path: Path = None) -> tuple[kuzu.Database, kuzu.Connection]:
    """Opens or creates a Kùzu database and returns (db, conn)."""
    if db_path is None:
        db_path = settings.KUZU_DB_PATH
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    init_schema(conn)
    return db, conn
