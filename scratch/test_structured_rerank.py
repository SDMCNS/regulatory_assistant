import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from sentence_transformers import CrossEncoder
from ingestion.retrieval.hybrid_search import search_hybrid

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
print("Retrieving candidates...")
candidates = search_hybrid(query=query, top_k=50)

model = CrossEncoder("BAAI/bge-reranker-v2-m3")

# Test 1: Text only
pairs_text_only = [[query, c.get("text", "")] for c in candidates]
scores_text_only = model.predict(pairs_text_only)

# Test 2: Structured text (Document title + Section path + Text)
def format_cand(c):
    doc = c.get("document_id", "")
    path = " > ".join(c.get("path", []))
    text = c.get("text", "")
    return f"Document: {doc}\nSection: {path}\nContent:\n{text}"

pairs_structured = [[query, format_cand(c)] for c in candidates]
scores_structured = model.predict(pairs_structured)

print("\n=== COMPARISON FOR HELICOPTER CHUNKS ===")
for i, c in enumerate(candidates):
    snip = c.get("text", "")[:120].replace("\n", " ")
    if "helicopter" in snip.lower() or "cat operations with aeroplanes" in snip.lower():
        doc = c.get("document_id")
        path = " > ".join(c.get("path", []))
        s_text = scores_text_only[i]
        s_struct = scores_structured[i]
        print(f"[{doc}] [{path[:40]}]")
        print(f"   Text-only Score:   {s_text:+.4f}")
        print(f"   Structured Score:  {s_struct:+.4f}")
        print(f"   Snippet: {snip}...\n")

# Top 5 under structured:
ranked_struct = sorted(zip(scores_structured, candidates), key=lambda x: x[0], reverse=True)
print("=== TOP 8 STRUCTURED RERANKED ===")
for r, (score, c) in enumerate(ranked_struct[:8]):
    doc = c.get("document_id")
    path = " > ".join(c.get("path", []))
    snip = c.get("text", "")[:100].replace("\n", " ")
    print(f"{r+1}. Score: {score:+.4f} | [{doc}] [{path}] -> {snip}...")
