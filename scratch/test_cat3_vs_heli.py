import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import sqlite3
from ingestion.core.config import settings
from sentence_transformers import CrossEncoder

conn = sqlite3.connect(settings.SQLITE_PATH)
c = conn.cursor()

# Search chunks with CAT III or Category III or Low Visibility
c.execute("""
    SELECT chunk_id, document_id, section_path, source_text
    FROM chunks
    WHERE source_text LIKE '%CAT III%' OR source_text LIKE '%Category III%'
    LIMIT 20
""")
cat3_chunks = c.fetchall()

# Also get the helicopter chunk
c.execute("""
    SELECT chunk_id, document_id, section_path, source_text
    FROM chunks
    WHERE source_text LIKE '%CAT operations with aeroplanes and helicopters%'
    LIMIT 1
""")
heli_chunks = c.fetchall()

all_test_chunks = heli_chunks + cat3_chunks

model = CrossEncoder("BAAI/bge-reranker-v2-m3")
query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"

pairs = [[query, ch[3]] for ch in all_test_chunks]
scores = model.predict(pairs)

ranked = sorted(zip(scores, all_test_chunks), key=lambda x: x[0], reverse=True)

print("\n=== CROSS-ENCODER RANKINGS FOR CAT III vs HELICOPTER CHUNK ===")
for rank, (score, ch) in enumerate(ranked):
    cid, doc_id, sec_path, text = ch
    is_heli = "helicopter" in text.lower()
    marker = ">>> [HELICOPTER CHUNK]" if is_heli else "    [CAT III CHUNK]"
    print(f"{rank+1:2d}. {marker} Score: {score:+.4f} | [{doc_id}] [{sec_path[:40]}] -> {text[:100].replace(chr(10), ' ')}...")
