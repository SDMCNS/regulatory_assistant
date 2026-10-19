"""Unit tests for FilterEngine."""

from icao_rag.filter import FilterEngine
from icao_rag.config import FilterConfig
from icao_rag.models import Chunk, ChunkMetadata, PageData, SearchFilter


def test_page_filtering():
    engine = FilterEngine(FilterConfig(exclude_blank_pages=True, exclude_cover_pages=True))
    pages = [
        PageData(page_number=1, raw_text="Cover Page", clean_text="Cover Page", page_type="cover"),
        PageData(page_number=2, raw_text="", clean_text="", page_type="blank"),
        PageData(page_number=15, raw_text="Valid airport content...", clean_text="Valid airport content...", page_type="content")
    ]

    filtered = engine.filter_pages(pages)
    assert len(filtered) == 1
    assert filtered[0].page_number == 15


def test_chunk_validation():
    engine = FilterEngine()
    assert engine.is_valid_chunk("This is a sufficiently long valid technical chunk discussing ICAO Annex 14.")
    # Too short
    assert not engine.is_valid_chunk("short")
    # Table of contents dot line
    assert not engine.is_valid_chunk("Chapter 1 ..................................................... 1-1")


def test_search_filter_matching():
    engine = FilterEngine()
    meta = ChunkMetadata(
        chunk_id="doc_9562_p21_c1",
        doc_id="doc_9562",
        doc_title="ICAO Doc 9562",
        filename="9562_cons_en.pdf",
        page_number=21,
        page_type="content",
        chapter="Chapter 1. Charges and policies"
    )
    chunk = Chunk(chunk_id=meta.chunk_id, metadata=meta, text="Sample text about airport rates")

    # Match doc_id
    assert engine.matches_search_filter(chunk, SearchFilter(doc_id="doc_9562"))
    assert not engine.matches_search_filter(chunk, SearchFilter(doc_id="doc_9750"))

    # Match page range
    assert engine.matches_search_filter(chunk, SearchFilter(min_page=10, max_page=30))
    assert not engine.matches_search_filter(chunk, SearchFilter(min_page=25))

    # Match chapter keyword
    assert engine.matches_search_filter(chunk, SearchFilter(chapter_keyword="charges"))
    assert not engine.matches_search_filter(chunk, SearchFilter(chapter_keyword="navigation"))
