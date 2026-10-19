"""Persistent vector store with cosine similarity retrieval and metadata filtering."""

import json
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np

from .models import Chunk, DocumentMetadata, SearchFilter
from .filter import FilterEngine


class VectorStore:
    """Stores embeddings, chunks, and documents with fast NumPy retrieval and disk persistence."""

    def __init__(self, filter_engine: Optional[FilterEngine] = None):
        self.filter_engine = filter_engine or FilterEngine()
        self.chunks: List[Chunk] = []
        self.embeddings: Optional[np.ndarray] = None
        self.documents: List[DocumentMetadata] = []

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def dimension(self) -> int:
        return self.embeddings.shape[1] if self.embeddings is not None and len(self.embeddings) > 0 else 0

    def add(
        self,
        chunks: List[Chunk],
        embeddings: np.ndarray,
        doc_meta: Optional[DocumentMetadata] = None
    ):
        """Append chunks and their embeddings to the store."""
        if len(chunks) == 0:
            return

        if doc_meta:
            # Update or append document metadata
            existing_idx = next((i for i, d in enumerate(self.documents) if d.doc_id == doc_meta.doc_id), None)
            if existing_idx is not None:
                self.documents[existing_idx] = doc_meta
            else:
                self.documents.append(doc_meta)

        self.chunks.extend(chunks)

        if self.embeddings is None or len(self.embeddings) == 0:
            self.embeddings = embeddings.astype(np.float32)
        else:
            self.embeddings = np.vstack([self.embeddings, embeddings.astype(np.float32)])

    def remove_document(self, doc_id: str):
        """Remove all chunks, embeddings, and metadata associated with a document ID."""
        keep_indices = [i for i, c in enumerate(self.chunks) if c.metadata.doc_id != doc_id]
        if len(keep_indices) == len(self.chunks):
            return

        self.chunks = [self.chunks[i] for i in keep_indices]
        if self.embeddings is not None and len(self.embeddings) > 0:
            if keep_indices:
                self.embeddings = self.embeddings[keep_indices]
            else:
                self.embeddings = None

        self.documents = [d for d in self.documents if d.doc_id != doc_id]

    def search_dense(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        search_filter: Optional[SearchFilter] = None
    ) -> List[Tuple[int, float]]:
        """Compute cosine similarity of query against stored embeddings, returning (idx, score)."""
        if self.embeddings is None or len(self.embeddings) == 0:
            return []

        # Query vector is assumed normalized; compute dot products
        scores = np.dot(self.embeddings, query_vector)

        # Apply metadata filtering mask
        valid_indices = []
        for idx, chunk in enumerate(self.chunks):
            if self.filter_engine.matches_search_filter(chunk, search_filter):
                valid_indices.append(idx)

        if not valid_indices:
            return []

        # Sort filtered indices by score descending
        valid_scores = scores[valid_indices]
        top_local_order = np.argsort(valid_scores)[::-1][:top_k]

        return [(valid_indices[i], float(valid_scores[i])) for i in top_local_order]

    def save(self, storage_dir: str | Path):
        """Persist vector store to disk."""
        path = Path(storage_dir)
        path.mkdir(parents=True, exist_ok=True)

        if self.embeddings is not None:
            np.save(path / "embeddings.npy", self.embeddings)

        chunks_data = [chunk.model_dump() for chunk in self.chunks]
        with open(path / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks_data, f, ensure_ascii=False)

        docs_data = [doc.model_dump() for doc in self.documents]
        with open(path / "documents.json", "w", encoding="utf-8") as f:
            json.dump(docs_data, f, ensure_ascii=False, indent=2)

    def load(self, storage_dir: str | Path) -> bool:
        """Load vector store from disk. Returns True if successfully loaded."""
        path = Path(storage_dir)
        emb_file = path / "embeddings.npy"
        chunk_file = path / "chunks.json"
        doc_file = path / "documents.json"

        if not (emb_file.exists() and chunk_file.exists()):
            return False

        try:
            self.embeddings = np.load(emb_file)

            with open(chunk_file, "r", encoding="utf-8") as f:
                raw_chunks = json.load(f)
                self.chunks = [Chunk(**c) for c in raw_chunks]

            if doc_file.exists():
                with open(doc_file, "r", encoding="utf-8") as f:
                    raw_docs = json.load(f)
                    self.documents = [DocumentMetadata(**d) for d in raw_docs]

            return True
        except Exception:
            return False
