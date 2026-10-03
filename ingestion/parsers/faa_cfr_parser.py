"""
FAA 14 CFR XML Parser and Chunking Module.

Parses Government Publishing Office (GPO) Code of Federal Regulations (CFR) Title 14 XML volumes
(e.g., CFR-2025-title14-vol1.xml, vol2.xml, vol3.xml) and aligns the parsing and chunking strategy
with the established EASA / Formex pipeline.

Key architectural design:
1. Splits multi-regulation CFR volumes by <PART> into discrete, self-contained regulation documents.
2. Extracts hierarchical context paths: [Title 14 Part, Subpart, Subject Group, Section].
3. Chunks at the <SECTION> level with intelligent splitting for massive definitions dictionaries
   (e.g., § 1.1) and multi-part appendices.
4. Normalizes GPO typography (unicode spaces, em-dashes, inline formatting).
5. Converts <GPOTABLE> elements into standard Markdown tables.
6. Populates sequential pointers (previous_chunk_id, next_chunk_id) to enable LLM context retrieval.
"""

import sys
import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------
RE_PART_NUM = re.compile(r'\b(?:PART|Pt\.)\s*(\d+[A-Z]?)\b', re.IGNORECASE)
RE_SECT_NUM = re.compile(r'§+\s*([0-9]+(?:\.[0-9]+)?(?:-[0-9]+(?:\.[0-9]+)?)?)')
RE_THIN_SPACE = re.compile(r'[\u2009\u00a0\u2002\u2003\u200a]')
RE_MULTI_SPACE = re.compile(r'[ \t]+')


# ---------------------------------------------------------------------------
# Text Normalization & Extraction Utilities
# ---------------------------------------------------------------------------

def normalize_text(text: Optional[str]) -> str:
    """Normalizes GPO typography and whitespace."""
    if not text:
        return ""
    text = RE_THIN_SPACE.sub(" ", text)
    text = text.replace('\u2014', ' - ').replace('\u2013', ' - ')
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    lines = [RE_MULTI_SPACE.sub(' ', line).strip() for line in text.split('\n')]
    return "\n".join(l for l in lines if l)


def elem_to_text(elem: Optional[ET.Element]) -> str:
    """Recursively extract plain text from an XML element, ignoring page break tags."""
    if elem is None:
        return ""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if child.tag == 'PRTPAGE':
            continue
        parts.append(elem_to_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def table_to_markdown(table_elem: ET.Element) -> str:
    """Converts a CFR <GPOTABLE> into a clean Markdown table string."""
    headers = []
    boxhd = table_elem.find('.//BOXHD')
    if boxhd is not None:
        for ched in boxhd.findall('.//CHED'):
            h_text = normalize_text(elem_to_text(ched)).replace('\n', ' ')
            headers.append(h_text if h_text else f"Col {len(headers)+1}")
            
    rows = []
    for row in table_elem.findall('.//ROW'):
        row_cells = []
        for ent in row.findall('.//ENT'):
            c_text = normalize_text(elem_to_text(ent)).replace('\n', ' ')
            row_cells.append(c_text)
        if any(row_cells):
            rows.append(row_cells)
            
    if not rows and not headers:
        return normalize_text(elem_to_text(table_elem))
        
    num_cols = max(len(headers), max((len(r) for r in rows), default=0))
    if not num_cols:
        return ""
        
    while len(headers) < num_cols:
        headers.append(f"Col {len(headers)+1}")
        
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * num_cols) + " |")
    for r in rows:
        while len(r) < num_cols:
            r.append("")
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def extract_body_blocks(container_elem: ET.Element, ignore_tags: Set[str]) -> List[str]:
    """Extracts sequential paragraphs, tables, and extracts from a container element."""
    blocks = []
    for child in container_elem:
        if child.tag in ignore_tags or child.tag == 'PRTPAGE':
            continue
        elif child.tag == 'GPOTABLE':
            t_md = table_to_markdown(child)
            if t_md:
                blocks.append(t_md)
        elif child.tag in ('P', 'FP'):
            p_text = normalize_text(elem_to_text(child))
            if p_text:
                blocks.append(p_text)
        elif child.tag == 'EXTRACT':
            for sub in child:
                if sub.tag in ('P', 'FP'):
                    p_text = normalize_text(elem_to_text(sub))
                    if p_text:
                        blocks.append(f"> {p_text}")
                elif sub.tag == 'GPOTABLE':
                    t_md = table_to_markdown(sub)
                    if t_md:
                        blocks.append(t_md)
        elif child.tag == 'EDNOTE':
            note_text = normalize_text(elem_to_text(child))
            if note_text:
                blocks.append(f"[Editorial Note: {note_text}]")
        elif child.tag == 'NOTE':
            note_text = normalize_text(elem_to_text(child))
            if note_text:
                blocks.append(f"> Note: {note_text}")
        elif child.tag == 'MATH':
            m_text = normalize_text(elem_to_text(child))
            if m_text:
                blocks.append(f"[Formula: {m_text}]")
        elif child.tag == 'RESERVED':
            blocks.append("[Reserved]")
    return blocks


