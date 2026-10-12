"""
extractor.py - High-Performance PDF to Text Extractor for Skybrary Documents.

Wraps PyMuPDF (fitz) text extraction with optional Tesseract OCR fallback,
Unicode validation, and page boundary preservation.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF


DEFAULT_MIN_CHARS_PER_PAGE = 50
DEFAULT_OCR_DPI = 180
DEFAULT_TESSERACT_WINDOWS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class ExtractionResult:
    source_path: str
    output_path: str
    status: str  # PASS, WARN, FAIL
    pages: int = 0
    pages_with_text: int = 0
    pages_ocr: int = 0
    total_chars: int = 0
    total_words: int = 0
    sha256: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class SkybraryExtractor:
    """PDF-to-text extractor and validator."""

    def __init__(
        self,
        enable_ocr: bool = False,
        tesseract_cmd: Optional[str] = None,
        ocr_dpi: int = DEFAULT_OCR_DPI,
        min_chars_per_page: int = DEFAULT_MIN_CHARS_PER_PAGE,
    ):
        self.enable_ocr = enable_ocr
        self.tesseract_cmd = tesseract_cmd or self._detect_tesseract()
        self.ocr_dpi = ocr_dpi
        self.min_chars_per_page = min_chars_per_page

    @staticmethod
    def _detect_tesseract() -> Optional[str]:
        """Detects tesseract binary on PATH or common Windows installation paths."""
        which_path = shutil.which("tesseract")
        if which_path:
            return which_path
        if os.path.exists(DEFAULT_TESSERACT_WINDOWS):
            return DEFAULT_TESSERACT_WINDOWS
        return None

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()

    def extract_file(self, pdf_path: Path, output_txt_path: Optional[Path] = None) -> Tuple[ExtractionResult, str]:
        """
        Extracts a single PDF file and returns (ExtractionResult, combined_text).
        If output_txt_path is provided, writes the text file.
        """
        started = time.perf_counter()
        pdf_path = Path(pdf_path)
        out_str = str(output_txt_path) if output_txt_path else ""

        res = ExtractionResult(
            source_path=str(pdf_path),
            output_path=out_str,
            status="PASS",
        )

        try:
            res.sha256 = self.sha256_file(pdf_path)
        except Exception as e:
            res.status = "FAIL"
            res.errors.append(f"Cannot read file: {e}")
            res.elapsed_seconds = time.perf_counter() - started
            return res, ""

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            res.status = "FAIL"
            res.errors.append(f"Failed to open PDF: {e}")
            res.elapsed_seconds = time.perf_counter() - started
            return res, ""

        try:
            res.pages = len(doc)
            if res.pages == 0:
                res.status = "FAIL"
                res.errors.append("PDF contains zero pages.")
                return res, ""

            page_chunks = []
            empty_count = 0

            for idx in range(res.pages):
                page_num = idx + 1
                page = doc.load_page(idx)

                try:
                    text = page.get_text("text", sort=True) or ""
                except Exception as e:
                    text = ""
                    res.warnings.append(f"Page {page_num} extraction error: {e}")

                # Optional OCR fallback if page text is suspiciously small
                if (
                    self.enable_ocr
                    and len(text.strip()) < self.min_chars_per_page
                    and self.tesseract_cmd
                ):
                    try:
                        import pytesseract
                        from PIL import Image

                        pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
                        pix = page.get_pixmap(dpi=self.ocr_dpi)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr_text = pytesseract.image_to_string(img, lang="eng", config="--psm 3", timeout=30)
                        if len(ocr_text.strip()) > len(text.strip()):
                            text = ocr_text
                            res.pages_ocr += 1
                    except Exception as e:
                        res.warnings.append(f"Page {page_num} OCR failed: {e}")

                clean_text = unicodedata.normalize("NFC", text).strip()
                if clean_text:
                    res.pages_with_text += 1
                else:
                    empty_count += 1

                page_chunks.append(f"--- PAGE {page_num} ---\n{clean_text}\n")

            combined_text = "\n".join(page_chunks)
            res.total_chars = len(combined_text)
            res.total_words = len(combined_text.split())

            if empty_count > 0:
                res.warnings.append(f"{empty_count} page(s) contain no extractable text.")
                res.status = "WARN"

            if output_txt_path:
                output_txt_path = Path(output_txt_path)
                output_txt_path.parent.mkdir(parents=True, exist_ok=True)
                output_txt_path.write_text(combined_text, encoding="utf-8")

        finally:
            doc.close()

        res.elapsed_seconds = time.perf_counter() - started
        return res, combined_text
