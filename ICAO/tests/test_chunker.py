"""Unit tests for Hierarchical Chunker."""

from icao_rag.chunker import HierarchicalChunker
from icao_rag.config import ChunkerConfig
from icao_rag.models import DocumentMetadata, PageData


def test_hierarchical_chunking_with_context():
    config = ChunkerConfig(chunk_size=300, chunk_overlap=50, prepend_context=True)
    chunker = HierarchicalChunker(config)

    doc_meta = DocumentMetadata(
        doc_id="doc_9562",
        filename="9562_cons_en.pdf",
        title="ICAO Doc 9562: Airport Economics Manual",
        total_pages=146,
        indexed_pages=135
    )

    page = PageData(
        page_number=21,
        raw_text="",
        clean_text=(
            "The cost basis for airport charges should be established in accordance with ICAO principles.\n\n"
            "Charges must be non-discriminatory and directly related to the costs of providing services.\n\n"
            "States should encourage consultation between airport operators and airport users."
        ),
        page_type="content",
        detected_chapter="Chapter 1. ICAO policies on charges",
        detected_sections=["1.1 Cost Basis"]
    )

    chunks = chunker.chunk_document(doc_meta, [page])
    assert len(chunks) >= 1

    first_chunk = chunks[0]
    assert first_chunk.metadata.doc_id == "doc_9562"
    assert first_chunk.metadata.page_number == 21
    assert "Doc 9562" in first_chunk.context_prefix
    assert "Chapter 1" in first_chunk.context_prefix
    assert "Document:" in first_chunk.embedding_text
    assert "The cost basis" in first_chunk.text
