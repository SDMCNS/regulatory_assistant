import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
import numpy as np
import faiss

from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.core.config import settings

logger = logging.getLogger(__name__)


class LocalVectorIndex:
    """Native CPU local FAISS vector store handling segmented index partitions with dynamic dimension adaptation."""

    def __init__(self, index_dir: Path = settings.EMBEDDINGS_DIR, dimensions: int = settings.EMBEDDING_DIMENSIONS):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions
        self.indices: Dict[str, faiss.IndexFlatIP] = {}
        self.id_maps: Dict[str, List[str]] = {}

        self._initialize_indices()

    def _initialize_indices(self):
        for etype in EmbeddingType:
            etype_str = etype.value
            idx_file = self.index_dir / f"{etype_str.lower()}.index"
            map_file = self.index_dir / f"{etype_str.lower()}_map.json"

            if idx_file.exists() and map_file.exists():
                try:
                    loaded_index = faiss.read_index(str(idx_file))
                    with open(map_file, "r", encoding="utf-8") as f:
                        loaded_map = json.load(f)

                    self.indices[etype_str] = loaded_index
                    self.id_maps[etype_str] = loaded_map
                    logger.info(f"Loaded existing index for '{etype_str}' with {loaded_index.ntotal} vectors ({loaded_index.d}D).")
                except Exception as e:
                    logger.warning(f"Failed to load existing index for '{etype_str}', initializing fresh index: {e}")
                    self.indices[etype_str] = faiss.IndexFlatIP(self.dimensions)
                    self.id_maps[etype_str] = []
            else:
                self.indices[etype_str] = faiss.IndexFlatIP(self.dimensions)
                self.id_maps[etype_str] = []

    def add_records(self, records: List[EmbeddingRecord]):
        if not records:
            return

        grouped: Dict[str, Tuple[List[List[float]], List[str]]] = {}

        for r in records:
            etype = r.embedding_type.value if hasattr(r.embedding_type, "value") else str(r.embedding_type)
            grouped.setdefault(etype, ([], []))
            grouped[etype][0].append(r.vector)
            grouped[etype][1].append(r.fragment_id)

        for etype, (vectors, frag_ids) in grouped.items():
            if not vectors:
                continue

            vec_array = np.array(vectors, dtype=np.float32)
            if vec_array.ndim == 1:
                vec_array = np.expand_dims(vec_array, axis=0)

            actual_dim = vec_array.shape[1]

            # Initialize partitions that were not registered in EmbeddingType enum
            if etype not in self.indices:
                logger.info(f"Creating new FAISS IndexFlatIP for partition '{etype}' with {actual_dim}D.")
                self.indices[etype] = faiss.IndexFlatIP(actual_dim)
                self.id_maps[etype] = []

            expected_dim = self.indices[etype].d

            # Handle dimension mismatches dynamically
            if actual_dim != expected_dim:
                if self.indices[etype].ntotal == 0:
                    logger.warning(
                        f"Dimension mismatch for partition '{etype}': Model generated {actual_dim}D vectors, "
                        f"re-initializing empty index from {expected_dim}D to {actual_dim}D."
                    )
                    self.indices[etype] = faiss.IndexFlatIP(actual_dim)
                else:
                    raise ValueError(
                        f"Critical dimension mismatch for partition '{etype}': Model returned {actual_dim}D, "
                        f"but existing FAISS index holds {self.indices[etype].ntotal} records at {expected_dim}D. "
                        f"Delete old index files under {self.index_dir} or switch model back to {expected_dim}D."
                    )

            # Normalize vectors for Cosine Similarity via Inner Product
            faiss.normalize_L2(vec_array)

            self.indices[etype].add(vec_array)
            self.id_maps[etype].extend(frag_ids)
            self._save_index(etype)

    def search(self, query_vector: List[float], embedding_type: EmbeddingType, top_k: int = 5) -> List[Tuple[str, float]]:
        etype = embedding_type.value if hasattr(embedding_type, "value") else str(embedding_type)

        if etype not in self.indices or self.indices[etype].ntotal == 0:
            return []

        vec = np.array([query_vector], dtype=np.float32)
        if vec.shape[1] != self.indices[etype].d:
            logger.error(
                f"Search query dimension ({vec.shape[1]}D) does not match index dimension ({self.indices[etype].d}D)."
            )
            return []

        faiss.normalize_L2(vec)
        scores, indices = self.indices[etype].search(vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and idx < len(self.id_maps[etype]):
                results.append((self.id_maps[etype][idx], float(score)))

        return results

    def _save_index(self, etype: str):
        idx_file = self.index_dir / f"{etype.lower()}.index"
        map_file = self.index_dir / f"{etype.lower()}_map.json"

        faiss.write_index(self.indices[etype], str(idx_file))
        with open(map_file, "w", encoding="utf-8") as f:
            json.dump(self.id_maps[etype], f)

    def save(self):
        """Explicit global flush to save all active index partitions."""
        for etype in self.indices.keys():
            self._save_index(etype)