# ---------------------------------------------------------------------------
# Section and Definition Extraction
# ---------------------------------------------------------------------------

def extract_definitions_from_section(sec_node: ET.Element) -> List[Tuple[str, str]]:
    """
    Detects if a section is a definitions glossary (like § 1.1) and extracts
    individual (term, definition_text) tuples.
    """
    defs = []
    for p_elem in sec_node.findall('./P'):
        e = p_elem.find('./E')
        if e is not None and e.get('T') in ('03', '04'):
            term = normalize_text(elem_to_text(e))
            txt = normalize_text(elem_to_text(p_elem))
            if term and len(term) < 120 and txt:
                defs.append((term, txt))
    return defs


def extract_section_content(sec_elem: ET.Element) -> Tuple[str, Dict[str, Any]]:
    """Extracts clean section body text and metadata (citations, future effective dates)."""
    metadata: Dict[str, Any] = {}
    
    cita = sec_elem.find('CITA')
    if cita is not None:
        metadata["cita"] = normalize_text(elem_to_text(cita))
        
    effd = sec_elem.find('EFFDNOTP') or sec_elem.find('EFFDNOT')
    if effd is not None:
        metadata["effective_date_note"] = normalize_text(elem_to_text(effd))
        
    if sec_elem.find('.//STARS') is not None:
        metadata["is_amendment_excerpt"] = True
        
    blocks = extract_body_blocks(sec_elem, {'SECTNO', 'SUBJECT', 'CITA', 'EFFDNOTP', 'EFFDNOT'})
    source_text = "\n\n".join(blocks)
    return source_text, metadata


# ---------------------------------------------------------------------------
# Part Document Parser
# ---------------------------------------------------------------------------

