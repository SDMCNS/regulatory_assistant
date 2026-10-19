import sqlite3

conn = sqlite3.connect("data/regulations/sqlite/chunks.db")
c = conn.cursor()
c.execute("SELECT chunk_id, document_id, section_path, source_text FROM chunks WHERE source_text LIKE '%CAT III%' OR source_text LIKE '%Category III%' LIMIT 10")
rows = c.fetchall()
print(f"Total found: {len(rows)}")
for r in rows:
    print(f"[{r[1]}] [{r[2]}] -> {r[3][:120].replace(chr(10), ' ')}...")
