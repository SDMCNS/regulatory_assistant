"""Pydantic and dataclass models for ICAO document representations and search."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata describing an ICAO document."""
    doc_id: str = Field(..., description="Unique document ID (e.g., 'doc_9562')")
    filename: str = Field(..., description="Original PDF filename")
    title: str = Field(..., description="Official document title")
    edition: Optional[str] = Field(None, description="Document edition or release info")
    total_pages: int = Field(..., description="Total pages in the PDF")
    indexed_pages: int = Field(0, description="Number of content pages indexed")
    file_size_bytes: int = Field(0, description="File size in bytes")
    file_mtime: Optional[float] = Field(None, description="File modification timestamp (epoch)")
    source_path: Optional[str] = Field(None, description="Path to source PDF file")


class PageData(BaseModel):
    """Data extracted from a single PDF page."""
    page_number: int = Field(..., description="1-indexed page number")
    raw_text: str = Field(..., description="Extracted raw text")
    clean_text: str = Field(..., description="Cleaned, filtered body text")
    page_type: str = Field("content", description="Category: 'cover', 'front_matter', 'content', 'blank'")
    running_header: Optional[str] = Field(None, description="Running chapter/section header if present")
    detected_chapter: Optional[str] = Field(None, description="Chapter title/number")
    detected_sections: List[str] = Field(default_factory=list, description="Section headings detected on this page")
    char_count: int = Field(0, description="Clean text character count")


class ChunkMetadata(BaseModel):
    """Metadata attached to each text chunk for filtering and citation."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    doc_id: str = Field(..., description="Source document ID")
    doc_title: str = Field(..., description="Source document title")
    filename: str = Field(..., description="Source PDF filename")
    page_number: int = Field(..., description="1-indexed page number in the PDF")
    page_type: str = Field("content", description="Page category")
    chapter: Optional[str] = Field(None, description="Chapter context")
    section: Optional[str] = Field(None, description="Specific section heading")
    chunk_index_in_doc: int = Field(0, description="Ordinal position in document")
    char_start: int = Field(0, description="Start character offset in page")
    char_end: int = Field(0, description="End character offset in page")


class Chunk(BaseModel):
    """A semantic chunk of text with context prefix and metadata."""
    chunk_id: str
    metadata: ChunkMetadata
    text: str = Field(..., description="Raw text of the chunk")
    context_prefix: str = Field("", description="Hierarchical context prepended for embedding")

    @property
    def embedding_text(self) -> str:
        """Text used for vector embedding and hybrid search."""
        if self.context_prefix:
            return f"{self.context_prefix}\n{self.text}"
        return self.text


class SearchFilter(BaseModel):
    """Filters applicable during retrieval."""
    doc_id: Optional[str] = Field(None, description="Filter by document ID (e.g. 'doc_9562')")
    min_page: Optional[int] = Field(None, description="Minimum page number")
    max_page: Optional[int] = Field(None, description="Maximum page number")
    chapter_keyword: Optional[str] = Field(None, description="Substring match on chapter title")
    exclude_front_matter: bool = Field(False, description="Exclude front matter / TOC pages")


class SearchRequest(BaseModel):
    """User search request."""
    query: str = Field(..., min_length=2, description="Search query string")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    dense_weight: float = Field(0.65, ge=0.0, le=1.0, description="Weight for semantic dense search")
    bm25_weight: float = Field(0.35, ge=0.0, le=1.0, description="Weight for keyword BM25 search")
    filter: Optional[SearchFilter] = Field(None, description="Optional metadata filters")


class SearchResultItem(BaseModel):
    """An individual search hit."""
    chunk_id: str
    doc_id: str
    doc_title: str
    filename: str
    page_number: int
    chapter: Optional[str]
    section: Optional[str]
    score: float = Field(..., description="Fused hybrid score (higher is better)")
    dense_score: Optional[float] = Field(None, description="Cosine similarity score")
    bm25_score: Optional[float] = Field(None, description="BM25 lexical score")
    text: str = Field(..., description="Chunk content")
    snippet: str = Field(..., description="Highlighted or focused snippet")


class SearchResponse(BaseModel):
    """Search response payload."""
    query: str
    total_results: int
    results: List[SearchResultItem]
    retrieval_mode: str = "hybrid (dense + bm25)"
    time_taken_ms: float = 0.0


class IndexingStats(BaseModel):
    """Statistics about indexed documents and chunks."""
    total_documents: int = 0
    total_chunks: int = 0
    total_pages_indexed: int = 0
    documents: List[DocumentMetadata] = Field(default_factory=list)
    embedding_backend: str = ""
    embedding_dimension: int = 0
    index_path: str = ""


class ImportFileInfo(BaseModel):
    """Information about a PDF found in the import or workspace directory."""
    filename: str
    file_path: str
    size_bytes: int
    last_modified: str
    mtime: float
    status: str = Field(..., description="'new', 'updated', or 'up_to_date'")
    doc_id: Optional[str] = None
    indexed_pages: Optional[int] = None


class ImportStatusResponse(BaseModel):
    """Status of files in the import directory vs currently indexed corpus."""
    import_dir: str
    has_pending_changes: bool
    total_pending: int
    new_files: List[ImportFileInfo] = Field(default_factory=list)
    updated_files: List[ImportFileInfo] = Field(default_factory=list)
    up_to_date_files: List[ImportFileInfo] = Field(default_factory=list)


class SyncImportResponse(BaseModel):
    """Response returned when new or updated PDFs are re-parsed and synced."""
    synced_count: int
    updated_documents: List[str]
    stats: IndexingStats

