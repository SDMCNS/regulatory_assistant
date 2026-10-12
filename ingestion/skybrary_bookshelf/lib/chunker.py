"""
chunker.py - Page-Aware and Structure-Aware Chunker for Skybrary Publications.

Segments text into clean, contextualized regulatory chunks matching the project's
canonical chunk schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .furniture import strip_document_furniture


PAGE_DELIMITER_RE = re.compile(r"^---\s*PAGE\s+(\d+)\s*---$", re.MULTILINE)


@dataclass
class DocumentMetadata:
    document_id: str
    title: str
    language: str
    date: str
    source: str
    category: str
    author: str
    summary_url: str
    pdf_url: str
    pdf_filename: str
    url_file_element: str
    pages: int
    char_count: int
    word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    chunk_type: str
    section_path: List[str]
    section_numbers: List[str]
    source_text: str
    embedding_text: str
    parent_chunk_id: Optional[str]
    previous_chunk_id: Optional[str]
    next_chunk_id: Optional[str]
    structure: Dict[str, Any]
    references: List[str]
    metadata: Dict[str, Any]


class SkybraryChunker:
    """Configurable chunker for Skybrary documents."""

    def __init__(
        self,
        target_words: int = 350,
        max_words: int = 600,
        min_words_per_chunk: int = 30,
    ):
        self.target_words = target_words
        self.max_words = max_words
        self.min_words_per_chunk = min_words_per_chunk

    @staticmethod
    def parse_pages(raw_text: str) -> List[Tuple[int, str]]:
        """Splits raw text containing '--- PAGE X ---' into [(page_num, text), ...]."""
        splits = PAGE_DELIMITER_RE.split(raw_text)
        if len(splits) == 1:
            return [(1, raw_text.strip())]

        pages: List[Tuple[int, str]] = []
        for i in range(1, len(splits), 2):
            page_num = int(splits[i])
            content = splits[i + 1] if i + 1 < len(splits) else ""
            pages.append((page_num, content.strip()))
        return pages

    def chunk_document(
        self,
        pub_info: Dict[str, Any],
        raw_text: str,
        doc_id_prefix: str = "SKYBRARY",
    ) -> Tuple[DocumentMetadata, List[ChunkRecord]]:
        """Chunks an extracted Skybrary text document into structured records."""
        skybrary_id = pub_info.get("id")
        doc_id = f"{doc_id_prefix}_{skybrary_id}" if skybrary_id else f"{doc_id_prefix}_0"

        title = pub_info.get("title") or "Unknown Title"
        category = pub_info.get("category") or "Uncategorized"
        author = pub_info.get("author") or "Unknown"
        pub_date = pub_info.get("publication_date") or ""
        summary_url = pub_info.get("summary_url") or ""
        pdf_url = pub_info.get("pdf_url") or ""
        pdf_path = pub_info.get("pdf_path") or ""
        pdf_filename = Path(pdf_path).name if pdf_path else ""
        url_file_elem = pdf_url.rstrip("/").split("/")[-1] if pdf_url else ""

        # Step 1: Parse pages
        raw_pages = self.parse_pages(raw_text)

        # Step 2: Strip recurring furniture/headers/footers
        cleaned_pages = strip_document_furniture(raw_pages)

        total_chars = sum(len(txt) for _, txt in cleaned_pages)
        total_words = sum(len(txt.split()) for _, txt in cleaned_pages)

        doc_meta = DocumentMetadata(
            document_id=doc_id,
            title=title,
            language="en",
            date=pub_date,
            source="SKYBRARY",
            category=category,
            author=author,
            summary_url=summary_url,
            pdf_url=pdf_url,
            pdf_filename=pdf_filename,
            url_file_element=url_file_elem,
            pages=len(cleaned_pages),
            char_count=total_chars,
            word_count=total_words,
            metadata={
                "skybrary_id": skybrary_id,
                "llm_classification": pub_info.get("llm_classification"),
                "llm_score": pub_info.get("llm_score"),
            },
        )

        chunks: List[ChunkRecord] = []
        chunk_counter = 0

        for page_num, clean_content in cleaned_pages:
            if not clean_content.strip():
                continue

            # Split by double newlines into logical paragraphs
            paras = re.split(r"\n\s*\n+", clean_content)
            current_block: List[str] = []
            current_words = 0

            for p in paras:
                p_clean = " ".join(p.split())
                if not p_clean:
                    continue

                words_in_p = len(p_clean.split())

                if current_words + words_in_p > self.max_words and current_block:
                    chunk_counter += 1
                    chunks.append(
                        self._build_chunk(
                            doc_id=doc_id,
                            counter=chunk_counter,
                            title=title,
                            category=category,
                            author=author,
                            pub_date=pub_date,
                            page_num=page_num,
                            source_text="\n\n".join(current_block),
                            pub_info=pub_info,
                        )
                    )
                    current_block = [p_clean]
                    current_words = words_in_p
                else:
                    current_block.append(p_clean)
                    current_words += words_in_p

                    if current_words >= self.target_words:
                        chunk_counter += 1
                        chunks.append(
                            self._build_chunk(
                                doc_id=doc_id,
                                counter=chunk_counter,
                                title=title,
                                category=category,
                                author=author,
                                pub_date=pub_date,
                                page_num=page_num,
                                source_text="\n\n".join(current_block),
                                pub_info=pub_info,
                            )
                        )
                        current_block = []
                        current_words = 0

            if current_block:
                chunk_counter += 1
                chunks.append(
                    self._build_chunk(
                        doc_id=doc_id,
                        counter=chunk_counter,
                        title=title,
                        category=category,
                        author=author,
                        pub_date=pub_date,
                        page_num=page_num,
                        source_text="\n\n".join(current_block),
                        pub_info=pub_info,
                    )
                )

        # Merge tiny trailing orphan chunks (< min_words_per_chunk) with previous chunk if same page
        merged_chunks: List[ChunkRecord] = []
        for c in chunks:
            if (
                merged_chunks
                and c.metadata["word_count"] < self.min_words_per_chunk
                and merged_chunks[-1].metadata["page_end"] == c.metadata["page_start"]
            ):
                prev = merged_chunks[-1]
                prev.source_text += "\n\n" + c.source_text
                # Refresh embedding_text
                prev.embedding_text = self._build_embedding_text(
                    title, category, author, pub_date, prev.metadata["page_start"], prev.source_text
                )
                prev.metadata["word_count"] = len(prev.source_text.split())
                prev.metadata["char_count"] = len(prev.source_text)
            else:
                merged_chunks.append(c)

        # Re-number and link previous/next chunk IDs
        for i, c in enumerate(merged_chunks):
            c.previous_chunk_id = merged_chunks[i - 1].chunk_id if i > 0 else None
            c.next_chunk_id = merged_chunks[i + 1].chunk_id if i + 1 < len(merged_chunks) else None

        return doc_meta, merged_chunks

    @staticmethod
    def _build_embedding_text(
        title: str, category: str, author: str, pub_date: str, page_num: int, text: str
    ) -> str:
        header_parts = [f"Document: {title}"]
        sub = []
        if category and category != "Uncategorized":
            sub.append(f"Category: {category}")
        if author and author != "Unknown":
            sub.append(f"Author: {author}")
        if pub_date:
            sub.append(f"Date: {pub_date}")
        sub.append(f"Page: {page_num}")
        header_parts.append(" | ".join(sub))
        return f"{chr(10).join(header_parts)}\n\n{text}"

    def _build_chunk(
        self,
        doc_id: str,
        counter: int,
        title: str,
        category: str,
        author: str,
        pub_date: str,
        page_num: int,
        source_text: str,
        pub_info: Dict[str, Any],
    ) -> ChunkRecord:
        chunk_id = f"{doc_id}:P{page_num}:{counter}"
        embedding_text = self._build_embedding_text(title, category, author, pub_date, page_num, source_text)

        return ChunkRecord(
            chunk_id=chunk_id,
            document_id=doc_id,
            chunk_type="paragraph",
            section_path=[title, category, f"Page {page_num}"],
            section_numbers=[str(page_num)],
            source_text=source_text,
            embedding_text=embedding_text,
            parent_chunk_id=None,
            previous_chunk_id=None,
            next_chunk_id=None,
            structure={"node_type": "paragraph", "pages": [page_num]},
            references=[],
            metadata={
                "source": "SKYBRARY",
                "skybrary_id": pub_info.get("id"),
                "category": category,
                "author": author,
                "publication_date": pub_date,
                "summary_url": pub_info.get("summary_url"),
                "pdf_url": pub_info.get("pdf_url"),
                "page_start": page_num,
                "page_end": page_num,
                "word_count": len(source_text.split()),
                "char_count": len(source_text),
            },
        )
