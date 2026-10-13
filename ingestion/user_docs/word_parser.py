"""
word_parser.py - Robust Parser for Legacy Word (.doc) and Modern Word (.docx) Documents.

Supports:
1. Legacy Word 97-2003 (.doc) binary format via pure-Python OLE2 / Compound File Binary Format (CFBF).
   - Extracts OLE Property Sets (Title, Author, Subject, Creation Date, Page Count, Word Count).
   - Parses Word File Information Block (FIB) and Piece Table (Clx / Plcfpcd).
   - Decodes compressed 8-bit CP1252 and uncompressed 16-bit UTF-16LE text streams.
   - Cleans Word control codes, table cell markers (\x07), page breaks (\x0c), and fields.
   - Includes heuristic stream scanner fallback and optional Windows COM fallback for maximum resilience.
2. Modern Word OpenXML (.docx) format via python-docx.
   - Preserves headings (#, ##), paragraphs, bullet lists, and tables (formatted as Markdown tables).
   - Extracts core properties (Title, Author, Created, Modified).
"""

from __future__ import annotations

import io
import os
import re
import struct
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    import olefile
except ImportError:
    olefile = None

try:
    import docx
except ImportError:
    docx = None

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


OLE2_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
ZIP_MAGIC = b"PK\x03\x04"


def is_word_binary_doc(file_path: Path) -> bool:
    """Checks whether the file is an OLE2 binary Word .doc file."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
            if header != OLE2_MAGIC:
                return False
        if olefile and olefile.isOleFile(str(file_path)):
            with olefile.OleFileIO(str(file_path)) as ole:
                return ole.exists("WordDocument")
        return False
    except Exception:
        return False


def is_word_docx(file_path: Path) -> bool:
    """Checks whether the file is a Word OpenXML .docx file."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
            if header != ZIP_MAGIC:
                return False
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as z:
                return "word/document.xml" in z.namelist()
        return False
    except Exception:
        return False


