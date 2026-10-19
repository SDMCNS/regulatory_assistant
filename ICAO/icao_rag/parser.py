"""PDF parsing engine tailored for ICAO manuals and technical aviation documents."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import fitz  # PyMuPDF

from .config import ParserConfig
from .models import DocumentMetadata, PageData


class PDFParser:
    """Extracts text, structural hierarchy, and metadata from ICAO PDF documents."""

    def __init__(self, config: Optional[ParserConfig] = None):
        self.config = config or ParserConfig()

    def parse_document(self, file_path: str | Path) -> Tuple[DocumentMetadata, List[PageData]]:
        """Parse an entire PDF file and return its DocumentMetadata and PageData list."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF document not found: {path}")

        doc = fitz.open(str(path))
        total_pages = len(doc)
        file_size = path.stat().st_size

        # Deduce title & doc number from filename and first pages
        doc_id, title, edition = self._extract_doc_info(path, doc)

        pages_data: List[PageData] = []
        current_chapter: Optional[str] = None

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1

            page_data, current_chapter = self._parse_page(
                page=page,
                page_num=page_num,
                total_pages=total_pages,
                current_chapter=current_chapter
            )
            pages_data.append(page_data)

        doc.close()

        # Count content pages
        indexed_pages = sum(1 for p in pages_data if p.page_type == "content" and len(p.clean_text) > 30)

        metadata = DocumentMetadata(
            doc_id=doc_id,
            filename=path.name,
            title=title,
            edition=edition,
            total_pages=total_pages,
            indexed_pages=indexed_pages,
            file_size_bytes=file_size,
            file_mtime=path.stat().st_mtime,
            source_path=str(path.resolve())
        )

        return metadata, pages_data

    ICAO_ANNEX_TITLES: Dict[int, str] = {
        1: "Personnel Licensing",
        2: "Rules of the Air",
        3: "Meteorological Service for International Air Navigation",
        4: "Aeronautical Charts",
        5: "Units of Measurement to be Used in Air and Ground Operations",
        6: "Operation of Aircraft",
        7: "Aircraft Nationality and Registration Marks",
        8: "Airworthiness of Aircraft",
        9: "Facilitation",
        10: "Aeronautical Telecommunications",
        11: "Air Traffic Services",
        12: "Search and Rescue",
        13: "Aircraft Accident and Incident Investigation",
        14: "Aerodromes",
        15: "Aeronautical Information Services",
        16: "Environmental Protection",
        17: "Security - Safeguarding International Civil Aviation Against Acts of Unlawful Interference",
        18: "The Safe Transport of Dangerous Goods by Air",
        19: "Safety Management",
    }

    ICAO_DOC_TITLES: Dict[int, str] = {
        4444: "Procedures for Air Navigation Services - Air Traffic Management (PANS-ATM)",
        7030: "Regional Supplementary Procedures",
        7300: "Convention on International Civil Aviation (Chicago Convention)",
        8126: "Aeronautical Information Services Manual",
        8168: "Procedures for Air Navigation Services - Aircraft Operations (PANS-OPS)",
        9328: "Manual of Runway Visual Range Observing and Reporting Practices",
        9432: "Manual of Radiotelephony",
        9501: "Environmental Technical Manual",
        9562: "Airport Economics Manual",
        9574: "Manual on Implementation of a 300 m (1 000 ft) Vertical Separation Minimum Between FL 290 and FL 410 (RVSM)",
        9613: "Performance-based Navigation (PBN) Manual",
        9750: "Global Air Navigation Plan (GANP)",
        9760: "Airworthiness Manual",
        9859: "Safety Management Manual (SMM)",
        9868: "Procedures for Air Navigation Services - Training (PANS-TRG)",
        9965: "Manual on Continuous Descent Operations (CDO)",
        9981: "Procedures for Air Navigation Services - Aerodromes (PANS-Aerodromes)",
        10066: "Procedures for Air Navigation Services - Aeronautical Information Management (PANS-AIM)",
    }

    def _extract_doc_info(self, path: Path, doc: fitz.Document) -> Tuple[str, str, Optional[str]]:
        """Identify standard ICAO document number, title, and edition with comprehensive catalog matching."""
        filename = path.stem.lower()

        sample_text = ""
        for i in range(min(5, len(doc))):
            sample_text += doc[i].get_text() + "\n"

        edition: Optional[str] = None
        ed_match = re.search(r'((?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth)\s+Edition[^\n\r]*)', sample_text, re.IGNORECASE)
        if ed_match:
            edition = ed_match.group(1).strip()
        else:
            amdt_match = re.search(r'((?:Amendment|Amdt)[\s\d\-]+[^\n\r]*)', sample_text, re.IGNORECASE)
            if amdt_match:
                edition = amdt_match.group(1).strip()

        # 1. Chicago Convention
        if "7300" in filename or "convention_on_international" in filename:
            return "ICAO_DOC_7300", "ICAO Doc 7300: Convention on International Civil Aviation (Chicago Convention)", edition or "Eighth Edition, 2000"

        # 2. Check for ICAO Doc manuals (Doc 4444, Doc 8168, 9562, 9750, etc.)
        doc_m = re.search(r'(?:icao[_\s-]*)?doc[_\s-]*(\d+)|^(\d{4})\b', filename)
        if doc_m:
            num = int(doc_m.group(1) or doc_m.group(2))
            base_title = self.ICAO_DOC_TITLES.get(num, f"Doc {num}")
            part_m = re.search(r'(?:part|pt)[_\s-]*([ivxlcdm]+|\d+)', filename)
            vol_m = re.search(r'(?:volume|vol)[_\s-]*([ivxlcdm]+|\d+)', filename)
            if not vol_m:
                vol_m = re.search(r'\bv(\d+)\b', filename)
            if not part_m:
                part_m = re.search(r'\bp(\d+)\b', filename)

            suffix = ""
            vol_str = ""
            part_str = ""
            if vol_m:
                v_val = vol_m.group(1).upper()
                suffix += f" Vol {v_val}"
                vol_str = f"_VOL_{v_val}"
            if part_m:
                p_val = part_m.group(1).upper()
                suffix += f" Part {p_val}"
                part_str = f"_PART_{p_val}"

            doc_id = f"ICAO_DOC_{num}{vol_str}{part_str}"
            return doc_id, f"ICAO Doc {num}: {base_title}{suffix}", edition

        # 3. Check for ICAO Annexes (Annex 1 to 19)
        annex_m = re.search(r'(?:icao[_\s-]*)?annex[_\s-]*(\d+)|\ban(\d{1,2})[_\s-]', filename)
        if annex_m:
            num = int(annex_m.group(1) or annex_m.group(2))
            base_title = self.ICAO_ANNEX_TITLES.get(num, f"Annex {num}")
            part_m = re.search(r'(?:part|pt)[_\s-]*([ivxlcdm]+|\d+)', filename)
            vol_m = re.search(r'(?:volume|vol)[_\s-]*([ivxlcdm]+|\d+)', filename)
            if not vol_m:
                vol_m = re.search(r'\bv(\d+)\b', filename)
            if not part_m:
                part_m = re.search(r'\bp(\d+)\b', filename)

            suffix = ""
            vol_str = ""
            part_str = ""
            if vol_m:
                v_val = vol_m.group(1).upper()
                suffix += f" Vol {v_val}"
                vol_str = f"_VOL_{v_val}"
            if part_m:
                p_val = part_m.group(1).upper()
                suffix += f" Part {p_val}"
                part_str = f"_PART_{p_val}"

            doc_id = f"ICAO_ANNEX_{num}{vol_str}{part_str}"
            return doc_id, f"ICAO Annex {num}: {base_title}{suffix}", edition

        # 4. Fallback: inspect sample text for Doc or Annex patterns
        txt_doc_match = re.search(r'Doc\s+(\d+)\s*\n+([^\n]+)', sample_text, re.IGNORECASE)
        if txt_doc_match:
            d_num = int(txt_doc_match.group(1))
            t_str = self.ICAO_DOC_TITLES.get(d_num, txt_doc_match.group(2).strip())
            return f"ICAO_DOC_{d_num}", f"ICAO Doc {d_num}: {t_str}", edition

        txt_annex_match = re.search(r'Annex\s+(\d+)\s*\n+([^\n]+)', sample_text, re.IGNORECASE)
        if txt_annex_match:
            a_num = int(txt_annex_match.group(1))
            t_str = self.ICAO_ANNEX_TITLES.get(a_num, txt_annex_match.group(2).strip())
            return f"ICAO_ANNEX_{a_num}", f"ICAO Annex {a_num}: {t_str}", edition

        clean_slug = re.sub(r'[^a-zA-Z0-9_]', '_', filename).upper()
        return f"ICAO_{clean_slug}", f"ICAO: {path.stem.replace('_', ' ').title()}", edition

    def _parse_page(
        self,
        page: fitz.Page,
        page_num: int,
        total_pages: int,
        current_chapter: Optional[str]
    ) -> Tuple[PageData, Optional[str]]:
        """Parse a single PDF page with layout and header awareness."""
        raw_text = page.get_text()
        stripped_raw = raw_text.strip()

        if len(stripped_raw) < self.config.min_page_char_count:
            return PageData(
                page_number=page_num,
                raw_text=raw_text,
                clean_text="",
                page_type="blank",
                char_count=0
            ), current_chapter

        # Determine page type
        page_type = "content"
        if page_num <= 3:
            page_type = "cover"
        elif page_num <= 20 and self._is_front_matter(stripped_raw):
            page_type = "front_matter"

        # Extract blocks from page for paragraph boundaries
        # block tuple: (x0, y0, x1, y1, text, block_no, block_type)
        blocks = page.get_text("blocks")
        text_blocks = [b[4].strip() for b in blocks if len(b) > 4 and b[4].strip()]

        running_header, detected_chapter, cleaned_paragraphs = self._process_blocks(
            text_blocks, current_chapter
        )

        detected_sections = self._find_sections(cleaned_paragraphs)
        clean_text = "\n\n".join(cleaned_paragraphs)

        page_data = PageData(
            page_number=page_num,
            raw_text=raw_text,
            clean_text=clean_text,
            page_type=page_type,
            running_header=running_header,
            detected_chapter=detected_chapter or current_chapter,
            detected_sections=detected_sections,
            char_count=len(clean_text)
        )

        return page_data, detected_chapter or current_chapter

    def _is_front_matter(self, text: str) -> bool:
        """Check if page belongs to front matter (TOC, amendments, glossary, foreword)."""
        lower = text.lower()
        front_keywords = [
            "table of contents",
            "amendments",
            "foreword",
            "glossary of terms",
            "list of acronyms",
            "publications;",
            "corrigenda"
        ]
        return any(kw in lower for kw in front_keywords)

    def _process_blocks(
        self,
        blocks: List[str],
        current_chapter: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Filter running headers and footers while extracting chapter tracking."""
        running_header: Optional[str] = None
        detected_chapter = current_chapter
        cleaned_blocks: List[str] = []

        re_chapter = re.compile(r"^(Chapter\s+\d+[\.\:]?\s*.*|PART\s+[IVXLCDM]+[\.\:]?\s*.*)", re.IGNORECASE)
        re_page_num = re.compile(r"^(\d+-\d+|\([ivxlcdm]+\)|\d+|[IVXLCDM]+-\d+-\d+)$", re.IGNORECASE)
        re_doc_title = re.compile(r"^(Airport Economics Manual|Global Air Navigation Plan.*)$", re.IGNORECASE)

        for idx, block in enumerate(blocks):
            # Clean non-breaking spaces and unicode replacement
            b_clean = block.replace("\xa0", " ").replace("\ufffd", "'").replace("\r\n", "\n")

            # Check if top block is a header
            first_line = b_clean.split("\n")[0].strip()
            if idx == 0:
                chap_match = re_chapter.match(first_line)
                if chap_match:
                    detected_chapter = chap_match.group(1).strip()
                    running_header = detected_chapter
                    if self.config.strip_running_headers:
                        # If block only contains header line or page number, skip
                        remaining_lines = [l.strip() for l in b_clean.split("\n")[1:] if l.strip() and not re_page_num.match(l.strip())]
                        if not remaining_lines:
                            continue
                        b_clean = "\n".join(remaining_lines)

                elif re_doc_title.match(first_line) or re_page_num.match(first_line):
                    if self.config.strip_running_headers:
                        remaining_lines = [l.strip() for l in b_clean.split("\n")[1:] if l.strip() and not re_page_num.match(l.strip())]
                        if not remaining_lines:
                            continue
                        b_clean = "\n".join(remaining_lines)

            # Check if bottom block is just a lone page number
            if idx == len(blocks) - 1 and re_page_num.match(b_clean.strip()):
                if self.config.strip_running_headers:
                    continue

            # Clean hyphenation within the block
            if self.config.clean_hyphenation:
                b_clean = re.sub(r"(\b\w+)-\s*\n\s*(\w+\b)", r"\1\2", b_clean)

            # Replace single internal newlines with space, preserving sentences
            lines = [l.strip() for l in b_clean.split("\n") if l.strip()]
            b_text = " ".join(lines)
            b_text = re.sub(r"[ \t]{2,}", " ", b_text)

            if len(b_text) > 10:
                cleaned_blocks.append(b_text)

        return running_header, detected_chapter, cleaned_blocks

    def _find_sections(self, paragraphs: List[str]) -> List[str]:
        """Detect section headers in extracted paragraphs."""
        sections = []
        section_pattern = re.compile(r"^(\d+\.\d+(\.\d+)?\s+[A-Z][^\.]{3,60})")
        for p in paragraphs:
            match = section_pattern.match(p.strip())
            if match:
                sections.append(match.group(1).strip())
        return sections
