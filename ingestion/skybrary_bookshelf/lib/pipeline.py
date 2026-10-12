"""
pipeline.py - High-Level Orchestrator for Skybrary Ingestion.

Coordinates PDF text extraction, database metadata linking, boilerplate
cleaning, page-aware chunking, and JSON/SQLite export.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .chunker import ChunkRecord, DocumentMetadata, SkybraryChunker
from .db_linker import SkybraryDBLinker
from .extractor import ExtractionResult, SkybraryExtractor
from .storage import save_to_sqlite, write_batch_manifest, write_document_json


class SkybraryPipeline:
    """Overarching Skybrary Bookshelf pipeline."""

    def __init__(
        self,
        db_path: Path,
        enable_ocr: bool = False,
        tesseract_cmd: Optional[str] = None,
        target_words: int = 350,
        max_words: int = 600,
    ):
        self.db_path = Path(db_path)
        self.linker = SkybraryDBLinker(self.db_path)
        self.extractor = SkybraryExtractor(enable_ocr=enable_ocr, tesseract_cmd=tesseract_cmd)
        self.chunker = SkybraryChunker(target_words=target_words, max_words=max_words)

    def process_text_file(
        self,
        txt_file: Path,
        text_dir: Path,
        out_dir: Optional[Path] = None,
        sqlite_db: Optional[Path] = None,
    ) -> Optional[Tuple[DocumentMetadata, List[ChunkRecord]]]:
        """Processes a single extracted text file: links DB record, cleans, chunks, and writes."""
        txt_file = Path(txt_file)
        text_dir = Path(text_dir)

        pub_info = self.linker.find_publication(txt_file, base_dir=text_dir)
        if not pub_info:
            return None

        raw_text = txt_file.read_text(encoding="utf-8")
        doc_meta, chunks = self.chunker.chunk_document(pub_info, raw_text)

        if out_dir:
            out_dir = Path(out_dir)
            rel = txt_file.relative_to(text_dir)
            out_json = out_dir / rel.with_suffix(".chunks.json")
            write_document_json(doc_meta, chunks, out_json)

        if sqlite_db:
            save_to_sqlite(Path(sqlite_db), doc_meta, chunks)

        return doc_meta, chunks

    def process_all_texts(
        self,
        text_dir: Path,
        out_dir: Path,
        sqlite_db: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Processes all extracted text files in a directory."""
        text_dir = Path(text_dir)
        out_dir = Path(out_dir)
        t0 = time.time()

        txt_files = sorted(
            p for p in text_dir.rglob("*.txt")
            if p.is_file() and not p.name.startswith("_")
        )

        manifest_docs: List[Dict[str, Any]] = []
        matched = 0
        unmatched = 0
        total_chunks = 0

        for idx, txt_file in enumerate(txt_files, 1):
            rel = txt_file.relative_to(text_dir)
            res = self.process_text_file(txt_file, text_dir, out_dir=out_dir, sqlite_db=sqlite_db)
            if res is None:
                unmatched += 1
                continue

            doc_meta, chunks = res
            matched += 1
            total_chunks += len(chunks)

            if idx % 250 == 0 or idx == len(txt_files):
                print(
                    f"[{idx}/{len(txt_files)}] Generated {total_chunks} chunks ({matched} matched, {unmatched} unmatched)...",
                    flush=True,
                )

            out_json = out_dir / rel.with_suffix(".chunks.json")
            manifest_docs.append({
                "skybrary_id": doc_meta.metadata.get("skybrary_id"),
                "document_id": doc_meta.document_id,
                "title": doc_meta.title,
                "category": doc_meta.category,
                "author": doc_meta.author,
                "date": doc_meta.date,
                "pages": doc_meta.pages,
                "chunk_count": len(chunks),
                "chunks_file": str(out_json.relative_to(out_dir)),
                "source_txt": str(rel),
                "pdf_url": doc_meta.pdf_url,
                "pdf_filename": doc_meta.pdf_filename,
                "url_file_element": doc_meta.url_file_element,
            })

        elapsed = time.time() - t0
        manifest_path = out_dir / "_skybrary_manifest.json"
        write_batch_manifest(manifest_docs, manifest_path, matched, total_chunks, elapsed)

        return {
            "total_files": len(txt_files),
            "matched": matched,
            "unmatched": unmatched,
            "total_chunks": total_chunks,
            "elapsed_seconds": round(elapsed, 2),
            "manifest_path": manifest_path,
        }

    def extract_and_chunk_pdfs(
        self,
        pdf_dir: Path,
        text_dir: Path,
        out_dir: Path,
        sqlite_db: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Full end-to-end extraction from PDFs followed by chunking and export."""
        pdf_dir = Path(pdf_dir)
        text_dir = Path(text_dir)
        out_dir = Path(out_dir)

        pdf_files = sorted(pdf_dir.rglob("*.pdf"))

        for pdf in pdf_files:
            rel = pdf.relative_to(pdf_dir)
            out_txt = text_dir / rel.with_suffix(".txt")
            if not out_txt.exists():
                self.extractor.extract_file(pdf, out_txt)

        return self.process_all_texts(text_dir, out_dir, sqlite_db=sqlite_db)