def parse_faa_part(part_elem: ET.Element, volume_name: str, revised_date: str = "2025-01-01") -> Optional[Dict[str, Any]]:
    """
    Parses a single <PART> element into a structured Regulation Document.
    Returns None if the part is reserved or empty.
    """
    ear_raw = elem_to_text(part_elem.find('EAR'))
    hd_raw = elem_to_text(part_elem.find('HD'))
    
    # Skip reserved parts with no regulations
    if not hd_raw and part_elem.find('RESERVED') is not None:
        return None
        
    # Extract Part Number
    part_num = None
    m = RE_PART_NUM.search(ear_raw) or RE_PART_NUM.search(hd_raw)
    if m:
        part_num = m.group(1).upper()
    else:
        m2 = re.search(r'PART\s+(\d+[A-Z]?)', hd_raw, re.IGNORECASE)
        if m2:
            part_num = m2.group(1).upper()
            
    if not part_num:
        return None
        
    # Standardize Document Title
    clean_hd = normalize_text(hd_raw)
    if not clean_hd.startswith("14 CFR"):
        doc_title = f"14 CFR {clean_hd}"
    else:
        doc_title = clean_hd
        
    document_id = f"FAA_14CFR_Part_{part_num}"
    
    auth_text = normalize_text(elem_to_text(part_elem.find('AUTH')))
    source_text = normalize_text(elem_to_text(part_elem.find('SOURCE')))
    
    sections = []
    
    def add_section(sec_node: ET.Element, current_path: List[str]):
        sectno_raw = normalize_text(elem_to_text(sec_node.find('SECTNO')))
        subject_raw = normalize_text(elem_to_text(sec_node.find('SUBJECT')))
        
        if not subject_raw and sec_node.find('RESERVED') is not None:
            subject_raw = normalize_text(elem_to_text(sec_node.find('RESERVED')))
            
        full_sec_title = f"{sectno_raw} {subject_raw}".strip()
        sec_body, meta = extract_section_content(sec_node)
        
        sec_num_match = RE_SECT_NUM.search(sectno_raw)
        sec_numbers = [sec_num_match.group(1)] if sec_num_match else []
        
        section_path = list(current_path)
        if full_sec_title:
            section_path.append(full_sec_title)
            
        # Check if this is a definitions dictionary
        defs = []
        if "definitions" in full_sec_title.lower() and len(sec_node.findall('./P')) > 15:
            defs = extract_definitions_from_section(sec_node)
            
        sections.append({
            "type": "definitions" if defs else "section",
            "sectno": sectno_raw,
            "section_number": sec_numbers[0] if sec_numbers else "",
            "subject": subject_raw,
            "full_title": full_sec_title,
            "section_path": section_path,
            "section_numbers": sec_numbers,
            "source_text": sec_body,
            "metadata": meta,
            "definitions": defs,
        })

    def add_appendix(app_node: ET.Element, current_path: List[str]):
        ear = normalize_text(elem_to_text(app_node.find('EAR')))
        hd = normalize_text(elem_to_text(app_node.find('HD')))
        app_title = hd or ear or "Appendix"
        
        # Check if the appendix has multiple distinct major sub-headings
        sub_headings = app_node.findall('.//HD')
        has_major_subheadings = any(h.get('SOURCE') in ('HD1', 'HD2') for h in sub_headings)
        
        if has_major_subheadings and len(app_node.findall('.//P')) > 20:
            # Multi-part appendix: split into sub-headings
            current_sub_hd = app_title
            current_blocks = []
            sub_idx = 0
            
            for child in app_node:
                if child.tag in ('EAR', 'PRTPAGE'):
                    continue
                elif child.tag == 'HD' and child.get('SOURCE') in ('HD1', 'HD2'):
                    if current_blocks:
                        part_body = "\n\n".join(current_blocks)
                        sub_path = list(current_path) + [app_title, current_sub_hd]
                        sections.append({
                            "type": "appendix",
                            "sectno": f"{ear or app_title} ({current_sub_hd})",
                            "section_number": f"{ear or 'App'}_{sub_idx}",
                            "subject": current_sub_hd,
                            "full_title": f"{app_title} - {current_sub_hd}",
                            "section_path": sub_path,
                            "section_numbers": [],
                            "source_text": part_body,
                            "metadata": {"is_appendix": True, "appendix_parent": app_title},
                        })
                        sub_idx += 1
                        current_blocks = []
                    current_sub_hd = normalize_text(elem_to_text(child))
                elif child.tag == 'GPOTABLE':
                    t_md = table_to_markdown(child)
                    if t_md: current_blocks.append(t_md)
                elif child.tag in ('P', 'FP'):
                    p_text = normalize_text(elem_to_text(child))
                    if p_text: current_blocks.append(p_text)
                elif child.tag in ('EDNOTE', 'NOTE'):
                    n_text = normalize_text(elem_to_text(child))
                    if n_text: current_blocks.append(f"> Note: {n_text}")
                    
            if current_blocks:
                part_body = "\n\n".join(current_blocks)
                sub_path = list(current_path) + [app_title, current_sub_hd]
                sections.append({
                    "type": "appendix",
                    "sectno": f"{ear or app_title} ({current_sub_hd})",
                    "section_number": f"{ear or 'App'}_{sub_idx}",
                    "subject": current_sub_hd,
                    "full_title": f"{app_title} - {current_sub_hd}",
                    "section_path": sub_path,
                    "section_numbers": [],
                    "source_text": part_body,
                    "metadata": {"is_appendix": True, "appendix_parent": app_title},
                })
        else:
            # Single-part or compact appendix
            blocks = extract_body_blocks(app_node, {'EAR', 'HD'})
            app_body = "\n\n".join(blocks)
            app_path = list(current_path) + [app_title]
            sections.append({
                "type": "appendix",
                "sectno": ear or app_title,
                "section_number": ear or app_title,
                "subject": app_title,
                "full_title": app_title,
                "section_path": app_path,
                "section_numbers": [],
                "source_text": app_body,
                "metadata": {"is_appendix": True},
            })

    # Hierarchical tree walk
    base_path = [doc_title]
    
    for child in part_elem:
        if child.tag == 'SECTION':
            add_section(child, base_path)
        elif child.tag == 'SUBPART':
            sp_hd = normalize_text(elem_to_text(child.find('HD')))
            sp_path = list(base_path)
            if sp_hd:
                sp_path.append(sp_hd)
            for sp_child in child:
                if sp_child.tag == 'SECTION':
                    add_section(sp_child, sp_path)
                elif sp_child.tag == 'SUBJGRP':
                    sg_hd = normalize_text(elem_to_text(sp_child.find('HD')))
                    sg_path = list(sp_path)
                    if sg_hd:
                        sg_path.append(sg_hd)
                    for sg_child in sp_child:
                        if sg_child.tag == 'SECTION':
                            add_section(sg_child, sg_path)
                elif sp_child.tag == 'APPENDIX':
                    add_appendix(sp_child, sp_path)
        elif child.tag == 'SUBJGRP':
            sg_hd = normalize_text(elem_to_text(child.find('HD')))
            sg_path = list(base_path)
            if sg_hd:
                sg_path.append(sg_hd)
            for sg_child in child:
                if sg_child.tag == 'SECTION':
                    add_section(sg_child, sg_path)
        elif child.tag == 'APPENDIX':
            add_appendix(child, base_path)
            
    doc = {
        "document_id": document_id,
        "title": doc_title,
        "part_number": part_num,
        "volume": volume_name,
        "date": revised_date,
        "authority": auth_text,
        "source_note": source_text,
        "sections": sections,
        "sections_count": len(sections),
    }
    return doc


