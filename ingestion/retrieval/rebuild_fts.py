import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.core.config import settings
from ingestion.retrieval.keyword_search import ensure_fts_index

def rebuild_fts(db_path: Optional[Path] = None):
    target_db = Path(db_path) if db_path else settings.SQLITE_PATH
    if not target_db.exists():
        print(f"Error: Database not found at {target_db}")
        return

    print(f"Connecting to SQLite database at {target_db}...")
    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        
        # Ensure the table exists first (if not, it creates it)
        ensure_fts_index(conn)
        
        print("Rebuilding FTS5 index...")
        # Issue the rebuild command
        cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');")
        conn.commit()
        
        # Optimize the FTS index
        print("Optimizing FTS5 index...")
        cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize');")
        conn.commit()
        
        print("FTS index rebuilt and optimized successfully.")

if __name__ == "__main__":
    rebuild_fts()
