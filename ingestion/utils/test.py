import sqlite3
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
db_path = project_root / "ingestion" / "data" / "regulations" / "sqlite" / "chunks.db"

if __name__ == "__main__":
    if not db_path.exists():
        print(f"Database not found at {db_path}")
    else:
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT chunk_id, chunk_type, source_text FROM chunks WHERE document_id LIKE 'L_2017062EN%'")
            for row in c.fetchall():
                if "ATSEP" in row[0] or "ATSEP" in row[2]:
                    print(f"{row[0]} | {row[1]} | {row[2][:50]}")
