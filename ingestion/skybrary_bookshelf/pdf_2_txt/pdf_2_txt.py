#!/usr/bin/env python3
"""
Robust batch PDF -> text extractor and validator.

Primary extractor: PyMuPDF
Optional OCR fallback: Tesseract + pytesseract

Design goals:
- Never let one bad PDF stop a batch.
- Preserve page boundaries.
- Validate extracted Unicode rather than assuming extraction succeeded.
- Flag suspicious files for human follow-up.
- Produce TXT + CSV + JSONL manifests.
- Optionally recurse through subdirectories.
- Safe to run repeatedly.

Typical usage:
    python pdf_to_text.py ./pdfs ./text
    python pdf_to_text.py ./pdfs ./text --recursive --ocr
    python pdf_to_text.py ./pdfs ./text --workers 4 --ocr

Dependencies:
    pip install pymupdf

Optional OCR:
    pip install pytesseract pillow
    Install the Tesseract executable separately and make sure it is on PATH.
    On Windows, alternatively use:
        --tesseract "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

Exit codes:
    0 = batch completed; no FAIL files
    1 = batch completed; one or more files FAILed
    2 = configuration/runtime error
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF is not installed. Run: pip install pymupdf", file=sys.stderr)
    raise SystemExit(2)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MIN_CHARS_PER_PAGE = 50
DEFAULT_MIN_ALNUM_RATIO = 0.08
DEFAULT_MAX_REPLACEMENT_RATIO = 0.0005
DEFAULT_MAX_SUSPICIOUS_RATIO = 0.01
DEFAULT_MIN_WORDS_PER_TEXT_PAGE = 8
DEFAULT_OCR_DPI = 180

# Common mojibake signatures. These are warnings, not automatic failures.
MOJIBAKE_PATTERNS = [
    r"Ã.",
    r"Â.",
    r"â[€€™œž“”]",
    r"ðŸ",
    r"ï¿½",
    r"â€",
]

# Characters that are normally highly suspicious in extracted prose.
# Do not classify ordinary whitespace/control formatting as suspicious.
SUSPICIOUS_CATEGORIES = {"Cc", "Cs", "Co", "Cn"}

# Characters allowed from the C0 control range.
ALLOWED_CONTROLS = {"\t", "\n", "\r", "\f"}

# Some PDFs use these harmless formatting characters.
ALLOWED_FORMAT_CHARS = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # BOM / zero-width no-break space
}

# Replacement character is particularly important.
REPLACEMENT_CHAR = "\ufffd"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    page_number: int
    native_chars: int = 0
    native_words: int = 0
    native_alnum: int = 0
    native_replacement: int = 0
    native_suspicious: int = 0
    native_unknown: int = 0
    native_mojibake_hits: int = 0
    native_text: str = ""
    ocr_used: bool = False
    ocr_chars: int = 0
    ocr_words: int = 0
    ocr_confidence: float | None = None
    ocr_text: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class FileResult:
    source: str
    output: str = ""
    status: str = "FAIL"
    reason: str = ""
    size_bytes: int = 0
    sha256: str = ""
    pages: int = 0
    pages_with_text: int = 0
    pages_ocr: int = 0
    total_chars: int = 0
    total_words: int = 0
    alnum_ratio: float = 0.0
    replacement_count: int = 0
    replacement_ratio: float = 0.0
    suspicious_count: int = 0
    suspicious_ratio: float = 0.0
    unknown_count: int = 0
    mojibake_hits: int = 0
    empty_pages: int = 0
    short_pages: int = 0
    native_chars: int = 0
    ocr_chars: int = 0
    avg_ocr_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    page_diagnostics: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def safe_output_name(pdf: Path, input_root: Path) -> Path:
    """
    Preserve relative directory structure, changing only the suffix.
    This prevents two PDFs with the same basename in different directories
    from overwriting each other.
    """
    try:
        rel = pdf.relative_to(input_root)
    except ValueError:
        rel = Path(pdf.name)
    return rel.with_suffix(".txt")


def is_suspicious_char(ch: str) -> bool:
    if ch in ALLOWED_CONTROLS or ch in ALLOWED_FORMAT_CHARS:
        return False

    category = unicodedata.category(ch)

    if category in SUSPICIOUS_CATEGORIES:
        return True

    # Isolated surrogate / non-character handling.
    code = ord(ch)
    if 0xD800 <= code <= 0xDFFF:
        return True

    return False


def character_stats(text: str) -> dict:
    replacements = text.count(REPLACEMENT_CHAR)
    suspicious = 0
    unknown = 0

    for ch in text:
        category = unicodedata.category(ch)
        if category == "Cn":
            unknown += 1
        if is_suspicious_char(ch):
            suspicious += 1

    alnum = sum(ch.isalnum() for ch in text)
    return {
        "chars": len(text),
        "alnum": alnum,
        "replacement": replacements,
        "suspicious": suspicious,
        "unknown": unknown,
        "mojibake": count_mojibake(text),
    }


def count_mojibake(text: str) -> int:
    return sum(len(re.findall(pattern, text)) for pattern in MOJIBAKE_PATTERNS)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÖØ-öø-ÿĀ-ſ]+(?:[-'][\wÀ-ÖØ-öø-ÿĀ-ſ]+)*\b", text, re.UNICODE))


def normalise_text(text: str) -> str:
    """
    Conservative normalisation.

    NFC combines canonically equivalent sequences but does not alter the
    meaning of normal accented characters. We deliberately do NOT strip
    unusual Unicode merely because it is unusual; validation should flag it.
    """
    text = text.replace("\x00", "")
    text = unicodedata.normalize("NFC", text)

    # Normalise line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove trailing whitespace but preserve internal spacing.
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # Collapse pathological runs of blank lines while retaining page breaks.
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip() + ("\n" if text.strip() else "")


def render_page_for_ocr(page, dpi: int):
    """Render a PDF page as a PIL image for Tesseract."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for OCR. Install with: pip install pillow"
        ) from exc

    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    # pix.samples is RGB because alpha=False.
    from PIL import Image
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def auto_detect_tesseract() -> str | None:
    """Detects tesseract binary on PATH or standard Windows installation locations."""
    which = shutil.which("tesseract")
    if which:
        return which
    windows_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(windows_default):
        return windows_default
    windows_x86 = r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    if os.path.exists(windows_x86):
        return windows_x86
    return None


