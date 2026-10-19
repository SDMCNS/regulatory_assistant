"""Filtering engine for pages, chunks, and metadata in ICAO documents."""

import re
from typing import Callable, List, Optional
from .config import FilterConfig
from .models import Chunk, PageData, SearchFilter


class FilterEngine:
    """Provides page-level, text-level, and search-time filtering capabilities."""

    def __init__(self, config: Optional[FilterConfig] = None):
        self.config = config or FilterConfig()
        self._compiled_noise_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.config.noise_patterns
        ]

    def filter_pages(
        self,
        pages: List[PageData],
        custom_predicate: Optional[Callable[[PageData], bool]] = None
    ) -> List[PageData]:
        """Filter a list of extracted pages based on configuration and optional predicate."""
        filtered = []
        for p in pages:
            # Blank check
            if self.config.exclude_blank_pages and (p.page_type == "blank" or len(p.clean_text) < 10):
                continue

            # Cover check
            if self.config.exclude_cover_pages and p.page_type == "cover":
                continue

            # Front matter check
            if self.config.exclude_front_matter and p.page_type == "front_matter":
                continue

            # Custom predicate
            if custom_predicate and not custom_predicate(p):
                continue

            filtered.append(p)

        return filtered

    def clean_chunk_text(self, text: str) -> str:
        """Strip noise, dot leaders, lone page markers from chunk text."""
        cleaned = text
        for pat in self._compiled_noise_patterns:
            cleaned = pat.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def is_valid_chunk(self, chunk_text: str) -> bool:
        """Check if chunk text satisfies quality thresholds."""
        length = len(chunk_text)
        if length < self.config.min_chunk_length:
            return False
        if length > self.config.max_chunk_length:
            return False

        # Reject chunks that are mostly dots (TOC entries)
        dot_ratio = chunk_text.count(".") / max(1, length)
        if dot_ratio > 0.25:
            return False

        # Must have at least a few alphabetic words
        words = [w for w in chunk_text.split() if any(c.isalpha() for c in w)]
        if len(words) < 5:
            return False

        return True

    def matches_search_filter(self, chunk: Chunk, search_filter: Optional[SearchFilter]) -> bool:
        """Evaluate if a chunk satisfies search criteria."""
        if not search_filter:
            return True

        meta = chunk.metadata

        # Document ID filter
        if search_filter.doc_id:
            if meta.doc_id.lower() != search_filter.doc_id.lower():
                return False

        # Page range filter
        if search_filter.min_page is not None and meta.page_number < search_filter.min_page:
            return False
        if search_filter.max_page is not None and meta.page_number > search_filter.max_page:
            return False

        # Chapter keyword filter
        if search_filter.chapter_keyword:
            kw = search_filter.chapter_keyword.lower()
            if not meta.chapter or kw not in meta.chapter.lower():
                return False

        # Front matter exclusion
        if search_filter.exclude_front_matter and meta.page_type in ("front_matter", "cover"):
            return False

        return True
