"""Configuration settings for the ICAO Document RAG Library and API."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
IMPORT_DIR = BASE_DIR / "import_pdfs"
STORAGE_DIR = BASE_DIR / "icao_rag" / "storage"
DEFAULT_CACHE_DIR = STORAGE_DIR / "index_cache"


@dataclass
class ParserConfig:
    """Configuration for PDF parsing and layout analysis."""
    extract_tables: bool = True
    clean_hyphenation: bool = True
    strip_running_headers: bool = True
    min_page_char_count: int = 40
    detect_sections: bool = True


@dataclass
class FilterConfig:
    """Configuration for filtering pages and text chunks."""
    exclude_cover_pages: bool = True
    exclude_front_matter: bool = False  # can be enabled to skip TOC, amendments
    exclude_blank_pages: bool = True
    min_chunk_length: int = 50
    max_chunk_length: int = 2500
    noise_patterns: List[str] = field(default_factory=lambda: [
        r"^\s*Table of Contents\s*$",
        r"^\s*\(?[ivxlcdm]+\)?\s*$",  # Lone roman numerals
        r"^\s*Page\s+\d+\s*$",
        r"^\s*\.{5,}\s*\d*\s*$",  # Dot leaders from TOC
    ])


@dataclass
class ChunkerConfig:
    """Configuration for hierarchical semantic chunking."""
    chunk_size: int = 800  # Target characters per chunk
    chunk_overlap: int = 150  # Overlap between consecutive chunks
    prepend_context: bool = True  # Prepend document & chapter context to embedding text
    respect_paragraphs: bool = True
    respect_headings: bool = True


@dataclass
class EmbedderConfig:
    """Configuration for vector embedding generation."""
    backend: str = "sentence_transformers"  # 'sentence_transformers', 'tfidf', 'gemini'
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 32
    normalize_embeddings: bool = True
    device: str = "cpu"  # 'cpu', 'cuda', or 'auto'


@dataclass
class SearchConfig:
    """Configuration for hybrid retrieval and search."""
    dense_weight: float = 0.65
    bm25_weight: float = 0.35
    rrf_k: int = 60
    default_top_k: int = 5
    snippet_window: int = 200
    highlight_terms: bool = True


@dataclass
class PipelineConfig:
    """Master configuration encompassing all components."""
    data_dir: Path = BASE_DIR
    import_dir: Path = IMPORT_DIR
    storage_dir: Path = DEFAULT_CACHE_DIR
    parser: ParserConfig = field(default_factory=ParserConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
