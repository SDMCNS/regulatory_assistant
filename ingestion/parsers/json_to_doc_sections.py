import sys
import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.core.config import settings
from ingestion.parsers.json_to_doc import find_json_file

# ==============================================================================
# Section Break Formatting
# ==============================================================================

def make_section_break(meta: Optional[Dict[str, Any]] = None) -> str:
    """
    Creates a section break formatted as a Markdown horizontal rule accompanied by
    an HTML comment containing metadata JSON.
    
    In standard Markdown renderers (marked.js, GitHub), the comment is invisible
    and the '---' renders a visual divider line.
    
    In frontend code, splitting on the comment enables rendering individual sections
    as collapsible cards, tabs, or distinct blocks.
    """
    if meta:
        # Compact JSON serialization of metadata (id, title, type, etc.)
        meta_json = json.dumps(meta, ensure_ascii=False)
        return f"\n\n---\n<!-- SECTION_BREAK {meta_json} -->\n\n"
    return "\n\n---\n<!-- SECTION_BREAK -->\n\n"

# ==============================================================================
# Formex Rendering with Section Breaks
# ==============================================================================

def render_formex_content(node, level=1):
    lines = []
    if isinstance(node, list):
        for child in node:
            lines.extend(render_formex_content(child, level))
        return lines

    if not isinstance(node, dict):
        return lines

    node_type = node.get("type", "")
    
    if node_type == "article":
        num = node.get("number", "")
        article_title = f"Article {num}" if not str(num).lower().startswith("article") else num
        lines.append(make_section_break({"type": "article", "title": article_title, "number": num}))
        lines.append(f"## {num}\n\n")
        if "text" in node:
            lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "section":
        title = node.get("title", "")
        num = node.get("number", "")
        heading = f"{num} {title}".strip()
        lines.append(make_section_break({"type": "section", "title": heading, "number": num}))
        if heading:
            lines.append(f"{'#' * min(level + 1, 6)} {heading}\n\n")
        if "text" in node:
            lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "paragraph":
        num = node.get("number", "")
        prefix = f"**{num}** " if num else ""
        if "text" in node:
            lines.append(f"{prefix}{node['text']}\n\n")
        if "content" in node:
            if not "text" in node and num:
                lines.append(f"{prefix}\n")
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "item":
        num = node.get("number", "")
        text = node.get("text", "")
        prefix = f"{num} " if num else ""
        lines.append(f"* {prefix}{text}\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "list":
        if "items" in node:
            for item in node["items"]:
                lines.extend(render_formex_content(item, level + 1))
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
        lines.append("\n")
        
    elif node_type == "quote":
        if "content" in node:
            quote_lines = render_formex_content(node["content"], level)
            for ql in quote_lines:
                if ql.strip():
                    lines.append(f"> {ql.strip()}\n")
            lines.append("\n")
                    
    elif node_type == "text":
        lines.append(node.get("text", "") + "\n\n")
        
    elif node_type == "signature":
        lines.append(make_section_break({"type": "signature", "title": "Signature"}))
        lines.append(node.get("place_and_date", "") + "\n\n")
        for sig in node.get("signatories", []):
            lines.append(sig + "\n")
            
    elif "text" in node:
        lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level))
            
    return lines

