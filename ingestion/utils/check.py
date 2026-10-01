import sqlite3; c=sqlite3.connect('data/sqlite/chunks.db').cursor(); c.execute(\
SELECT
chunk_id
chunk_type
source_text
FROM
chunks
WHERE
document_id
LIKE
L_2017062EN%
AND
embedding_text
LIKE
%ATSEP.OR.100 Scope%
\); print('\n'.join(f'{r[0]} | {r[1]} | {r[2][:50]}' for r in c.fetchall()))