# ---------------------------------------------------------------------------
# Chunking Strategy Aligned with EASA Pipeline
# ---------------------------------------------------------------------------

def generate_faa_chunks(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transforms a parsed FAA Part Document into SQLite/FAISS-aligned chunks.
    Matches schema: (chunk_id, document_id, chunk_type, section_path,
    section_numbers, source_text, embedding_text, parent_chunk_id,
    previous_chunk_id, next_chunk_id, structure_json, references_json, metadata_json).
    """
    document_id = doc["document_id"]
    main_title = doc["title"]
    raw_sections = doc["sections"]
    
    chunks: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    
    def register_chunk(
        chunk_type: str,
        section_path: List[str],
        section_numbers: List[str],
        source_text: str,
        sec_identifier: str,
        sec_title: str,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ):
        if not source_text and not sec_title:
            return
            
        clean_sec_id = re.sub(r'[^a-zA-Z0-9_]', '_', sec_identifier).strip('_')
        base_chunk_id = f"{document_id}:{clean_sec_id}"
        
        # Prevent collisions on duplicate section numbers / amendments
        if base_chunk_id in seen_ids:
            suffix_idx = 1
            while f"{base_chunk_id}_dup{suffix_idx}" in seen_ids:
                suffix_idx += 1
            chunk_id = f"{base_chunk_id}_dup{suffix_idx}"
        else:
            chunk_id = base_chunk_id
        seen_ids.add(chunk_id)
        
        # Format embedding_text exactly as EASA
        context_lines = []
        for p in section_path[1:-1]:
            context_lines.append(f"- {p}")
            
        emb_parts = [f"Document: {main_title}"]
        if context_lines:
            emb_parts.append("Context:\n" + "\n".join(context_lines))
        if sec_title:
            emb_parts.append(f"Section: {sec_title}")
        emb_parts.append(f"\n{source_text}")
        embedding_text = "\n".join(emb_parts)
        
        parent_id = section_path[-2] if len(section_path) > 1 else None
        
        meta = {
            "source": "FAA XML",
            "agency": "FAA",
            "cfr_title": 14,
            "part": doc["part_number"],
            "volume": doc["volume"],
            **(custom_metadata or {})
        }
        
        chunk = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "chunk_type": chunk_type,
            "section_path": json.dumps(section_path),
            "section_numbers": json.dumps(section_numbers),
            "source_text": source_text,
            "embedding_text": embedding_text,
            "parent_chunk_id": parent_id,
            "previous_chunk_id": None,
            "next_chunk_id": None,
            "structure_json": json.dumps({
                "part": doc["part_number"],
                "section": sec_identifier,
                "title": sec_title,
            }),
            "references_json": "[]",
            "metadata_json": json.dumps(meta),
        }
        chunks.append(chunk)

    for sec in raw_sections:
        # Check if this section has individual definitions (e.g. § 1.1)
        defs = sec.get("definitions") or []
        if defs:
            for term, def_text in defs:
                term_slug = re.sub(r'[^a-zA-Z0-9_]', '_', term.lower())
                def_path = list(sec["section_path"]) + [term]
                register_chunk(
                    chunk_type="definition",
                    section_path=def_path,
                    section_numbers=sec["section_numbers"],
                    source_text=def_text,
                    sec_identifier=f"sec_{sec['section_number']}_{term_slug}",
                    sec_title=f"{sec['full_title']} - {term}",
                    custom_metadata={"definition_term": term, **sec.get("metadata", {})},
                )
        else:
            sec_num_str = sec["section_number"] or sec["sectno"]
            register_chunk(
                chunk_type=sec["type"],
                section_path=sec["section_path"],
                section_numbers=sec["section_numbers"],
                source_text=sec["source_text"].strip(),
                sec_identifier=f"sec_{sec_num_str}",
                sec_title=sec["full_title"],
                custom_metadata=sec.get("metadata", {}),
            )
            
    # Sequential linking for adjacent context browsing
    for i, chunk in enumerate(chunks):
        chunk["previous_chunk_id"] = chunks[i-1]["chunk_id"] if i > 0 else None
        chunk["next_chunk_id"] = chunks[i+1]["chunk_id"] if i < len(chunks) - 1 else None
        
    return chunks


# ---------------------------------------------------------------------------
# Volume Processor
# ---------------------------------------------------------------------------

def parse_cfr_volume(xml_file_path: Path) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Streaming processor for a full GPO CFR volume.
    Yields or returns (doc, chunks) for each regulation Part.
    """
    volume_name = xml_file_path.stem
    results = []
    
    # Extract volume revision date from title page if present
    revised_date = "2025-01-01"
    
    context = ET.iterparse(str(xml_file_path), events=('end',))
    for event, elem in context:
        if elem.tag == 'REVISED' or elem.tag == 'DATE':
            txt = normalize_text(elem_to_text(elem))
            if txt:
                revised_date = txt
        elif elem.tag == 'PART':
            doc = parse_faa_part(elem, volume_name, revised_date)
            if doc:
                chunks = generate_faa_chunks(doc)
                results.append((doc, chunks))
            elem.clear()
            
    return results
