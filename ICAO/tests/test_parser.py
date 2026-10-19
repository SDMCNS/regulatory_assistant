"""Unit tests for PDF Parser."""

import pytest
from pathlib import Path
from icao_rag.parser import PDFParser
from icao_rag.config import ParserConfig


def test_parser_extracts_doc_9562():
    parser = PDFParser()
    pdf_path = Path("9562_cons_en.pdf")
    if not pdf_path.exists():
        pytest.skip("9562_cons_en.pdf not found")

    metadata, pages = parser.parse_document(pdf_path)

    assert metadata.doc_id == "doc_9562"
    assert "Airport Economics" in metadata.title
    assert metadata.total_pages == 146
    assert metadata.indexed_pages > 100
    assert len(pages) == 146

    # Verify content on page 21 (Chapter 1)
    page_21 = pages[20]
    assert page_21.page_number == 21
    assert "Chapter 1" in (page_21.detected_chapter or "")
    assert len(page_21.clean_text) > 100


def test_parser_extracts_doc_9750():
    parser = PDFParser()
    pdf_path = Path("9750_2ed_en.pdf")
    if not pdf_path.exists():
        pytest.skip("9750_2ed_en.pdf not found")

    metadata, pages = parser.parse_document(pdf_path)

    assert metadata.doc_id == "doc_9750"
    assert "Global Air Navigation" in metadata.title
    assert metadata.total_pages == 192
    assert metadata.indexed_pages > 150
