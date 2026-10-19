import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import json
import urllib.request
import numpy as np
from ingestion.retrieval.hybrid_search import search_hybrid

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
print("Retrieving candidate chunks from search_hybrid...")
candidates = search_hybrid(query=query, top_k=20)

print(f"Retrieved {len(candidates)} candidates.")

# Test reranker
def get_embeddings(texts, model="text-embedding-baai-bge-reranker-v2-m3-m3"):
    req = urllib.request.Request(
        "http://localhost:1234/v1/embeddings",
        data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        # Sort by index if returned out of order
        data = sorted(res["data"], key=lambda x: x["index"])
        return [d["embedding"] for d in data]

print("Embedding query and chunks with reranker model...")
q_emb = get_embeddings([query])[0]
q_vec = np.array(q_emb, dtype=np.float32)
q_norm = np.linalg.norm(q_vec)

chunk_texts = [c.get("text", "") for c in candidates]
# Batch embed in groups of 10
c_embs = []
batch_size = 10
for i in range(0, len(chunk_texts), batch_size):
    batch = chunk_texts[i:i+batch_size]
    c_embs.extend(get_embeddings(batch))

scores = []
for c, emb in zip(candidates, c_embs):
    cvec = np.array(emb, dtype=np.float32)
    cnorm = np.linalg.norm(cvec)
    cos_sim = float(np.dot(q_vec, cvec) / (q_norm * cnorm)) if (q_norm * cnorm) > 0 else 0.0
    scores.append((cos_sim, c))

scores.sort(key=lambda x: x[0], reverse=True)

print("\n=== RERANKED RESULTS ===")
for rank, (score, c) in enumerate(scores):
    cid = c.get("chunk_id")
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    snippet = c.get("text", "")[:130].replace("\n", " ")
    print(f"Rank {rank+1:2d} | Rerank Score: {score:.4f} | [{doc}] [{path}] -> {snippet}...")
