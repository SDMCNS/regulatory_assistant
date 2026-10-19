import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import List, Dict, Any, Optional
import time
import torch
from sentence_transformers import CrossEncoder

class RerankerService:
    _instance = None
    _models: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def resolve_model_name(self, model_name: Optional[str]) -> str:
        if not model_name or not model_name.strip():
            return "BAAI/bge-reranker-v2-m3"
        clean = model_name.strip()
        # Handle LM Studio or local model naming
        if "bge-reranker-v2-m3" in clean.lower():
            return "BAAI/bge-reranker-v2-m3"
        if "bge-reranker-large" in clean.lower():
            return "BAAI/bge-reranker-large"
        if "bge-reranker-base" in clean.lower():
            return "BAAI/bge-reranker-base"
        return clean

    def get_cross_encoder(self, model_name: Optional[str] = None):
        resolved = self.resolve_model_name(model_name)
        if resolved not in self._models:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[RerankerService] Loading CrossEncoder model '{resolved}' on device '{device}'...")
            t0 = time.time()
            self._models[resolved] = CrossEncoder(resolved, device=device)
            print(f"[RerankerService] Model '{resolved}' loaded in {time.time() - t0:.2f}s")
        return self._models[resolved]

    def rerank_chunks(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not chunks or not query.strip():
            return chunks

        model = self.get_cross_encoder(model_name)

        # Prepare structured input for each candidate chunk
        pairs = []
        for c in chunks:
            doc_id = c.get("document_id", "Regulation")
            title = c.get("title") or c.get("document_title") or doc_id
            path = c.get("path") or c.get("section_path") or []
            path_str = " > ".join(path) if isinstance(path, list) else str(path)
            text = c.get("text") or c.get("source_text") or ""
            
            # Structured passage gives the cross-encoder context of domain and section
            structured_text = f"Document: {title} ({doc_id})\nSection: {path_str}\nContent:\n{text}"
            pairs.append([query, structured_text])

        try:
            scores = model.predict(pairs, batch_size=32)
        except Exception as e:
            print(f"[RerankerService] Prediction failed: {e}")
            return chunks

        reranked = []
        for orig_idx, (score, c) in enumerate(zip(scores, chunks)):
            c_copy = dict(c)
            c_copy["rerank_score"] = float(score)
            c_copy["original_rank"] = orig_idx + 1
            reranked.append(c_copy)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)

        for new_idx, c in enumerate(reranked):
            c["rerank_rank"] = new_idx + 1

        if top_k is not None and top_k > 0:
            return reranked[:top_k]
        return reranked

# Test
if __name__ == "__main__":
    service = RerankerService.get_instance()
    from ingestion.retrieval.hybrid_search import search_hybrid
    q = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
    print(f"Testing search_hybrid with query: '{q}'")
    candidates = search_hybrid(query=q, top_k=25)
    print(f"Retrieved {len(candidates)} candidates.")
    
    print("\nExecuting rerank_chunks...")
    t0 = time.time()
    results = service.rerank_chunks(q, candidates, model_name="text-embedding-baai-bge-reranker-v2-m3-m3", top_k=5)
    print(f"Reranking completed in {time.time() - t0:.3f}s. Top 5 results:")
    for r in results:
        doc = r.get("document_id")
        path = " > ".join(r.get("path", []))
        score = r.get("rerank_score")
        orig_r = r.get("original_rank")
        rer_r = r.get("rerank_rank")
        snip = r.get("text", "")[:120].replace("\n", " ")
        print(f"Rank {rer_r} (was {orig_r}) | Score: {score:+.4f} | [{doc}] [{path}] -> {snip}...")