def render_formex_sections(data: Dict[str, Any]) -> str:
    lines = []
    doc_title = data.get('title', 'Unknown Title')
    lines.append(f"# DOCUMENT: {doc_title}\n\n")
    
    metadata = data.get("metadata", {})
    if metadata.get('date'):
        lines.append(f"**Date:** {metadata.get('date')}\n\n")
        
    preamble = data.get("preamble", {})
    if preamble:
        lines.append(make_section_break({"type": "preamble", "title": "Preamble"}))
        lines.append("## Preamble\n\n")
        if "initial" in preamble:
            lines.append(preamble["initial"] + "\n\n")
        for visa in preamble.get("visas", []):
            lines.append(visa + "\n\n")
        if "recitals_intro" in preamble:
            lines.append(preamble["recitals_intro"] + "\n\n")
        for recital in preamble.get("recitals", []):
            lines.extend(render_formex_content(recital))
        lines.append("\n")
        if "final" in preamble:
            lines.append(preamble["final"] + "\n\n")
            
    body = data.get("body", [])
    if body:
        lines.extend(render_formex_content(body))
        
    annexes = data.get("annexes", [])
    for idx, annex in enumerate(annexes):
        annex_title = annex.get('title', f'Annex {idx + 1}')
        lines.append(make_section_break({"type": "annex", "title": annex_title}))
        lines.append(f"# ANNEX: {annex_title}\n\n")
        if "content" in annex:
            lines.extend(render_formex_content(annex["content"]))
            
    final = data.get("final", {})
    if final:
        lines.append(make_section_break({"type": "final", "title": "Final Provisions"}))
        lines.extend(render_formex_content(final.get("content", [])))
        
    notes = data.get("notes", {})
    if notes:
        lines.append(make_section_break({"type": "notes", "title": "Notes"}))
        lines.append("## Notes\n\n")
        for k, v in notes.items():
            lines.append(f"[{k}]: {v}\n\n")
            
    return "".join(lines)

# ==============================================================================
# EASA Rendering with Section Breaks
# ==============================================================================

def render_easa_sections(data: Any, title: Optional[str] = None) -> str:
    lines = []
    
    if isinstance(data, list):
        doc_title = title
        if not doc_title:
            for item in data:
                if isinstance(item, dict) and item.get("meta", {}).get("subject"):
                    doc_title = item["meta"]["subject"].rstrip(";")
                    break
        doc_title = doc_title or "Unknown EASA Title"
        lines.append(f"# DOCUMENT: {doc_title}\n\n")
        
        current_heading = None
        for item in data:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", {})
            text = item.get("text", "").strip()
            t_type = meta.get("type", "")
            t_title = meta.get("title", "").strip()
            t_id = meta.get("id", "")
            
            # Check if first line of text is redundant with t_title
            lines_in_text = text.split("\n")
            first_line = lines_in_text[0].strip() if lines_in_text else ""
            t_title_norm = re.sub(r'\s+', ' ', t_title).strip().lower()
            first_line_norm = re.sub(r'\s+', ' ', first_line).strip().lower()
            
            if t_title_norm and t_title_norm == first_line_norm:
                body_text = "\n".join(lines_in_text[1:]).strip()
            else:
                body_text = text
            
            # Construct section metadata payload
            section_meta = {
                "id": t_id,
                "title": t_title or first_line,
                "type": t_type if t_type else "section",
                "parent_heading": current_heading
            }
            
            if t_type == "heading":
                current_heading = t_title
                heading_title = t_title or first_line
                
                # Introduce section break before major heading
                lines.append(make_section_break(section_meta))
                if heading_title:
                    lines.append(f"## {heading_title}\n\n")
                if body_text and body_text != heading_title:
                    lines.append(f"{body_text}\n\n")
            else:
                # Introduce section break before individual topic / specification / AMC
                lines.append(make_section_break(section_meta))
                if t_title:
                    level = "###" if current_heading else "##"
                    lines.append(f"{level} {t_title}\n\n")
                if body_text:
                    lines.append(f"{body_text}\n\n")
                    
        return "".join(lines)
        
    elif isinstance(data, dict):
        doc_title = title or data.get('title', 'Unknown EASA Title')
        lines.append(f"# DOCUMENT: {doc_title}\n\n")
        
        if data.get('raw_text'):
            lines.append(data.get('raw_text') + "\n\n")
            
        for topic in data.get("topics", []):
            topic_title = topic.get('title', '')
            lines.append(make_section_break({"title": topic_title, "type": "topic"}))
            if topic_title:
                lines.append(f"## {topic_title}\n\n")
                
            topic_text = topic.get('raw_text', '')
            if topic_text:
                lines.append(topic_text + "\n\n")
                
            for p in topic.get("paragraphs", []):
                p_text = p.get("raw_text", "")
                if p_text:
                    lines.append(p_text + "\n\n")
                    
        return "".join(lines)
    else:
        return f"```json\n{json.dumps(data, indent=2)}\n```"

# ==============================================================================
# Document Dispatcher
# ==============================================================================