def tesseract_available(tesseract_cmd: str | None) -> bool:
    try:
        import pytesseract
        cmd = tesseract_cmd or auto_detect_tesseract()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_page(page, dpi: int, tesseract_cmd: str | None) -> tuple[str, float | None]:
    import pytesseract

    cmd = tesseract_cmd or auto_detect_tesseract()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    image = render_page_for_ocr(page, dpi)

    # PSM 3 is a good general-purpose layout mode for regulatory documents.
    config = "--psm 3"

    try:
        # Single-pass execution with per-page timeout prevents duplicate processing and infinite hangs
        text = pytesseract.image_to_string(
            image,
            lang="eng",
            config=config,
            timeout=30,
        )
    except Exception:
        text = ""

    return text, None


def should_ocr(page_result: PageResult, min_chars: int) -> bool:
    """
    OCR only pages that look suspiciously empty or nearly empty.

    A native PDF page with substantial text is not OCR'd, which avoids
    unnecessary OCR degradation and makes the normal path much faster.
    """
    if page_result.native_chars == 0:
        return True

    if page_result.native_chars < min_chars:
        return True

    # Replacement characters or large amounts of suspicious encoding damage
    # justify an OCR attempt.
    if page_result.native_replacement > 0:
        return True

    if page_result.native_unknown > 0:
        return True

    return False


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_pdf(
    pdf_path: Path,
    output_path: Path,
    enable_ocr: bool,
    tesseract_cmd: str | None,
    ocr_dpi: int,
    min_chars_per_page: int,
    min_words_per_page: int,
    min_alnum_ratio: float,
    max_replacement_ratio: float,
    max_suspicious_ratio: float,
) -> FileResult:

    started = time.perf_counter()

    result = FileResult(
        source=str(pdf_path),
        output=str(output_path),
    )

    try:
        result.size_bytes = pdf_path.stat().st_size
        result.sha256 = sha256_file(pdf_path)
    except Exception as exc:
        result.errors.append(f"Cannot read file metadata: {type(exc).__name__}: {exc}")
        result.reason = "FILE_READ_ERROR"
        result.elapsed_seconds = time.perf_counter() - started
        return result

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        result.errors.append(f"PDF open failed: {type(exc).__name__}: {exc}")
        result.reason = "PDF_OPEN_ERROR"
        result.elapsed_seconds = time.perf_counter() - started
        return result

    try:
        if doc.is_encrypted:
            # PyMuPDF may open encrypted files but extraction can still fail.
            # Try the empty password; if it cannot authenticate, flag it.
            try:
                authenticated = doc.authenticate("")
            except Exception:
                authenticated = False
            if not authenticated and doc.needs_pass:
                result.errors.append("PDF is password protected.")
                result.reason = "PASSWORD_PROTECTED"
                return result

        result.pages = len(doc)

        if result.pages == 0:
            result.errors.append("PDF contains zero pages.")
            result.reason = "NO_PAGES"
            return result

        ocr_ready = False
        if enable_ocr:
            ocr_ready = tesseract_available(tesseract_cmd)
            if not ocr_ready:
                result.warnings.append(
                    "OCR requested but Tesseract is unavailable; native extraction only."
                )

        page_results: list[PageResult] = []
        page_texts: list[str] = []

        for page_index in range(result.pages):
            page = doc.load_page(page_index)
            pr = PageResult(page_number=page_index + 1)

            try:
                native_text = page.get_text("text", sort=True) or ""
            except Exception as exc:
                native_text = ""
                pr.warnings.append(
                    f"Native extraction failed: {type(exc).__name__}: {exc}"
                )

            native_text = normalise_text(native_text)
            stats = character_stats(native_text)

            pr.native_text = native_text
            pr.native_chars = stats["chars"]
            pr.native_words = word_count(native_text)
            pr.native_alnum = stats["alnum"]
            pr.native_replacement = stats["replacement"]
            pr.native_suspicious = stats["suspicious"]
            pr.native_unknown = stats["unknown"]
            pr.native_mojibake_hits = stats["mojibake"]

            selected_text = native_text

            if enable_ocr and ocr_ready and should_ocr(pr, min_chars_per_page):
                if result.pages > 1:
                    print(
                        f"      [{pdf_path.name[:45]}] OCR page {page_index + 1}/{result.pages}...",
                        flush=True,
                    )
                try:
                    ocr_t0 = time.perf_counter()
                    ocr_text, confidence = ocr_page(
                        page,
                        dpi=ocr_dpi,
                        tesseract_cmd=tesseract_cmd,
                    )
                    ocr_text = normalise_text(ocr_text)
                    pr.ocr_text = ocr_text
                    pr.ocr_chars = len(ocr_text)
                    pr.ocr_words = word_count(ocr_text)
                    pr.ocr_confidence = confidence

                    # Use OCR if it provides materially more text than the
                    # native extraction. This avoids replacing good PDF text
                    # with lower-quality OCR.
                    if pr.ocr_chars > max(pr.native_chars * 1.5, min_chars_per_page):
                        selected_text = ocr_text
                        pr.ocr_used = True
                    elif pr.native_chars == 0 and pr.ocr_chars > 0:
                        selected_text = ocr_text
                        pr.ocr_used = True

                    if result.pages > 1 and pr.ocr_used:
                        ocr_elapsed = time.perf_counter() - ocr_t0
                        print(
                            f"      [{pdf_path.name[:45]}] OCR page {page_index + 1}/{result.pages} done in {ocr_elapsed:.1f}s ({pr.ocr_chars} chars)",
                            flush=True,
                        )

                except Exception as exc:
                    pr.warnings.append(
                        f"OCR failed: {type(exc).__name__}: {exc}"
                    )

            if selected_text.strip():
                result.pages_with_text += 1
            else:
                result.empty_pages += 1
                pr.warnings.append("No extractable text.")

            if len(selected_text.strip()) < min_chars_per_page:
                result.short_pages += 1

            if pr.ocr_used:
                result.pages_ocr += 1
                result.ocr_chars += len(selected_text)
            else:
                result.native_chars += len(selected_text)

            page_texts.append(selected_text)
            page_results.append(pr)

        # Build output with explicit page markers. These are useful downstream
        # for legal/regulatory chunking and troubleshooting.
        chunks = []
        for pr, text in zip(page_results, page_texts):
            chunks.append(
                f"--- PAGE {pr.page_number} ---\n"
                f"{text.rstrip()}\n"
            )

        combined = normalise_text("\n".join(chunks))

        overall = character_stats(combined)
        result.total_chars = overall["chars"]
        result.total_words = word_count(combined)
        result.replacement_count = overall["replacement"]
        result.suspicious_count = overall["suspicious"]
        result.unknown_count = overall["unknown"]
        result.mojibake_hits = overall["mojibake"]

        if result.total_chars:
            result.alnum_ratio = overall["alnum"] / result.total_chars
            result.replacement_ratio = (
                result.replacement_count / result.total_chars
            )
            result.suspicious_ratio = (
                result.suspicious_count / result.total_chars
            )

        confidences = [
            p.ocr_confidence
            for p in page_results
            if p.ocr_used and p.ocr_confidence is not None
        ]
        if confidences:
            result.avg_ocr_confidence = sum(confidences) / len(confidences)

        # -------------------------------------------------------------------
        # Validation
        # -------------------------------------------------------------------

        failures: list[str] = []
        warnings: list[str] = []

        if result.pages_with_text == 0:
            failures.append("No text extracted from any page.")

        if result.replacement_count:
            if result.replacement_ratio > max_replacement_ratio:
                failures.append(
                    f"Replacement character ratio "
                    f"{result.replacement_ratio:.4%} exceeds "
                    f"{max_replacement_ratio:.4%}."
                )
            else:
                warnings.append(
                    f"Contains {result.replacement_count} Unicode replacement character(s)."
                )

        if result.unknown_count:
            failures.append(
                f"Contains {result.unknown_count} Unicode 'unassigned' character(s)."
            )

        if result.suspicious_ratio > max_suspicious_ratio:
            failures.append(
                f"Suspicious/control/private-use character ratio "
                f"{result.suspicious_ratio:.4%} exceeds "
                f"{max_suspicious_ratio:.4%}."
            )
        elif result.suspicious_count:
            warnings.append(
                f"Contains {result.suspicious_count} suspicious/control/private-use character(s)."
            )

        if result.mojibake_hits:
            warnings.append(
                f"Possible mojibake detected ({result.mojibake_hits} pattern hit(s))."
            )

        if result.alnum_ratio < min_alnum_ratio:
            failures.append(
                f"Very low alphanumeric ratio ({result.alnum_ratio:.2%}); "
                "possible extraction/layout failure."
            )

        # Don't fail a document merely because it contains blank pages.
        # But flag substantial blank-page populations.
        if result.empty_pages:
            if result.empty_pages >= max(2, math.ceil(result.pages * 0.25)):
                warnings.append(
                    f"{result.empty_pages}/{result.pages} pages contain no extractable text."
                )
            else:
                warnings.append(
                    f"{result.empty_pages} page(s) contain no extractable text."
                )

        if result.short_pages:
            if result.short_pages >= max(3, math.ceil(result.pages * 0.5)):
                warnings.append(
                    f"{result.short_pages}/{result.pages} pages contain very little text."
                )
            else:
                warnings.append(
                    f"{result.short_pages} page(s) contain very little text."
                )

        if result.pages_ocr:
            warnings.append(f"OCR used on {result.pages_ocr} page(s).")

        if (
            result.avg_ocr_confidence is not None
            and result.avg_ocr_confidence < 70
        ):
            warnings.append(
                f"Average OCR confidence is only {result.avg_ocr_confidence:.1f}%."
            )

        # A PDF with almost no words despite having characters is suspicious.
        if result.total_chars >= 500 and result.total_words < max(10, result.pages * min_words_per_page):
            warnings.append(
                "Character count is high but word count is unusually low; "
                "possible extraction/layout artefact."
            )

        # Detect a page where native extraction was tiny but OCR also failed.
        for pr in page_results:
            if (
                pr.native_chars < min_chars_per_page
                and not pr.ocr_used
                and pr.native_chars > 0
            ):
                warnings.append(
                    f"Page {pr.page_number} has only {pr.native_chars} extracted characters."
                )

        result.warnings.extend(warnings)
        result.errors.extend(failures)

        result.page_diagnostics = [
            {
                "page": p.page_number,
                "native_chars": p.native_chars,
                "native_words": p.native_words,
                "ocr_used": p.ocr_used,
                "ocr_chars": p.ocr_chars,
                "ocr_words": p.ocr_words,
                "ocr_confidence": p.ocr_confidence,
                "replacement": p.native_replacement,
                "suspicious": p.native_suspicious,
                "unknown": p.native_unknown,
                "mojibake": p.native_mojibake_hits,
                "warnings": p.warnings,
            }
            for p in page_results
        ]

        # Write text even for WARN/FAIL where useful. This lets the operator
        # inspect the output instead of losing potentially useful material.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(combined, encoding="utf-8", newline="\n")

        if failures:
            result.status = "FAIL"
            result.reason = "; ".join(failures)
        elif warnings:
            result.status = "WARN"
            result.reason = "; ".join(warnings)
        else:
            result.status = "PASS"
            result.reason = "Extraction and validation passed."

    except Exception as exc:
        result.status = "FAIL"
        result.reason = "UNEXPECTED_ERROR"
        result.errors.append(
            f"Unexpected processing error: {type(exc).__name__}: {exc}"
        )

    finally:
        try:
            doc.close()
        except Exception:
            pass

        result.elapsed_seconds = time.perf_counter() - started

    return result


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def find_pdfs(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(
        p for p in input_dir.glob(pattern)
        if p.is_file()
    )


def write_csv(results: list[FileResult], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in results:
        rows.append({
            "source": r.source,
            "output": r.output,
            "status": r.status,
            "reason": r.reason,
            "size_bytes": r.size_bytes,
            "sha256": r.sha256,
            "pages": r.pages,
            "pages_with_text": r.pages_with_text,
            "pages_ocr": r.pages_ocr,
            "total_chars": r.total_chars,
            "total_words": r.total_words,
            "alnum_ratio": f"{r.alnum_ratio:.6f}",
            "replacement_count": r.replacement_count,
            "replacement_ratio": f"{r.replacement_ratio:.8f}",
            "suspicious_count": r.suspicious_count,
            "suspicious_ratio": f"{r.suspicious_ratio:.8f}",
            "unknown_count": r.unknown_count,
            "mojibake_hits": r.mojibake_hits,
            "empty_pages": r.empty_pages,
            "short_pages": r.short_pages,
            "native_chars": r.native_chars,
            "ocr_chars": r.ocr_chars,
            "avg_ocr_confidence": (
                ""
                if r.avg_ocr_confidence is None
                else f"{r.avg_ocr_confidence:.2f}"
            ),
            "warnings": " | ".join(r.warnings),
            "errors": " | ".join(r.errors),
            "elapsed_seconds": f"{r.elapsed_seconds:.3f}",
        })

    if not rows:
        fieldnames = ["source"]
    else:
        fieldnames = list(rows[0].keys())

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(results: list[FileResult], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def write_followup_report(results: list[FileResult], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    flagged = [r for r in results if r.status != "PASS"]

    with path.open("w", encoding="utf-8") as f:
        f.write("# PDF extraction follow-up report\n\n")
        f.write(f"Flagged files: {len(flagged)} / {len(results)}\n\n")

        for r in flagged:
            f.write(f"## {r.source}\n\n")
            f.write(f"- Status: **{r.status}**\n")
            f.write(f"- Reason: {r.reason}\n")
            f.write(f"- Pages: {r.pages}\n")
            f.write(f"- Extracted characters: {r.total_chars}\n")
            f.write(f"- Extracted words: {r.total_words}\n")
            f.write(f"- OCR pages: {r.pages_ocr}\n")
            f.write(f"- SHA-256: `{r.sha256}`\n")

            if r.warnings:
                f.write("\n### Warnings\n")
                for item in r.warnings:
                    f.write(f"- {item}\n")

            if r.errors:
                f.write("\n### Errors / failures\n")
                for item in r.errors:
                    f.write(f"- {item}\n")

            f.write("\n")


def print_summary(results: list[FileResult]):
    counts = Counter(r.status for r in results)
    print()
    print("=" * 72)
    print("PDF EXTRACTION SUMMARY")
    print("=" * 72)
    print(f"Files processed : {len(results)}")
    print(f"PASS            : {counts.get('PASS', 0)}")
    print(f"WARN            : {counts.get('WARN', 0)}")
    print(f"FAIL            : {counts.get('FAIL', 0)}")
    print()

    flagged = [r for r in results if r.status != "PASS"]
    if flagged:
        print("FOLLOW-UP REQUIRED:")
        for r in flagged:
            print(f"  [{r.status}] {r.source}")
            if r.reason:
                print(f"       {r.reason}")

    print("=" * 72)


def worker(args_tuple):
    return extract_pdf(*args_tuple)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Robust batch PDF -> UTF-8 text extraction and validation."
    )

    p.add_argument("input", type=Path, help="Input directory containing PDFs.")
    p.add_argument("output", type=Path, help="Output directory for text/report files.")

    p.add_argument(
        "--recursive",
        action="store_true",
        help="Search input directory recursively.",
    )
    p.add_argument(
        "--ocr",
        action="store_true",
        help="OCR pages where native extraction appears empty/broken.",
    )
    p.add_argument(
        "--tesseract",
        type=str,
        default=None,
        help="Full path to tesseract.exe if it is not on PATH.",
    )
    p.add_argument(
        "--ocr-dpi",
        type=int,
        default=DEFAULT_OCR_DPI,
        help=f"OCR render DPI (default: {DEFAULT_OCR_DPI}).",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel worker processes. Start with 1; increase for large batches.",
    )

    p.add_argument(
        "--min-chars-page",
        type=int,
        default=DEFAULT_MIN_CHARS_PER_PAGE,
        help=f"Below this, a page is considered short (default: {DEFAULT_MIN_CHARS_PER_PAGE}).",
    )
    p.add_argument(
        "--min-words-page",
        type=int,
        default=DEFAULT_MIN_WORDS_PER_TEXT_PAGE,
        help=f"Expected minimum words/page for some structural checks (default: {DEFAULT_MIN_WORDS_PER_TEXT_PAGE}).",
    )
    p.add_argument(
        "--min-alnum-ratio",
        type=float,
        default=DEFAULT_MIN_ALNUM_RATIO,
        help=f"Minimum document alphanumeric ratio (default: {DEFAULT_MIN_ALNUM_RATIO}).",
    )
    p.add_argument(
        "--max-replacement-ratio",
        type=float,
        default=DEFAULT_MAX_REPLACEMENT_RATIO,
        help=f"Maximum replacement-char ratio before FAIL (default: {DEFAULT_MAX_REPLACEMENT_RATIO}).",
    )
    p.add_argument(
        "--max-suspicious-ratio",
        type=float,
        default=DEFAULT_MAX_SUSPICIOUS_RATIO,
        help=f"Maximum suspicious-char ratio before FAIL (default: {DEFAULT_MAX_SUSPICIOUS_RATIO}).",
    )

    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess files even when output text already exists.",
    )

    return p


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args()

    input_dir: Path = args.input.resolve()
    output_dir: Path = args.output.resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"ERROR: Input directory does not exist: {input_dir}", file=sys.stderr)
        return 2

    if args.workers < 1:
        print("ERROR: --workers must be >= 1", file=sys.stderr)
        return 2

    if not 0 <= args.min_alnum_ratio <= 1:
        print("ERROR: --min-alnum-ratio must be between 0 and 1", file=sys.stderr)
        return 2

    pdfs = find_pdfs(input_dir, args.recursive)

    if not pdfs:
        print(f"No PDF files found in {input_dir}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    skipped = []

    for pdf in pdfs:
        relative_txt = safe_output_name(pdf, input_dir)
        output_path = output_dir / relative_txt

        if output_path.exists() and not args.overwrite:
            skipped.append(pdf)
            continue

        jobs.append((
            pdf,
            output_path,
            args.ocr,
            args.tesseract,
            args.ocr_dpi,
            args.min_chars_page,
            args.min_words_page,
            args.min_alnum_ratio,
            args.max_replacement_ratio,
            args.max_suspicious_ratio,
        ))

    print(f"PDFs found       : {len(pdfs)}")
    print(f"Already processed: {len(skipped)}")
    print(f"To process       : {len(jobs)}")
    print(f"Workers          : {args.workers}")
    print(f"OCR              : {'enabled' if args.ocr else 'disabled'}")
    print()

    results: list[FileResult] = []

    if args.workers == 1:
        for i, job in enumerate(jobs, 1):
            source_name = Path(job[0]).name
            print(f"[{i}/{len(jobs)}] [START] {source_name} ...", flush=True)
            result = worker(job)
            results.append(result)

            ocr_info = f", {result.pages_ocr} OCR" if result.pages_ocr else ""
            print(
                f"[{i}/{len(jobs)}] "
                f"[{result.status:<4}] "
                f"{source_name} "
                f"({result.pages}p, {result.elapsed_seconds:.1f}s{ocr_info})"
            )
    else:
        # Each worker opens/closes its own PDF, avoiding shared PyMuPDF state.
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(worker, job): job[0]
                for job in jobs
            }

            completed = 0
            for future in as_completed(future_map):
                completed += 1
                source = future_map[future]

                try:
                    result = future.result()
                except Exception as exc:
                    result = FileResult(
                        source=str(source),
                        status="FAIL",
                        reason="WORKER_ERROR",
                        errors=[f"{type(exc).__name__}: {exc}"],
                    )

                results.append(result)

                ocr_info = f", {result.pages_ocr} OCR" if result.pages_ocr else ""
                print(
                    f"[{completed}/{len(jobs)}] "
                    f"[{result.status:<4}] "
                    f"{Path(result.source).name} "
                    f"({result.pages}p, {result.elapsed_seconds:.1f}s{ocr_info})"
                )

    results.sort(key=lambda r: r.source.lower())

    # Reports live at the root of the output directory.
    write_csv(results, output_dir / "_pdf_extraction_report.csv")
    write_jsonl(results, output_dir / "_pdf_extraction_report.jsonl")
    write_followup_report(results, output_dir / "_FOLLOW_UP.md")

    # A small batch metadata file makes downstream automation easier.
    metadata = {
        "tool": "robust-pdf-to-text",
        "version": "1.0.0",
        "input_directory": str(input_dir),
        "output_directory": str(output_dir),
        "recursive": args.recursive,
        "ocr": args.ocr,
        "ocr_dpi": args.ocr_dpi,
        "workers": args.workers,
        "files_found": len(pdfs),
        "files_skipped": len(skipped),
        "files_processed": len(results),
        "pass": sum(r.status == "PASS" for r in results),
        "warn": sum(r.status == "WARN" for r in results),
        "fail": sum(r.status == "FAIL" for r in results),
        "generated_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
    }

    (output_dir / "_batch_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print_summary(results)

    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
