"""Semantic and hierarchical chunking engine for structured ICAO documents."""

import re
from typing import List, Optional, Tuple
from .config import ChunkerConfig
from .filter import FilterEngine
from .models import Chunk, ChunkMetadata, DocumentMetadata, PageData


class HierarchicalChunker:
    """Chunks documents into semantic blocks with contextual metadata prefixes."""

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        filter_engine: Optional[FilterEngine] = None
    ):
        self.config = config or ChunkerConfig()
        self.filter_engine = filter_engine or FilterEngine()

    def chunk_document(
        self,
        doc_meta: DocumentMetadata,
        pages: List[PageData]
    ) -> List[Chunk]:
        """Convert a document's pages into a sequence of contextual chunks."""
        chunks: List[Chunk] = []
        chunk_idx = 0

        for page in pages:
            if not page.clean_text or len(page.clean_text) < 20:
                continue

            page_chunks = self._chunk_page(
                doc_meta=doc_meta,
                page=page,
                start_index=chunk_idx
            )
            chunks.extend(page_chunks)
            chunk_idx += len(page_chunks)

        return chunks

    def _chunk_page(
        self,
        doc_meta: DocumentMetadata,
        page: PageData,
        start_index: int
    ) -> List[Chunk]:
        """Split a single page into overlapping semantic chunks with context headers."""
        text = page.clean_text
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not paragraphs:
            return []

        # Break any oversized paragraphs into sentence groups
        normalized_units: List[str] = []
        for p in paragraphs:
            if len(p) <= self.config.chunk_size:
                normalized_units.append(p)
            else:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                current_unit: List[str] = []
                current_unit_len = 0
                for sent in sentences:
                    if current_unit_len + len(sent) > self.config.chunk_size and current_unit:
                        normalized_units.append(" ".join(current_unit))
                        current_unit = [sent]
                        current_unit_len = len(sent)
                    else:
                        current_unit.append(sent)
                        current_unit_len += len(sent) + 1
                if current_unit:
                    normalized_units.append(" ".join(current_unit))

        # Now group normalized units into target chunk sizes with overlap
        raw_chunks: List[Tuple[str, int, int]] = []
        current_block: List[str] = []
        current_len = 0
        char_offset = 0

        for unit in normalized_units:
            unit_len = len(unit)
            if current_len + unit_len > self.config.chunk_size and current_block:
                block_text = "\n\n".join(current_block)
                raw_chunks.append((block_text, char_offset, char_offset + len(block_text)))

                # Overlap logic
                if self.config.chunk_overlap > 0 and len(current_block) > 1:
                    last_unit = current_block[-1]
                    current_block = [last_unit]
                    current_len = len(last_unit)
                    char_offset += len(block_text) - len(last_unit)
                else:
                    current_block = []
                    current_len = 0
                    char_offset += len(block_text)

            current_block.append(unit)
            current_len += unit_len + 2

        if current_block:
            block_text = "\n\n".join(current_block)
            raw_chunks.append((block_text, char_offset, char_offset + len(block_text)))

        # Build Chunk objects
        results: List[Chunk] = []
        for block, start, end in raw_chunks:
            clean = self.filter_engine.clean_chunk_text(block)
            if self.filter_engine.is_valid_chunk(clean):
                chunk = self._build_chunk(
                    doc_meta=doc_meta,
                    page=page,
                    chunk_text=clean,
                    index=start_index + len(results),
                    char_start=start,
                    char_end=end
                )
                results.append(chunk)

        return results

    def _build_chunk(
        self,
        doc_meta: DocumentMetadata,
        page: PageData,
        chunk_text: str,
        index: int,
        char_start: int,
        char_end: int
    ) -> Chunk:
        """Create a Chunk with structured metadata and contextual prefix."""
        chunk_id = f"{doc_meta.doc_id}_p{page.page_number}_c{index}"
        section = page.detected_sections[0] if page.detected_sections else None

        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            doc_id=doc_meta.doc_id,
            doc_title=doc_meta.title,
            filename=doc_meta.filename,
            page_number=page.page_number,
            page_type=page.page_type,
            chapter=page.detected_chapter,
            section=section,
            chunk_index_in_doc=index,
            char_start=char_start,
            char_end=char_end
        )

        prefix_parts = [f"Document: {doc_meta.title}"]
        if page.detected_chapter:
            prefix_parts.append(f"Chapter: {page.detected_chapter}")
        if section:
            prefix_parts.append(f"Section: {section}")
        prefix_parts.append(f"Page: {page.page_number}")

        context_prefix = "[" + " | ".join(prefix_parts) + "]"

        return Chunk(
            chunk_id=chunk_id,
            metadata=metadata,
            text=chunk_text,
            context_prefix=context_prefix if self.config.prepend_context else ""
        )