def clean_word_text(text: str) -> str:
    """
    Cleans Word special control characters:
    - Normalizes paragraph breaks (\r -> \n)
    - Converts table cell delimiters (\x07) to tabs or pipes
    - Converts form feed (\x0c) to page break marker
    - Converts vertical tab / shift-enter (\x0b) to \n
    - Resolves or strips field codes (\x13, \x14, \x15)
    - Strips non-printable ASCII characters < 32
    """
    # Clean Word field codes: \x13 ... \x14 ... \x15
    # Word puts field instructions (e.g. HYPERLINK "...") between \x13 and \x14,
    # and displayed result text between \x14 and \x15.
    def clean_fields(s: str) -> str:
        # Replace field structure: keep content between \x14 and \x15
        s = re.sub(r"\x13[^\x14\x15]*\x14([^\x15]*)\x15", r"\1", s)
        # Any remaining lone field markers
        s = re.sub(r"[\x13\x14\x15]", "", s)
        return s

    text = clean_fields(text)

    # Convert table cells
    # Multiple \x07 in succession often end a table row
    text = re.sub(r"\x07\x07+", "\n", text)
    text = text.replace("\x07", " | ")

    # Page breaks and section breaks
    text = text.replace("\x0c", "\n\n--- PAGE BREAK ---\n\n")

    # Line breaks and paragraph breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")

    # Remove non-printable control characters below 32 (except \t and \n)
    text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)

    # Normalize multiple blank lines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_doc_piece_table(word_doc_bytes: bytes, table_bytes: bytes) -> str:
    """
    Extracts text from WordDocument and Table streams using the FIB Piece Table.
    Follows [MS-DOC]: Word (.doc) Binary File Format specification.
    """
    if len(word_doc_bytes) < 426:
        raise ValueError("WordDocument stream too short to contain FIB.")

    wIdent, nFib = struct.unpack_from("<HH", word_doc_bytes, 0)
    if wIdent not in (0xA5EC, 0xA5DC):
        raise ValueError(f"Unrecognized WordDocument magic: 0x{wIdent:04X}")

    # Word 6.0/95 direct storage
    if wIdent == 0xA5DC:
        fcMin = struct.unpack_from("<I", word_doc_bytes, 24)[0]
        ccpText = struct.unpack_from("<I", word_doc_bytes, 76)[0]
        raw_bytes = word_doc_bytes[fcMin : fcMin + ccpText]
        return raw_bytes.decode("cp1252", errors="replace")

    # Word 97-2003 (wIdent == 0xA5EC)
    fcMin = struct.unpack_from("<I", word_doc_bytes, 24)[0]
    ccpText = struct.unpack_from("<I", word_doc_bytes, 76)[0]
    fcClx = struct.unpack_from("<I", word_doc_bytes, 418)[0]
    lcbClx = struct.unpack_from("<I", word_doc_bytes, 422)[0]

    if fcClx + lcbClx > len(table_bytes):
        raise ValueError(f"Clx offset outside table stream: {fcClx} + {lcbClx} > {len(table_bytes)}")

    clx = table_bytes[fcClx : fcClx + lcbClx]
    pos = 0
    pieces: List[str] = []

    while pos < len(clx):
        clxt = clx[pos]
        pos += 1
        if clxt == 0x01:  # Prc (property modifier)
            if pos + 2 > len(clx):
                break
            cbPrc = struct.unpack_from("<H", clx, pos)[0]
            pos += 2 + cbPrc
        elif clxt == 0x02:  # Pcdt (Piece Descriptor Table)
            if pos + 4 > len(clx):
                break
            lcb = struct.unpack_from("<I", clx, pos)[0]
            pos += 4
            plcfpcd = clx[pos : pos + lcb]

            # In Plcfpcd: (n + 1) * 4 bytes of CP + n * 8 bytes of Pcd
            # Total lcb = 12n + 4
            n = (len(plcfpcd) - 4) // 12
            if n <= 0:
                break

            cps = [struct.unpack_from("<I", plcfpcd, i * 4)[0] for i in range(n + 1)]
            pcd_start = (n + 1) * 4

            for i in range(n):
                fc = struct.unpack_from("<I", plcfpcd, pcd_start + i * 8 + 2)[0]
                cp_len = cps[i + 1] - cps[i]
                is_compressed = bool(fc & 0x40000000)
                actual_fc = fc & ~0x40000000

                if is_compressed:
                    raw_fc = actual_fc // 2
                    chunk = word_doc_bytes[raw_fc : raw_fc + cp_len]
                    text = chunk.decode("cp1252", errors="replace")
                else:
                    raw_fc = actual_fc
                    chunk = word_doc_bytes[raw_fc : raw_fc + cp_len * 2]
                    text = chunk.decode("utf-16-le", errors="replace")
                pieces.append(text)
            break

    if not pieces:
        raise ValueError("No text pieces found in Piece Table.")

    full_text = "".join(pieces)
    # If ccpText is valid and non-zero, the main document is the first ccpText characters
    if ccpText > 0 and len(full_text) >= ccpText:
        full_text = full_text[:ccpText]

    return full_text


def scan_printable_strings(raw_bytes: bytes, min_len: int = 4) -> str:
    """
    Fallback heuristic scanner for extracting printable strings from binary data.
    Decodes runs of UTF-16LE and ASCII/CP-1252 printable characters.
    """
    found_lines: List[str] = []

    # 1. UTF-16LE scanner (Word uses wide characters)
    utf16_pattern = re.compile(rb"(?:[\x20-\x7E]\x00){" + str(min_len).encode() + rb",}")
    for m in utf16_pattern.finditer(raw_bytes):
        try:
            decoded = m.group(0).decode("utf-16-le", errors="ignore").strip()
            if len(decoded) >= min_len:
                found_lines.append(decoded)
        except Exception:
            pass

    # 2. ASCII / CP1252 scanner
    ascii_pattern = re.compile(rb"[\x20-\x7E\r\n\t]{" + str(min_len).encode() + rb",}")
    for m in ascii_pattern.finditer(raw_bytes):
        try:
            decoded = m.group(0).decode("cp1252", errors="ignore").strip()
            if len(decoded) >= min_len:
                found_lines.append(decoded)
        except Exception:
            pass

    # Deduplicate and sort by order of occurrence
    seen = set()
    unique_lines: List[str] = []
    for line in found_lines:
        line_clean = line.strip()
        if len(line_clean) >= min_len and line_clean not in seen:
            seen.add(line_clean)
            unique_lines.append(line_clean)

    return "\n\n".join(unique_lines)


