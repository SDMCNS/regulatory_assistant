"""
db_linker.py - Skybrary Database Linking and Resolution.

Provides multi-key mapping between disk text/PDF files and skybrary.db metadata.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class SkybraryDBLinker:
    """Loads publications from skybrary.db and enables multi-key resolution."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.records_by_id: Dict[int, Dict[str, Any]] = {}
        self.records_by_pdf_path: Dict[str, Dict[str, Any]] = {}
        self.records_by_filename: Dict[str, Dict[str, Any]] = {}
        self.records_by_url_element: Dict[str, Dict[str, Any]] = {}
        self.records_by_title_clean: Dict[str, Dict[str, Any]] = {}
        self.load()

    @staticmethod
    def clean_stem(s: str) -> str:
        clean = re.sub(r"[^\w\s-]", "", s).strip().lower()
        return re.sub(r"\s+", " ", clean)

    def load(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("""
            SELECT id, title, category, author, publication_date, 
                   summary_url, pdf_url, pdf_path, download_status,
                   llm_score, llm_priority, llm_classification, llm_reason
            FROM publications
        """)
        rows = cur.fetchall()
        conn.close()

        for r in rows:
            rec = dict(r)
            doc_id = rec["id"]
            self.records_by_id[doc_id] = rec

            pdf_path_str = rec.get("pdf_path") or ""
            if pdf_path_str:
                norm_path = pdf_path_str.replace("/", "\\").strip().lower()
                self.records_by_pdf_path[norm_path] = rec

                fname = Path(pdf_path_str).name.lower()
                self.records_by_filename[fname] = rec
                self.records_by_filename[Path(fname).stem] = rec

            pdf_url = rec.get("pdf_url") or ""
            if pdf_url:
                url_elem = pdf_url.rstrip("/").split("/")[-1].lower()
                self.records_by_url_element[url_elem] = rec
                self.records_by_url_element[Path(url_elem).stem] = rec

            title = rec.get("title") or ""
            if title:
                self.records_by_title_clean[self.clean_stem(title)] = rec

    def find_publication(self, file_path: Path, base_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """
        Resolves a text or PDF file path against the DB index using 4 strategies:
        1. Relative path / category match
        2. Disk filename match (with .pdf or .txt stem)
        3. URL file element match (e.g. '34756_3.pdf' or '34756_3')
        4. Clean normalized title match
        """
        file_path = Path(file_path)

        # Strategy 1: Relative path match
        if base_dir:
            try:
                base_dir = Path(base_dir)
                rel = file_path.relative_to(base_dir)
                norm_rel = str(rel).replace("/", "\\").lower()
                norm_rel_pdf = str(rel.with_suffix(".pdf")).replace("/", "\\").lower()
                if norm_rel in self.records_by_pdf_path:
                    return self.records_by_pdf_path[norm_rel]
                if f"pdfs\\{norm_rel}" in self.records_by_pdf_path:
                    return self.records_by_pdf_path[f"pdfs\\{norm_rel}"]
                if f"pdfs\\{norm_rel_pdf}" in self.records_by_pdf_path:
                    return self.records_by_pdf_path[f"pdfs\\{norm_rel_pdf}"]
            except ValueError:
                pass

        # Strategy 2: Filename match
        fname = file_path.name.lower()
        fname_pdf = file_path.with_suffix(".pdf").name.lower()
        stem = file_path.stem.lower()

        if fname_pdf in self.records_by_filename:
            return self.records_by_filename[fname_pdf]
        if stem in self.records_by_filename:
            return self.records_by_filename[stem]

        # Strategy 3: URL file element match
        if fname_pdf in self.records_by_url_element:
            return self.records_by_url_element[fname_pdf]
        if stem in self.records_by_url_element:
            return self.records_by_url_element[stem]

        # Strategy 4: Clean title match
        clean_stem = self.clean_stem(file_path.stem)
        if clean_stem in self.records_by_title_clean:
            return self.records_by_title_clean[clean_stem]

        return None
