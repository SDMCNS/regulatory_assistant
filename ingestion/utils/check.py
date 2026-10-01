import sqlite3
from pathlib import Path

# Resolve path to chunks.db
project_root = Path(__file__).resolve().parent.parent.parent
db_path = project_root / "ingestion" / "data" / "regulations" / "sqlite" / "chunks.db"
if not db_path.exists():
    db_path = project_root / "ingestion" / "data" / "sqlite" / "chunks.db"

if __name__ == "__main__":
    if not db_path.exists():
        print(f"Database not found at {db_path}")
    else:
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT chunk_id, chunk_type, source_text
                FROM chunks
                WHERE document_id LIKE 'L_2017062EN%'
                AND embedding_text LIKE '%ATSEP.OR.100 Scope%'
            """)
            rows = c.fetchall()
            if rows:
                print('\n'.join(f'{r[0]} | {r[1]} | {r[2][:50]}' for r in rows))
            else:
                print("No matching chunks found.")