def extract_doc_via_win32com(file_path: Path) -> str:
    """Optional Windows COM fallback using Word.Application in headless mode."""
    if not HAS_WIN32COM:
        return ""
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(file_path.resolve()), ReadOnly=True, ConfirmConversions=False)
        text = doc.Content.Text
        doc.Close(False)
        return text or ""
    except Exception:
        return ""
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


def extract_word_doc(file_path: Path) -> Dict[str, Any]:
    """
    Parses a legacy Microsoft Word 97-2003 (.doc) binary file.
    Extracts text, metadata (title, author, creation date), and structure.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if olefile is None:
        raise ImportError("olefile package is required to parse .doc files.")

    metadata: Dict[str, Any] = {
        "title": None,
        "author": None,
        "subject": None,
        "comments": None,
        "created_date": None,
        "last_saved_date": None,
        "page_count": 1,
        "word_count": 0,
        "char_count": 0,
    }

    raw_text = ""
    extraction_method = "none"

    with olefile.OleFileIO(str(file_path)) as ole:
        # 1. Extract OLE Metadata
        try:
            meta = ole.get_metadata()
            if meta:
                # Decode bytes to str if needed
                def _decode_prop(val: Any) -> Optional[str]:
                    if val is None:
                        return None
                    if isinstance(val, bytes):
                        return val.decode("utf-8", errors="replace").strip()
                    return str(val).strip()

                t = _decode_prop(meta.title)
                if t and len(t) > 2:
                    metadata["title"] = t

                a = _decode_prop(meta.author)
                if a and len(a) > 1:
                    metadata["author"] = a

                s = _decode_prop(meta.subject)
                if s:
                    metadata["subject"] = s

                if meta.create_time:
                    metadata["created_date"] = str(meta.create_time)[:10]  # YYYY-MM-DD
                elif meta.last_saved_time:
                    metadata["created_date"] = str(meta.last_saved_time)[:10]

                if meta.num_pages and meta.num_pages > 0:
                    metadata["page_count"] = meta.num_pages
                if meta.num_words and meta.num_words > 0:
                    metadata["word_count"] = meta.num_words
                if meta.num_chars and meta.num_chars > 0:
                    metadata["char_count"] = meta.num_chars
        except Exception:
            pass

        # 2. Extract Text via Piece Table
        try:
            if ole.exists("WordDocument"):
                word_doc_bytes = ole.openstream("WordDocument").read()
                # Determine table stream (flags & 0x0200)
                flags = struct.unpack_from("<H", word_doc_bytes, 10)[0]
                table_stream_name = "1Table" if (flags >> 9) & 1 else "0Table"

                if ole.exists(table_stream_name):
                    table_bytes = ole.openstream(table_stream_name).read()
                    raw_text = extract_doc_piece_table(word_doc_bytes, table_bytes)
                    extraction_method = "olefile_piece_table"
                elif struct.unpack_from("<H", word_doc_bytes, 0)[0] == 0xA5DC:
                    # Word 6/95 without table stream
                    fcMin = struct.unpack_from("<I", word_doc_bytes, 24)[0]
                    ccpText = struct.unpack_from("<I", word_doc_bytes, 76)[0]
                    raw_text = word_doc_bytes[fcMin : fcMin + ccpText].decode("cp1252", errors="replace")
                    extraction_method = "olefile_word6"
        except Exception as e:
            raw_text = ""

        # 3. Fallback Heuristic Scanner
        if not raw_text.strip():
            try:
                if ole.exists("WordDocument"):
                    word_doc_bytes = ole.openstream("WordDocument").read()
                    raw_text = scan_printable_strings(word_doc_bytes)
                    extraction_method = "olefile_stream_scanner"
            except Exception:
                pass

    # 4. Fallback to Windows COM if available and text is still empty
    if not raw_text.strip() and HAS_WIN32COM:
        com_text = extract_doc_via_win32com(file_path)
        if com_text.strip():
            raw_text = com_text
            extraction_method = "win32com"

    cleaned_text = clean_word_text(raw_text)

    # Calculate actual words and characters
    actual_words = len(re.findall(r"\b\w+\b", cleaned_text))
    actual_chars = len(cleaned_text)

    if metadata["word_count"] == 0:
        metadata["word_count"] = actual_words
    if metadata["char_count"] == 0:
        metadata["char_count"] = actual_chars

    return {
        "raw_text": cleaned_text,
        "title": metadata["title"],
        "author": metadata["author"],
        "created_date": metadata["created_date"],
        "page_count": metadata["page_count"],
        "word_count": metadata["word_count"],
        "char_count": metadata["char_count"],
        "format": "doc",
        "extraction_method": extraction_method,
    }


def extract_word_docx(file_path: Path) -> Dict[str, Any]:
    """
    Parses a modern Microsoft Word OpenXML (.docx) file.
    Extracts structured text with headings, markdown tables, and core properties.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    metadata: Dict[str, Any] = {
        "title": None,
        "author": None,
        "created_date": None,
        "page_count": 1,
        "word_count": 0,
        "char_count": 0,
    }

    elements: List[str] = []

    if docx is not None:
        try:
            doc = docx.Document(str(file_path))

            # Extract Core Properties
            props = doc.core_properties
            if props.title and len(props.title.strip()) > 2:
                metadata["title"] = props.title.strip()
            if props.author and len(props.author.strip()) > 1:
                metadata["author"] = props.author.strip()
            if props.created:
                metadata["created_date"] = str(props.created)[:10]

            # Extract paragraphs and headings
            for p in doc.paragraphs:
                p_text = p.text.strip()
                if not p_text:
                    continue

                style_name = (p.style.name or "").lower() if p.style else ""
                if "heading 1" in style_name or "title" in style_name:
                    elements.append(f"# {p_text}")
                elif "heading 2" in style_name:
                    elements.append(f"## {p_text}")
                elif "heading 3" in style_name:
                    elements.append(f"### {p_text}")
                elif "list" in style_name or "bullet" in style_name:
                    elements.append(f"- {p_text}")
                else:
                    elements.append(p_text)

            # Extract tables as formatted Markdown tables
            for table in doc.tables:
                rows_text: List[List[str]] = []
                for row in table.rows:
                    cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                    if any(cells):
                        rows_text.append(cells)

                if rows_text:
                    col_count = max(len(r) for r in rows_text)
                    table_lines: List[str] = []
                    header = rows_text[0]
                    # Pad header if needed
                    while len(header) < col_count:
                        header.append("")
                    table_lines.append("| " + " | ".join(header) + " |")
                    table_lines.append("| " + " | ".join(["---"] * col_count) + " |")
                    for row in rows_text[1:]:
                        while len(row) < col_count:
                            row.append("")
                        table_lines.append("| " + " | ".join(row) + " |")

                    elements.append("\n" + "\n".join(table_lines) + "\n")

        except Exception as e:
            # Fallback to direct zip xml parsing if docx fails
            elements = []

    # Fallback to raw XML in docx ZIP if python-docx failed
    if not elements and zipfile.is_zipfile(file_path):
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                if "word/document.xml" in z.namelist():
                    xml_content = z.read("word/document.xml").decode("utf-8", errors="replace")
                    # Convert w:p to newline, strip tags
                    xml_paragraphs = re.findall(r"<w:p\b[^>]*>(.*?)</w:p>", xml_content, re.DOTALL)
                    for p_xml in xml_paragraphs:
                        text_parts = re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", p_xml)
                        p_text = "".join(text_parts).strip()
                        if p_text:
                            elements.append(p_text)
        except Exception:
            pass

    full_text = clean_word_text("\n\n".join(elements))
    actual_words = len(re.findall(r"\b\w+\b", full_text))
    actual_chars = len(full_text)

    metadata["word_count"] = actual_words
    metadata["char_count"] = actual_chars

    return {
        "raw_text": full_text,
        "title": metadata["title"],
        "author": metadata["author"],
        "created_date": metadata["created_date"],
        "page_count": metadata["page_count"],
        "word_count": metadata["word_count"],
        "char_count": metadata["char_count"],
        "format": "docx",
        "extraction_method": "python_docx",
    }
