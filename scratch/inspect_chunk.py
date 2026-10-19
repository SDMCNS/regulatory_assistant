import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import sqlite3
from ingestion.core.config import settings

conn = sqlite3.connect(settings.SQLITE_PATH)
c = conn.cursor()
c.execute("SELECT chunk_id, document_id, section_path, source_text FROM chunks WHERE document_id = 'L_202401111EN.000101.fmx' LIMIT 3")
rows = c.fetchall()
for r in rows:
    print(r[0], r[2])
    print("--- TEXT ---")
    print(r[3])
    print("=" * 60)
