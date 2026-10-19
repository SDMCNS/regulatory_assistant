"""Hybrid search engine combining dense semantic retrieval and sparse BM25 ranking."""

import re
import time
from typing import Dict, List, Optional, Tuple
import numpy as np

from .bm25 import BM25Index, default_tokenize
from .config import SearchConfig
from .embedder import BaseEmbedder
from .filter import FilterEngine
from .models import Chunk, SearchFilter, SearchRequest, SearchResponse, SearchResultItem
from .vector_store import VectorStore


class HybridSearchEngine:
    """Combines dense semantic vectors and sparse BM25 scores with metadata filtering and highlighting."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: BaseEmbedder,
        config: Optional[SearchConfig] = None,
        filter_engine: Optional[FilterEngine] = None
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.config = config or SearchConfig()
        self.filter_engine = filter_engine or FilterEngine()

        self.bm25_index = BM25Index()
        self._rebuild_bm25_if_needed()

    def _rebuild_bm25_if_needed(self):
        """Build or refresh BM25 inverted index from current vector store chunks."""
        if self.vector_store.total_chunks > 0 and self.bm25_index.corpus_size != self.vector_store.total_chunks:
            # We index both context prefix and chunk text
            texts = [c.embedding_text for c in self.vector_store.chunks]
            self.bm25_index.index(texts)

    def search(self, request: SearchRequest) -> SearchResponse:
        """Perform hybrid search matching the user request."""
        start_time = time.perf_counter()
        self._rebuild_bm25_if_needed()

        if self.vector_store.total_chunks == 0:
            return SearchResponse(
                query=request.query,
                total_results=0,
                results=[],
                time_taken_ms=0.0
            )

        top_k = request.top_k
        dense_w = request.dense_weight
        bm25_w = request.bm25_weight
        search_filter = request.filter

        # 1. Dense retrieval
        query_vec = self.embedder.embed_query(request.query)
        # Fetch candidate pool (up to 3x top_k)
        candidate_k = min(self.vector_store.total_chunks, max(50, top_k * 4))
        dense_hits = self.vector_store.search_dense(
            query_vector=query_vec,
            top_k=candidate_k,
            search_filter=search_filter
        )
        dense_rank_map: Dict[int, Tuple[int, float]] = {
            idx: (rank + 1, score) for rank, (idx, score) in enumerate(dense_hits)
        }

        # 2. BM25 retrieval
        bm25_scores = self.bm25_index.get_scores(request.query)
        # Filter and rank BM25 hits
        bm25_valid = []
        for idx, score in enumerate(bm25_scores):
            if score > 0.0:
                chunk = self.vector_store.chunks[idx]
                if self.filter_engine.matches_search_filter(chunk, search_filter):
                    bm25_valid.append((idx, score))

        bm25_valid.sort(key=lambda x: x[1], reverse=True)
        bm25_hits = bm25_valid[:candidate_k]
        bm25_rank_map: Dict[int, Tuple[int, float]] = {
            idx: (rank + 1, score) for rank, (idx, score) in enumerate(bm25_hits)
        }

        # 3. Reciprocal Rank Fusion (RRF) & score normalization
        all_candidate_indices = set(dense_rank_map.keys()) | set(bm25_rank_map.keys())
        rrf_k = self.config.rrf_k

        max_bm25 = max([s for _, s in bm25_hits], default=1.0)
        if max_bm25 <= 0:
            max_bm25 = 1.0

        fused_items: List[Tuple[int, float, Optional[float], Optional[float]]] = []

        for idx in all_candidate_indices:
            dense_rank, dense_raw_score = dense_rank_map.get(idx, (9999, 0.0))
            bm25_rank, bm25_raw_score = bm25_rank_map.get(idx, (9999, 0.0))

            # RRF score
            rrf_score = 0.0
            if idx in dense_rank_map:
                rrf_score += dense_w * (1.0 / (rrf_k + dense_rank))
            if idx in bm25_rank_map:
                rrf_score += bm25_w * (1.0 / (rrf_k + bm25_rank))

            # Normalized combined score for UI readability (0.0 to 1.0 range)
            norm_dense = max(0.0, min(1.0, float(dense_raw_score)))
            norm_bm25 = max(0.0, min(1.0, float(bm25_raw_score / max_bm25)))
            combined_score = (dense_w * norm_dense + bm25_w * norm_bm25) / max(0.01, (dense_w + bm25_w))

            # Blend RRF with combined score for fine ranking
            final_score = rrf_score * 10.0 + combined_score

            fused_items.append((
                idx,
                final_score,
                float(dense_raw_score) if idx in dense_rank_map else None,
                float(bm25_raw_score) if idx in bm25_rank_map else None
            ))

        # Sort by final score descending
        fused_items.sort(key=lambda x: x[1], reverse=True)
        top_items = fused_items[:top_k]

        # 4. Generate results with snippets and highlights
        result_items: List[SearchResultItem] = []
        for idx, score, dense_sc, bm25_sc in top_items:
            chunk = self.vector_store.chunks[idx]
            snippet = self._generate_snippet(chunk.text, request.query)

            result_items.append(SearchResultItem(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.metadata.doc_id,
                doc_title=chunk.metadata.doc_title,
                filename=chunk.metadata.filename,
                page_number=chunk.metadata.page_number,
                chapter=chunk.metadata.chapter,
                section=chunk.metadata.section,
                score=round(score, 4),
                dense_score=round(dense_sc, 4) if dense_sc is not None else None,
                bm25_score=round(bm25_sc, 4) if bm25_sc is not None else None,
                text=chunk.text,
                snippet=snippet
            ))

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return SearchResponse(
            query=request.query,
            total_results=len(result_items),
            results=result_items,
            retrieval_mode=f"hybrid (dense_w={dense_w:.2f}, bm25_w={bm25_w:.2f})",
            time_taken_ms=round(elapsed_ms, 2)
        )

    def _generate_snippet(self, text: str, query: str) -> str:
        """Create a focused snippet containing the most query term matches with highlighting."""
        query_terms = default_tokenize(query)
        if not query_terms:
            return text[:self.config.snippet_window] + ("..." if len(text) > self.config.snippet_window else "")

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        best_sentence_idx = 0
        best_match_count = -1

        for idx, sent in enumerate(sentences):
            sent_lower = sent.lower()
            count = sum(1 for t in query_terms if t in sent_lower)
            if count > best_match_count:
                best_match_count = count
                best_sentence_idx = idx

        # Pick a window of sentences around the best match
        start_idx = max(0, best_sentence_idx - 1)
        end_idx = min(len(sentences), best_sentence_idx + 2)
        snippet_text = " ".join(sentences[start_idx:end_idx]).strip()

        # If too short, pad with more of the original text
        if len(snippet_text) < 120 and len(text) > len(snippet_text):
            snippet_text = text[:self.config.snippet_window]

        # Highlight query terms
        if self.config.highlight_terms:
            for term in set(query_terms):
                if len(term) >= 3:
                    snippet_text = re.sub(
                        rf"(?i)\b({re.escape(term)})\b",
                        r"<mark>\1</mark>",
                        snippet_text
                    )

        return snippet_text