def render_document_sections(json_path: Path) -> str:
    """
    Renders a JSON regulation into a segmented Markdown document containing
    structured section break markers.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    if isinstance(data, dict):
        if data.get("format") == "formex":
            return render_formex_sections(data)
        elif "topics" in data:
            return render_easa_sections(data, title=data.get("title") or json_path.stem)
        else:
            return f"```json\n{json.dumps(data, indent=2)}\n```"
    elif isinstance(data, list):
        return render_easa_sections(data, title=json_path.stem)
    else:
        return f"```json\n{json.dumps(data, indent=2)}\n```"

# ==============================================================================
# Frontend-Style Section Parser (Reference Implementation)
# ==============================================================================

def parse_document_sections(markdown_doc: str) -> List[Dict[str, Any]]:
    """
    Demonstrates how frontend TypeScript/JavaScript code splits the document into
    distinct sections using the embedded <!-- SECTION_BREAK {...} --> markers.
    """
    pattern = re.compile(r'\n*(?:---\n*)?<!-- SECTION_BREAK\s*(\{.*?\})?\s*-->\n*')
    tokens = pattern.split(markdown_doc)
    
    sections = []
    
    # Overview / Header block before first section break
    if tokens and tokens[0].strip():
        sections.append({
            "index": 0,
            "id": "doc-header",
            "type": "doc_header",
            "title": "Document Overview",
            "meta": {"type": "doc_header", "title": "Document Overview"},
            "markdown": tokens[0].strip(),
            "word_count": len(tokens[0].split())
        })
        
    # Subsequent sections alternate: (meta_json, markdown_text)
    idx = 1
    sec_count = 1
    while idx < len(tokens):
        meta_raw = tokens[idx]
        content = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        meta = {}
        if meta_raw:
            try:
                meta = json.loads(meta_raw)
            except Exception:
                meta = {}
                
        title = meta.get("title", f"Section {sec_count}")
        sec_id = meta.get("id") or f"section-{sec_count}"
        sec_type = meta.get("type", "section")
        
        sections.append({
            "index": sec_count,
            "id": sec_id,
            "type": sec_type,
            "title": title,
            "meta": meta,
            "markdown": content.strip(),
            "word_count": len(content.split())
        })
        
        sec_count += 1
        idx += 2
        
    return sections

# ==============================================================================
# CLI Test Runner
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test segmented document rendering with section breaks.")
    parser.add_argument("document_id", type=str, help="Document ID or path to JSON file")
    parser.add_argument("--output", "-o", type=str, help="Output markdown path (optional)")
    parser.add_argument("--json_output", "-j", type=str, help="Output parsed sections JSON path (optional)")
    args = parser.parse_args()
    
    json_path = find_json_file(args.document_id)
    if not json_path:
        print(f"Error: Could not find JSON file for document '{args.document_id}'")
        sys.exit(1)
        
    print(f"Loading and rendering document: {json_path.name}")
    segmented_md = render_document_sections(json_path)
    print(f"-> Generated {len(segmented_md):,} characters of segmented Markdown.")
    
    # Parse sections
    sections = parse_document_sections(segmented_md)
    print(f"-> Successfully extracted {len(sections)} distinct sections!\n")
    
    # Section types summary
    type_counts = {}
    for s in sections:
        type_counts[s["type"]] = type_counts.get(s["type"], 0) + 1
    print("Section Types Breakdown:")
    for t, cnt in type_counts.items():
        print(f"  - {t}: {cnt}")
        
    print("\nSample Extracted Sections:")
    for s in sections[:4]:
        print("-" * 70)
        print(f"Section #{s['index']} | ID: {s['id']} | Type: {s['type']} | Words: {s['word_count']}")
        print(f"Title: {s['title']}")
        first_lines = s['markdown'].split('\n')[:3]
        print("Preview:\n  " + "\n  ".join(first_lines))
        
    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(segmented_md, encoding="utf-8")
        print(f"\nSaved segmented Markdown to: {out_p.resolve()}")
        
    if args.json_output:
        out_j = Path(args.json_output)
        out_j.parent.mkdir(parents=True, exist_ok=True)
        out_j.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved parsed sections JSON to: {out_j.resolve()}")

if __name__ == "__main__":
    main()
