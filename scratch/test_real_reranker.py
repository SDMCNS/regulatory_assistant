import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sentence_transformers import CrossEncoder
from ingestion.retrieval.hybrid_search import search_hybrid

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
print("Retrieving candidates via search_hybrid...")
candidates = search_hybrid(query=query, top_k=25)
print(f"Retrieved {len(candidates)} candidates.")

print("\n--- BEFORE RERANKING (Top 10 from search_hybrid) ---")
for i, c in enumerate(candidates[:10]):
    cid = c.get("chunk_id")
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    score = c.get("score")
    snip = c.get("text", "")[:120].replace("\n", " ")
    print(f"{i+1:2d}. [Score: {score:.4f}] [{doc}] [{path}] -> {snip}...")

print("\nScoring with CrossEncoder('BAAI/bge-reranker-v2-m3')...")
model = CrossEncoder("BAAI/bge-reranker-v2-m3")

pairs = [[query, c.get("text", "")] for c in candidates]
rerank_scores = model.predict(pairs)

reranked = list(zip(rerank_scores, candidates))
reranked.sort(key=lambda x: x[0], reverse=True)

print("\n--- AFTER RERANKING (Top 15 via CrossEncoder) ---")
for rank, (score, c) in enumerate(reranked[:15]):
    cid = c.get("chunk_id")
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    snip = c.get("text", "")[:130].replace("\n", " ")
    print(f"{rank+1:2d}. [Rerank: {score:+.4f}] [{doc}] [{path}] -> {snip}...")

print("\n--- BOTTOM 5 AFTER RERANKING ---")
for rank, (score, c) in enumerate(reranked[-5:]):
    cid = c.get("chunk_id")
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    snip = c.get("text", "")[:130].replace("\n", " ")
    print(f"{len(reranked)-5+rank+1:2d}. [Rerank: {score:+.4f}] [{doc}] [{path}] -> {snip}...")
