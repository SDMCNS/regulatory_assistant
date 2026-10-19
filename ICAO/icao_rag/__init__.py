"""ICAO Document RAG Library: Parse, Filter, Chunk, Embed, and Search ICAO Manuals."""

from .config import (
    ChunkerConfig,
    EmbedderConfig,
    FilterConfig,
    ParserConfig,
    PipelineConfig,
    SearchConfig,
)
from .models import (
    Chunk,
    ChunkMetadata,
    DocumentMetadata,
    ImportFileInfo,
    ImportStatusResponse,
    IndexingStats,
    PageData,
    SearchFilter,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SyncImportResponse,
)
from .parser import PDFParser
from .filter import FilterEngine
from .chunker import HierarchicalChunker
from .embedder import BaseEmbedder, SentenceTransformerEmbedder, TfidfEmbedder, get_embedder
from .bm25 import BM25Index
from .vector_store import VectorStore
from .retriever import HybridSearchEngine
from .pipeline import ICAOPipeline

__version__ = "1.0.0"

__all__ = [
    "ICAOPipeline",
    "PDFParser",
    "FilterEngine",
    "HierarchicalChunker",
    "BaseEmbedder",
    "SentenceTransformerEmbedder",
    "TfidfEmbedder",
    "get_embedder",
    "BM25Index",
    "VectorStore",
    "HybridSearchEngine",
    "PipelineConfig",
    "ParserConfig",
    "FilterConfig",
    "ChunkerConfig",
    "EmbedderConfig",
    "SearchConfig",
    "DocumentMetadata",
    "PageData",
    "Chunk",
    "ChunkMetadata",
    "SearchFilter",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "IndexingStats",
]
