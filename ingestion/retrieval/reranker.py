"""
Neural Reranker Preprocessing Service

Preprocesses and ranks candidate chunks retrieved from semantic vector search,
BM25 keyword search, and reciprocal rank fusion (RRF) before context injection into LLM prompts.
Supports HuggingFace CrossEncoders (e.g. BAAI/bge-reranker-v2-m3) and LM Studio hosted reranker configurations.
"""

import sys
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.core.config import settings

logger = logging.getLogger("RerankerService")

class RerankerService:
    _instance: Optional["RerankerService"] = None
    _models: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> "RerankerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def resolve_model_name(self, model_name: Optional[str] = None) -> str:
        """
        Maps user or LM Studio model names to appropriate CrossEncoder model identifiers or local paths.
        """
        raw = (model_name or settings.RERANKER_MODEL_NAME or "").strip()
        if not raw:
            return "BAAI/bge-reranker-v2-m3"

        raw_lower = raw.lower()
        if "bge-reranker-v2-m3" in raw_lower:
            return "BAAI/bge-reranker-v2-m3"
        elif "bge-reranker-large" in raw_lower:
            return "BAAI/bge-reranker-large"
        elif "bge-reranker-base" in raw_lower:
            return "BAAI/bge-reranker-base"
        
        return raw

    def get_cross_encoder(self, model_name: Optional[str] = None):
        """
        Retrieves or initializes a cached CrossEncoder instance.
        """
        import torch
        from sentence_transformers import CrossEncoder

        resolved = self.resolve_model_name(model_name)
        if resolved not in self._models:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Initializing CrossEncoder model '{resolved}' on device '{device}'...")
            t0 = time.time()
            try:
                self._models[resolved] = CrossEncoder(resolved, device=device)
                logger.info(f"CrossEncoder model '{resolved}' initialized in {time.time() - t0:.2f}s")
            except Exception as e:
                logger.error(f"Failed to load CrossEncoder for '{resolved}': {e}")
                raise e

        return self._models[resolved]

    def _build_structured_chunk_text(self, chunk: Dict[str, Any]) -> str:
        """
        Formats a chunk with document title, section breadcrumbs, and content
        to provide the cross-encoder with regulatory structural context.
        """
        doc_id = chunk.get("document_id", "Regulation")
        title = chunk.get("title") or chunk.get("document_title") or doc_id
        path = chunk.get("path") or chunk.get("section_path") or []
        path_str = " > ".join(path) if isinstance(path, list) else str(path)
        text = chunk.get("text") or chunk.get("source_text") or ""
        
        return f"Document: {title} ({doc_id})\nSection: {path_str}\nContent:\n{text}"

    def predict_scores(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model_name: Optional[str] = None
    ) -> List[float]:
        """
        Predicts cross-encoder relevance scores for query-chunk pairs.
        """
        if not chunks or not query.strip():
            return []

        model = self.get_cross_encoder(model_name)
        pairs = [[query, self._build_structured_chunk_text(c)] for c in chunks]

        scores = model.predict(pairs, batch_size=32)
        return [float(s) for s in scores]

    def rerank_chunks(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Reranks a list of candidate chunks against a query.
        Attaches 'rerank_score', 'original_rank', and 'rerank_rank' to each chunk.
        Returns the top_k ranked chunks.
        """
        if not chunks:
            return []
        if not query or not query.strip():
            return chunks[:top_k] if top_k else chunks

        try:
            scores = self.predict_scores(query, chunks, model_name=model_name)
        except Exception as e:
            logger.warning(f"Reranking encountered an error ({e}). Falling back to original candidate ranking.")
            return chunks[:top_k] if top_k else chunks

        reranked = []
        for orig_idx, (score, c) in enumerate(zip(scores, chunks)):
            c_copy = dict(c)
            c_copy["rerank_score"] = float(score)
            c_copy["original_rank"] = orig_idx + 1
            reranked.append(c_copy)

        # Sort descending by neural cross-encoder score
        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)

        for new_idx, c in enumerate(reranked):
            c["rerank_rank"] = new_idx + 1

        if top_k is not None and top_k > 0:
            return reranked[:top_k]
        return reranked

    def test_status(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Tests the reranker model initialization and returns diagnostic information.
        """
        import torch
        resolved = self.resolve_model_name(model_name)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.time()
        try:
            model = self.get_cross_encoder(model_name)
            load_time = time.time() - t0
            
            # Quick sanity test
            test_pairs = [["aircraft operations", "CAT III low visibility operations for commercial air transport"]]
            t1 = time.time()
            score = float(model.predict(test_pairs)[0])
            infer_time = time.time() - t1
            
            return {
                "success": True,
                "model_name": model_name or settings.RERANKER_MODEL_NAME,
                "resolved_model": resolved,
                "device": device,
                "cuda_available": torch.cuda.is_available(),
                "load_time_seconds": round(load_time, 3),
                "test_inference_seconds": round(infer_time, 4),
                "test_score": round(score, 4),
                "message": f"Reranker '{resolved}' is active and operational on {device.upper()}."
            }
        except Exception as e:
            return {
                "success": False,
                "model_name": model_name or settings.RERANKER_MODEL_NAME,
                "resolved_model": resolved,
                "device": device,
                "error": str(e),
                "message": f"Reranker initialization failed: {str(e)}"
            }

def get_reranker_service() -> RerankerService:
    """Convenience getter for singleton RerankerService."""
    return RerankerService.get_instance()

def rerank_candidate_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    top_k: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper function for reranking candidate chunks.
    """
    service = RerankerService.get_instance()
    return service.rerank_chunks(query=query, chunks=chunks, model_name=model_name, top_k=top_k)
