"""Embedding backends for semantic vector representation."""

import os
from abc import ABC, abstractmethod
from typing import List, Optional
import numpy as np

from .config import EmbedderConfig


class BaseEmbedder(ABC):
    """Abstract interface for text embedding models."""

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embed a list of text strings into a 2D float32 numpy array (N, dim)."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string into a 1D float32 numpy array (dim,)."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vector."""
        pass


class SentenceTransformerEmbedder(BaseEmbedder):
    """Dense neural embedding model using SentenceTransformers (default all-MiniLM-L6-v2)."""

    def __init__(self, config: Optional[EmbedderConfig] = None):
        self.config = config or EmbedderConfig()
        from sentence_transformers import SentenceTransformer

        # Load model
        self.model = SentenceTransformer(
            self.config.model_name,
            device=self.config.device
        )
        if hasattr(self.model, "get_embedding_dimension"):
            self._dimension = self.model.get_embedding_dimension()
        else:
            self._dimension = self.model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            show_progress_bar=False,
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]


class TfidfEmbedder(BaseEmbedder):
    """Fallback lightweight embedder using HashingVectorizer for fixed-dimension normalized vectors."""

    def __init__(self, dimension: int = 128):
        from sklearn.feature_extraction.text import HashingVectorizer

        self._dimension = dimension
        self.vectorizer = HashingVectorizer(
            n_features=dimension,
            norm="l2",
            alternate_sign=True,
            token_pattern=r"\b\w+\b"
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        vecs = self.vectorizer.transform(texts).toarray()
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vecs / norms).astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]


def get_embedder(config: Optional[EmbedderConfig] = None) -> BaseEmbedder:
    """Factory function to instantiate the configured embedder."""
    cfg = config or EmbedderConfig()
    backend = cfg.backend.lower()

    if backend == "sentence_transformers":
        return SentenceTransformerEmbedder(cfg)
    elif backend == "tfidf":
        return TfidfEmbedder()
    else:
        # Default fallback
        try:
            return SentenceTransformerEmbedder(cfg)
        except Exception:
            return TfidfEmbedder()
