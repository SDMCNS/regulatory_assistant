"""
Skybrary Bookshelf Ingestion & Chunking Library.

Provides reusable components for:
- PDF text extraction with PyMuPDF & optional OCR (SkybraryExtractor)
- Multi-key metadata linking with skybrary.db (SkybraryDBLinker)
- Regulatory boilerplate and furniture cleaning (clean_page_furniture, strip_document_furniture)
- Page-aware semantic chunking with embedding text generation (SkybraryChunker)
- Storage adapters for JSON and SQLite (save_to_sqlite, write_document_json)
- End-to-end pipeline execution (SkybraryPipeline)
"""

from .chunker import ChunkRecord, DocumentMetadata, SkybraryChunker
from .db_linker import SkybraryDBLinker
from .extractor import ExtractionResult, SkybraryExtractor
from .furniture import clean_page_furniture, is_furniture_line, strip_document_furniture
from .pipeline import SkybraryPipeline
from .storage import save_to_sqlite, write_batch_manifest, write_document_json

__all__ = [
    "SkybraryExtractor",
    "ExtractionResult",
    "SkybraryDBLinker",
    "clean_page_furniture",
    "is_furniture_line",
    "strip_document_furniture",
    "SkybraryChunker",
    "DocumentMetadata",
    "ChunkRecord",
    "save_to_sqlite",
    "write_document_json",
    "write_batch_manifest",
    "SkybraryPipeline",
]
