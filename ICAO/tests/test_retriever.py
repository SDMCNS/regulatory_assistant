"""Unit tests for VectorStore, BM25, and HybridSearchEngine."""

import numpy as np
from icao_rag.bm25 import BM25Index
from icao_rag.embedder import TfidfEmbedder
from icao_rag.models import Chunk, ChunkMetadata, DocumentMetadata, SearchFilter, SearchRequest
from icao_rag.retriever import HybridSearchEngine
from icao_rag.vector_store import VectorStore


def test_bm25_exact_match():
    bm25 = BM25Index()
    docs = [
        "ICAO Doc 9562 details airport charges and Article 15.",
        "Doc 9750 defines the Global Air Navigation Plan for CNS/ATM.",
        "Airport concession fees from retail, parking, and catering."
    ]
    bm25.index(docs)

    scores = bm25.get_scores("CNS/ATM")
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]

    scores_art15 = bm25.get_scores("Article 15")
    assert scores_art15[0] > scores_art15[1]


def test_hybrid_search():
    embedder = TfidfEmbedder(dimension=32)
    store = VectorStore()

    texts = [
        "Principles of cost recovery for airport landing and passenger charges.",
        "Global CNS/ATM air navigation transition strategies and GNSS.",
        "Setting concession fees and commercial non-aeronautical development."
    ]
    embs = embedder.embed_texts(texts)

    chunks = []
    for i, t in enumerate(texts):
        doc_id = "doc_9562" if i != 1 else "doc_9750"
        meta = ChunkMetadata(
            chunk_id=f"c_{i}",
            doc_id=doc_id,
            doc_title=f"Title {doc_id}",
            filename=f"{doc_id}.pdf",
            page_number=10 * (i + 1),
            page_type="content",
            chapter=f"Chapter {i+1}"
        )
        chunks.append(Chunk(chunk_id=f"c_{i}", metadata=meta, text=t))

    store.add(chunks, embs)

    engine = HybridSearchEngine(vector_store=store, embedder=embedder)

    # Search for navigation
    req = SearchRequest(query="CNS/ATM satellite navigation", top_k=2)
    resp = engine.search(req)

    assert len(resp.results) > 0
    # Top result should be the CNS/ATM chunk
    assert resp.results[0].chunk_id == "c_1"
    assert "<mark>" in resp.results[0].snippet or "navigation" in resp.results[0].snippet.lower()

    # Search with document filter
    req_filtered = SearchRequest(
        query="charges",
        top_k=2,
        filter=SearchFilter(doc_id="doc_9562")
    )
    resp_filtered = engine.search(req_filtered)
    assert all(r.doc_id == "doc_9562" for r in resp_filtered.results)
