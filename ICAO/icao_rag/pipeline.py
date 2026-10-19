"""Master end-to-end pipeline connecting Parser, Filter, Chunker, Embedder, and Search Engine."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

from .chunker import HierarchicalChunker
from .config import PipelineConfig
from .embedder import BaseEmbedder, get_embedder
from .filter import FilterEngine
from .models import (
    Chunk,
    DocumentMetadata,
    ImportFileInfo,
    ImportStatusResponse,
    IndexingStats,
    SearchFilter,
    SearchRequest,
    SearchResponse,
    SyncImportResponse,
)
from .parser import PDFParser
from .retriever import HybridSearchEngine
from .vector_store import VectorStore

logger = logging.getLogger("icao_rag")


class ICAOPipeline:
    """Master pipeline for indexing and searching ICAO technical documents."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

        self.parser = PDFParser(self.config.parser)
        self.filter_engine = FilterEngine(self.config.filter)
        self.chunker = HierarchicalChunker(self.config.chunker, self.filter_engine)
        self.embedder: BaseEmbedder = get_embedder(self.config.embedder)
        self.vector_store = VectorStore(self.filter_engine)

        # Attempt to load cached index if available
        if self.config.storage_dir and Path(self.config.storage_dir).exists():
            loaded = self.vector_store.load(self.config.storage_dir)
            if loaded:
                logger.info(f"Loaded {self.vector_store.total_chunks} chunks from {self.config.storage_dir}")

        self.search_engine = HybridSearchEngine(
            vector_store=self.vector_store,
            embedder=self.embedder,
            config=self.config.search,
            filter_engine=self.filter_engine
        )

    def index_document(self, file_path: str | Path, save: bool = True) -> DocumentMetadata:
        """Parse, filter, chunk, embed, and index a single PDF document."""
        path = Path(file_path)
        logger.info(f"Parsing document: {path.name}")
        doc_meta, pages = self.parser.parse_document(path)

        # If this document already exists in the store, remove its previous chunks first
        self.vector_store.remove_document(doc_meta.doc_id)

        # Filter pages according to config
        filtered_pages = self.filter_engine.filter_pages(pages)
        logger.info(f"Retained {len(filtered_pages)} content pages for {path.name}")

        # Chunk pages
        chunks = self.chunker.chunk_document(doc_meta, filtered_pages)
        logger.info(f"Generated {len(chunks)} chunks for {path.name}")

        if chunks:
            # Embed chunks using context-prefixed text
            embedding_texts = [c.embedding_text for c in chunks]
            embeddings = self.embedder.embed_texts(embedding_texts)

            # Add to vector store
            self.vector_store.add(chunks, embeddings, doc_meta)
        else:
            existing_idx = next((i for i, d in enumerate(self.vector_store.documents) if d.doc_id == doc_meta.doc_id), None)
            if existing_idx is not None:
                self.vector_store.documents[existing_idx] = doc_meta
            else:
                self.vector_store.documents.append(doc_meta)

        if save and self.config.storage_dir:
            self.vector_store.save(self.config.storage_dir)

        # Rebuild BM25 index
        self.search_engine._rebuild_bm25_if_needed()

        return doc_meta

    def check_import_status(self) -> ImportStatusResponse:
        """Scan import directory and data directory for new or updated PDFs."""
        import_path = Path(self.config.import_dir)
        import_path.mkdir(parents=True, exist_ok=True)

        candidate_paths: Dict[str, Path] = {}

        # 1. Scan import_dir
        for p in import_path.glob("*.pdf"):
            candidate_paths[p.name.lower()] = p

        # 2. Scan data_dir
        if Path(self.config.data_dir).exists():
            for p in Path(self.config.data_dir).glob("*.pdf"):
                if p.name.lower() not in candidate_paths:
                    candidate_paths[p.name.lower()] = p

        indexed_doc_map = {d.filename.lower(): d for d in self.vector_store.documents}

        new_files: List[ImportFileInfo] = []
        updated_files: List[ImportFileInfo] = []
        up_to_date_files: List[ImportFileInfo] = []

        for fname_key, path in candidate_paths.items():
            stat = path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            last_mod_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            if fname_key not in indexed_doc_map:
                new_files.append(ImportFileInfo(
                    filename=path.name,
                    file_path=str(path.resolve()),
                    size_bytes=size,
                    last_modified=last_mod_str,
                    mtime=mtime,
                    status="new"
                ))
            else:
                existing = indexed_doc_map[fname_key]
                is_newer = (existing.file_mtime is not None and mtime > existing.file_mtime + 1.0)
                is_size_diff = (existing.file_size_bytes > 0 and abs(size - existing.file_size_bytes) > 0)

                if is_newer or is_size_diff:
                    updated_files.append(ImportFileInfo(
                        filename=path.name,
                        file_path=str(path.resolve()),
                        size_bytes=size,
                        last_modified=last_mod_str,
                        mtime=mtime,
                        status="updated",
                        doc_id=existing.doc_id,
                        indexed_pages=existing.indexed_pages
                    ))
                else:
                    up_to_date_files.append(ImportFileInfo(
                        filename=path.name,
                        file_path=str(path.resolve()),
                        size_bytes=size,
                        last_modified=last_mod_str,
                        mtime=mtime,
                        status="up_to_date",
                        doc_id=existing.doc_id,
                        indexed_pages=existing.indexed_pages
                    ))

        total_pending = len(new_files) + len(updated_files)

        return ImportStatusResponse(
            import_dir=str(import_path.resolve()),
            has_pending_changes=total_pending > 0,
            total_pending=total_pending,
            new_files=new_files,
            updated_files=updated_files,
            up_to_date_files=up_to_date_files
        )

    def sync_imports(self, force: bool = False) -> SyncImportResponse:
        """Reparse and index any new or updated PDF documents."""
        status = self.check_import_status()
        if force:
            targets = [Path(f.file_path) for f in status.new_files + status.updated_files + status.up_to_date_files]
        else:
            targets = [Path(f.file_path) for f in status.new_files + status.updated_files]

        updated_doc_names = []
        for pdf_path in targets:
            doc_meta = self.index_document(pdf_path, save=False)
            updated_doc_names.append(f"{doc_meta.title} ({doc_meta.filename})")

        if targets and self.config.storage_dir:
            self.vector_store.save(self.config.storage_dir)

        return SyncImportResponse(
            synced_count=len(targets),
            updated_documents=updated_doc_names,
            stats=self.get_stats()
        )

    def index_directory(
        self,
        directory: Optional[str | Path] = None,
        force_reindex: bool = False,
        pattern: str = "*.pdf"
    ) -> IndexingStats:
        """Discover and index all matching PDFs in a directory."""
        dir_path = Path(directory or self.config.data_dir)
        pdf_files = list(dir_path.glob(pattern))

        if not pdf_files:
            logger.warning(f"No PDF files found matching '{pattern}' in {dir_path}")
            return self.get_stats()

        # If already indexed and not force_reindex, verify documents
        if not force_reindex and self.vector_store.total_chunks > 0:
            indexed_filenames = {d.filename for d in self.vector_store.documents}
            new_files = [p for p in pdf_files if p.name not in indexed_filenames]
            if not new_files:
                logger.info("All documents in directory are already indexed.")
                return self.get_stats()
            pdf_files = new_files

        for pdf in pdf_files:
            self.index_document(pdf, save=False)

        # Persist once after all documents are processed
        if self.config.storage_dir:
            self.vector_store.save(self.config.storage_dir)

        return self.get_stats()

    def search(
        self,
        query: str,
        top_k: int = 5,
        dense_weight: float = 0.65,
        bm25_weight: float = 0.35,
        filter_criteria: Optional[SearchFilter] = None
    ) -> SearchResponse:
        """Execute hybrid search with customizable weights and metadata filters."""
        req = SearchRequest(
            query=query,
            top_k=top_k,
            dense_weight=dense_weight,
            bm25_weight=bm25_weight,
            filter=filter_criteria
        )
        return self.search_engine.search(req)

    def get_stats(self) -> IndexingStats:
        """Retrieve current indexing statistics."""
        return IndexingStats(
            total_documents=len(self.vector_store.documents),
            total_chunks=self.vector_store.total_chunks,
            total_pages_indexed=sum(d.indexed_pages for d in self.vector_store.documents),
            documents=self.vector_store.documents,
            embedding_backend=self.config.embedder.backend,
            embedding_dimension=self.vector_store.dimension or self.embedder.dimension,
            index_path=str(self.config.storage_dir)
        )

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Find a specific chunk by its ID."""
        for c in self.vector_store.chunks:
            if c.chunk_id == chunk_id:
                return c
        return None
