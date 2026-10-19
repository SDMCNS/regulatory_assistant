import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sentence_transformers import CrossEncoder
from ingestion.retrieval.hybrid_search import search_hybrid

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
print("Retrieving 50 candidates via search_hybrid...")
candidates = search_hybrid(query=query, top_k=50)
print(f"Retrieved {len(candidates)} candidates.")

model = CrossEncoder("BAAI/bge-reranker-v2-m3")

pairs = [[query, c.get("text", "")] for c in candidates]
rerank_scores = model.predict(pairs)

reranked = list(zip(rerank_scores, candidates))
reranked.sort(key=lambda x: x[0], reverse=True)

print("\n=== TOP 10 RERANKED RESULTS (from 50 candidates) ===")
for rank, (score, c) in enumerate(reranked[:10]):
    cid = c.get("chunk_id")
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    snip = c.get("text", "")[:130].replace("\n", " ")
    is_heli = "helicopter" in snip.lower()
    tag = " [HELICOPTER]" if is_heli else ""
    print(f"{rank+1:2d}. [Score: {score:+.4f}]{tag} [{doc}] [{path}] -> {snip}...")

# Check where the helicopter chunk ended up
for rank, (score, c) in enumerate(reranked):
    snip = c.get("text", "")[:130].replace("\n", " ")
    if "helicopter" in snip.lower():
        print(f"\n--> Helicopter chunk ranked at #{rank+1} with score {score:+.4f}: {snip}...")
