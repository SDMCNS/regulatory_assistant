"""
User-Supplied Documents Ingestion Package.
"""

from .detector import DocFormat, detect_document_format
from .extractor import extract_user_document
from .comparator import search_and_compare_document
from .pipeline import ingest_user_document

__all__ = [
    "DocFormat",
    "detect_document_format",
    "extract_user_document",
    "search_and_compare_document",
    "ingest_user_document",
]
