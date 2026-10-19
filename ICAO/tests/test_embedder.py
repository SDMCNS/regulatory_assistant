"""Unit tests for Embedder backends."""

import numpy as np
from icao_rag.embedder import SentenceTransformerEmbedder, TfidfEmbedder, get_embedder
from icao_rag.config import EmbedderConfig


def test_tfidf_embedder():
    embedder = TfidfEmbedder(dimension=64)
    texts = [
        "ICAO Doc 9562 deals with airport economics and charges.",
        "CNS/ATM systems provide global satellite air navigation.",
        "Concession revenues include duty-free shops and parking."
    ]
    embs = embedder.embed_texts(texts)
    assert embs.shape == (3, 64)

    q_emb = embedder.embed_query("airport charges")
    assert q_emb.shape == (64,)
    # Verify cosine norm is approx 1
    norm = np.linalg.norm(q_emb)
    assert np.isclose(norm, 1.0, atol=1e-3)


def test_sentence_transformer_embedder():
    embedder = SentenceTransformerEmbedder()
    assert embedder.dimension == 384

    texts = ["Airport landing fees.", "Satellite navigation."]
    embs = embedder.embed_texts(texts)
    assert embs.shape == (2, 384)

    # Dot product between normalized vectors is cosine similarity
    similarity = np.dot(embs[0], embs[1])
    assert -1.0 <= similarity <= 1.0
