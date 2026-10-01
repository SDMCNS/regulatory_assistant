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
            # Find some merged_lists that likely contain sub-items
            c.execute("""
                SELECT chunk_id, chunk_type, section_numbers, source_text, embedding_text 
                FROM chunks 
                WHERE chunk_type = 'merged_list' 
                AND source_text LIKE '%(a)%' 
                AND source_text LIKE '%(1)%'
                LIMIT 5
            """)
            rows = c.fetchall()
            print("--- MERGED LISTS (5 samples) ---")
            for r in rows:
                print(f"\nChunk ID: {r[0]}")
                print(f"Numbers: {r[2]}")
                print(f"--- Source Text ---\n{r[3]}")
                print(f"--- Embedding Text ---\n{r[4]}")
                print("=" * 60)

            # Find some regular items
            c.execute("""
                SELECT chunk_id, chunk_type, section_numbers, source_text, embedding_text 
                FROM chunks 
                WHERE chunk_type = 'item' 
                AND (section_numbers LIKE '%(a)%' OR section_numbers LIKE '%(1)%')
                LIMIT 3
            """)
            rows = c.fetchall()
            print("\n--- REGULAR ITEMS (3 samples) ---")
            for r in rows:
                print(f"\nChunk ID: {r[0]}")
                print(f"Numbers: {r[2]}")
                print(f"--- Source Text ---\n{r[3]}")
                print(f"--- Embedding Text ---\n{r[4]}")
                print("=" * 60)
