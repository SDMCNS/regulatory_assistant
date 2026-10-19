import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.retrieval.hybrid_search import search_hybrid
from ingestion.retrieval.search_chunks import search_semantic

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
print("=== HYBRID SEARCH (top_k=15) ===")
results = search_hybrid(query=query, top_k=15)
for i, r in enumerate(results):
    cid = r.get("chunk_id")
    doc = r.get("document_id")
    path = " > ".join(r.get("path", []))
    score = r.get("score")
    text_snippet = r.get("text", "")[:140].replace("\n", " ")
    print(f"{i+1}. [Score: {score:.4f}] [{doc}] [{path}] -> {text_snippet}...")
