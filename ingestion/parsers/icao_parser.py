"""
ICAO Technical Documentation Parser and Chunk Converter.

Leverages PyMuPDF block layout analysis, boilerplate and noise suppression,
and hierarchical semantic chunking from the ICAO RAG library, and produces
canonical SQLite document and chunk dictionaries aligned with the Regs platform.
"""

import sys
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ICAO.icao_rag.parser import PDFParser
from ICAO.icao_rag.filter import FilterEngine
from ICAO.icao_rag.chunker import HierarchicalChunker
from ICAO.icao_rag.config import ParserConfig, FilterConfig, ChunkerConfig


def extract_section_numbers(text: str) -> List[str]:
    """Extract section numbering like 1.2, 4.2.1, or Appendix A from text."""
    matches = re.findall(r'\b(?:\d+\.\d+(?:\.\d+)*|(?:Appendix|Attachment)\s+[A-Z\d]+)\b', text)
    seen = set()
    ordered = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def parse_icao_pdf(
    pdf_path: Path,
    chunk_size: int = 1000,
    chunk_overlap: int = 150
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parses a single ICAO PDF document into canonical (doc_dict, chunks_list)
    ready for insertion into the SQLite regulations database.
    """
    parser_cfg = ParserConfig()
    filter_cfg = FilterConfig()
    chunker_cfg = ChunkerConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    parser = PDFParser(parser_cfg)
    filter_engine = FilterEngine(filter_cfg)
    chunker = HierarchicalChunker(chunker_cfg, filter_engine)

    # 1. Parse document structure and pages
    doc_meta, pages = parser.parse_document(pdf_path)

    # 2. Filter blank and noise pages
    filtered_pages = filter_engine.filter_pages(pages)

    # 3. Chunk content pages
    raw_chunks = chunker.chunk_document(doc_meta, filtered_pages)

    # 4. Assemble canonical Document dictionary
    doc_id = doc_meta.doc_id
    doc_title = doc_meta.title

    doc_metadata = {
        "source": "ICAO PDF",
        "origin": "icao",
        "authority": "ICAO",
        "document_id": doc_id,
        "title": doc_title,
        "filename": doc_meta.filename,
        "edition": doc_meta.edition or "",
        "total_pages": doc_meta.total_pages,
        "indexed_pages": len(filtered_pages),
        "file_size_bytes": doc_meta.file_size_bytes,
        "chunk_count": len(raw_chunks)
    }

    doc_dict = {
        "document_id": doc_id,
        "title": doc_title,
        "language": "en",
        "date": doc_meta.edition or "2020",
        "source": "ICAO PDF",
        "metadata_json": json.dumps(doc_metadata, ensure_ascii=False),
        "is_active": 1,
        "superseded_by": None,
        "deactivation_reason": None
    }

    # 5. Assemble canonical Chunks dictionaries
    chunks: List[Dict[str, Any]] = []

    for idx, c in enumerate(raw_chunks):
        c_meta = c.metadata
        page_num = c_meta.page_number
        chapter = c_meta.chapter or ""
        section = c_meta.section or ""
        body_text = c.text.strip()

        # Build clean hierarchical section path
        section_path = [doc_title]
        if chapter and chapter != doc_title:
            section_path.append(chapter)
        if section and section != chapter:
            section_path.append(section)

        # Detect section numbers
        sec_numbers = extract_section_numbers(section)
        if not sec_numbers and chapter:
            sec_numbers = extract_section_numbers(chapter)

        # Build embedding text with clear hierarchical context prefix
        emb_parts = [f"Document: {doc_title}"]
        if chapter:
            emb_parts.append(f"Chapter: {chapter}")
        if section:
            emb_parts.append(f"Section: {section}")
        emb_parts.append(f"Page: {page_num}")

        context_header = " | ".join(emb_parts)
        embedding_text = f"[{context_header}]\n\n{body_text}"

        chunk_id = f"{doc_id}:p{page_num}:c{idx + 1}"

        chunk_meta = {
            "source": "ICAO PDF",
            "origin": "icao",
            "authority": "ICAO",
            "document_id": doc_id,
            "document_title": doc_title,
            "filename": doc_meta.filename,
            "page_number": page_num,
            "page_type": c_meta.page_type,
            "chapter": chapter,
            "section": section,
            "edition": doc_meta.edition or "",
            "char_start": c_meta.char_start,
            "char_end": c_meta.char_end
        }

        chunk_record = {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "chunk_type": "section" if section else ("chapter" if chapter else "text"),
            "section_path": json.dumps(section_path, ensure_ascii=False),
            "section_numbers": json.dumps(sec_numbers, ensure_ascii=False),
            "source_text": body_text,
            "embedding_text": embedding_text,
            "parent_chunk_id": doc_id,
            "previous_chunk_id": None,
            "next_chunk_id": None,
            "structure_json": json.dumps({
                "document_id": doc_id,
                "chapter": chapter,
                "section": section,
                "page_number": page_num
            }, ensure_ascii=False),
            "references_json": "[]",
            "metadata_json": json.dumps(chunk_meta, ensure_ascii=False),
            "is_active": 1
        }
        chunks.append(chunk_record)

    # 6. Sequential linking for adjacent context browsing
    for i, chunk in enumerate(chunks):
        chunk["previous_chunk_id"] = chunks[i - 1]["chunk_id"] if i > 0 else None
        chunk["next_chunk_id"] = chunks[i + 1]["chunk_id"] if i < len(chunks) - 1 else None

    return doc_dict, chunks
