"""
User-Supplied Documents Ingestion Package.
"""

from .detector import DocFormat, detect_document_format
from .extractor import extract_user_document
from .comparator import search_and_compare_document
from .pipeline import ingest_user_document
from .word_parser import (
    extract_word_doc,
    extract_word_docx,
    is_word_binary_doc,
    is_word_docx,
)

__all__ = [
    "DocFormat",
    "detect_document_format",
    "extract_user_document",
    "search_and_compare_document",
    "ingest_user_document",
    "extract_word_doc",
    "extract_word_docx",
    "is_word_binary_doc",
    "is_word_docx",
]

