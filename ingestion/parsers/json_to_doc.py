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

def find_json_file(document_id: str) -> Optional[Path]:
    p1 = settings.DATA_DIR / "regulations" / f"{document_id}.json"
    p2 = settings.DATA_DIR / "easa_json" / f"{document_id}.json"
    p2_alt = settings.DATA_DIR / "json" / f"{document_id}.json"
    
    if p1.exists():
        return p1
    if p2.exists():
        return p2
    if p2_alt.exists():
        return p2_alt
        
    # Also check if it's already a .json file path
    p3 = Path(document_id)
    if p3.exists() and p3.is_file():
        return p3
        
    return None

# ==============================================================================
# Section Break Formatting and Parsing
# ==============================================================================

def make_section_break(meta: Optional[Dict[str, Any]] = None, enabled: bool = True) -> str:
    """
    Creates a section break formatted as a Markdown horizontal rule accompanied by
    an HTML comment containing metadata JSON.
    
    In standard Markdown renderers (marked.js, GitHub), the comment is invisible
    and the '---' renders a visual divider line.
    
    In frontend code, splitting on the comment enables rendering individual sections
    as collapsible cards, tabs, or distinct blocks.
    """
    if not enabled:
        return ""
    if meta:
        meta_json = json.dumps(meta, ensure_ascii=False)
        return f"\n\n---\n<!-- SECTION_BREAK {meta_json} -->\n\n"
    return "\n\n---\n<!-- SECTION_BREAK -->\n\n"

def parse_document_sections(markdown_doc: str) -> List[Dict[str, Any]]:
    """
    Parses a segmented markdown document back into structured section dictionaries.
    Compatible with frontend parsing logic.
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
# Formex Rendering
# ==============================================================================

def render_formex_content(node, level=1, with_sections: bool = True):
    lines = []
    if isinstance(node, list):
        for child in node:
            lines.extend(render_formex_content(child, level, with_sections=with_sections))
        return lines

    if not isinstance(node, dict):
        return lines

    node_type = node.get("type", "")
    
    if node_type == "article":
        num = node.get("number", "")
        article_title = f"Article {num}" if not str(num).lower().startswith("article") else str(num)
        if with_sections:
            lines.append(make_section_break({"type": "article", "title": article_title, "number": num}))
        lines.append(f"## {num}\n\n")
        if "text" in node:
            lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1, with_sections=with_sections))
            
    elif node_type == "section":
        title = node.get("title", "")
        num = node.get("number", "")
        heading = f"{num} {title}".strip()
        if with_sections:
            lines.append(make_section_break({"type": "section", "title": heading, "number": num}))
        if heading:
            lines.append(f"{'#' * min(level + 1, 6)} {heading}\n\n")
        if "text" in node:
            lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1, with_sections=with_sections))
            
    elif node_type == "paragraph":
        num = node.get("number", "")
        prefix = f"**{num}** " if num else ""
        if "text" in node:
            lines.append(f"{prefix}{node['text']}\n\n")
        if "content" in node:
            if not "text" in node and num:
                lines.append(f"{prefix}\n")
            lines.extend(render_formex_content(node["content"], level + 1, with_sections=with_sections))
            
    elif node_type == "item":
        num = node.get("number", "")
        text = node.get("text", "")
        prefix = f"{num} " if num else ""
        lines.append(f"* {prefix}{text}\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1, with_sections=with_sections))
            
    elif node_type == "list":
        if "items" in node:
            for item in node["items"]:
                lines.extend(render_formex_content(item, level + 1, with_sections=with_sections))
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1, with_sections=with_sections))
        lines.append("\n")
        
    elif node_type == "quote":
        if "content" in node:
            quote_lines = render_formex_content(node["content"], level, with_sections=with_sections)
            for ql in quote_lines:
                if ql.strip():
                    lines.append(f"> {ql.strip()}\n")
            lines.append("\n")
                    
    elif node_type == "text":
        lines.append(node.get("text", "") + "\n\n")
        
    elif node_type == "signature":
        if with_sections:
            lines.append(make_section_break({"type": "signature", "title": "Signature"}))
        lines.append("\n---\n")
        lines.append(node.get("place_and_date", "") + "\n\n")
        for sig in node.get("signatories", []):
            lines.append(sig + "\n")
            
    elif "text" in node:
        lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level, with_sections=with_sections))
            
    return lines

def render_formex(data: Dict[str, Any], with_sections: bool = True) -> str:
    lines = []
    lines.append(f"# DOCUMENT: {data.get('title', 'Unknown Title')}\n\n")
    
    metadata = data.get("metadata", {})
    if metadata.get('date'):
        lines.append(f"**Date:** {metadata.get('date')}\n\n")
        
    preamble = data.get("preamble", {})
    if preamble:
        if with_sections:
            lines.append(make_section_break({"type": "preamble", "title": "Preamble"}))
        lines.append("## Preamble\n\n")
        if "initial" in preamble:
            lines.append(preamble["initial"] + "\n\n")
        for visa in preamble.get("visas", []):
            lines.append(visa + "\n\n")
        if "recitals_intro" in preamble:
            lines.append(preamble["recitals_intro"] + "\n\n")
        for recital in preamble.get("recitals", []):
            lines.extend(render_formex_content(recital, with_sections=with_sections))
        lines.append("\n")
        if "final" in preamble:
            lines.append(preamble["final"] + "\n\n")
            
    body = data.get("body", [])
    if body:
        lines.extend(render_formex_content(body, with_sections=with_sections))
        
    annexes = data.get("annexes", [])
    for idx, annex in enumerate(annexes):
        annex_title = annex.get('title', f'Annex {idx + 1}')
        if with_sections:
            lines.append(make_section_break({"type": "annex", "title": annex_title}))
        lines.append(f"# ANNEX: {annex_title}\n\n")
        annex_content = annex.get("content") or annex.get("body") or []
        if annex_content:
            lines.extend(render_formex_content(annex_content, with_sections=with_sections))
            
    final = data.get("final", {})
    if final:
        if with_sections:
            lines.append(make_section_break({"type": "final", "title": "Final Provisions"}))
        lines.extend(render_formex_content(final.get("content", []), with_sections=with_sections))
        
    notes = data.get("notes", {})
    if notes:
        if with_sections:
            lines.append(make_section_break({"type": "notes", "title": "Notes"}))
        lines.append("## Notes\n\n")
        for k, v in notes.items():
            lines.append(f"[{k}]: {v}\n\n")
            
    return "".join(lines)

# ==============================================================================
# EASA Rendering
# ==============================================================================

def render_easa(data: Any, title: Optional[str] = None, with_sections: bool = True) -> str:
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
            
            section_meta = {
                "id": t_id,
                "title": t_title or first_line,
                "type": t_type if t_type else "section",
                "parent_heading": current_heading
            }
            
            if t_type == "heading":
                current_heading = t_title
                heading_title = t_title or first_line
                if with_sections:
                    lines.append(make_section_break(section_meta))
                if heading_title:
                    lines.append(f"## {heading_title}\n\n")
                if body_text and body_text != heading_title:
                    lines.append(f"{body_text}\n\n")
            else:
                if with_sections:
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
            if with_sections:
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

def render_document(json_path: Path, with_sections: bool = True) -> str:
    """
    Renders a JSON regulation file into Markdown text.
    If with_sections=True (default), introduces section break delimiters
    with embedded JSON metadata for frontend section rendering.
    """
    
    # Check if this is a multi-part formex file
    is_formex_part = ".fmx.json" in json_path.name and not json_path.name.endswith(".chunks.json")
    if is_formex_part:
        # Extract base name like L_202601821EN
        base_name = json_path.name.split('.')[0]
        # Find all sibling parts
        siblings = [f for f in json_path.parent.glob(f"{base_name}.*.fmx.json") if not f.name.endswith('.chunks.json')]
        
        if len(siblings) > 1:
            # It is a multi-part document, render them in order
            # The .doc.fmx.json should ideally be first.
            doc_file = json_path.parent / f"{base_name}.doc.fmx.json"
            other_files = sorted([f for f in siblings if f != doc_file])
            
            all_files_to_render = []
            if doc_file.exists():
                all_files_to_render.append(doc_file)
            all_files_to_render.extend(other_files)
            
            full_md = []
            for f_path in all_files_to_render:
                with open(f_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("format") == "formex":
                    md_text = render_formex(data, with_sections=with_sections)
                    
                    # Prevent duplicate "# DOCUMENT:" headers for parts other than the first
                    if len(full_md) > 0 and md_text.startswith("# DOCUMENT:"):
                        lines = md_text.split('\n')
                        # strip the "# DOCUMENT: ..." line
                        md_text = "\n".join(lines[1:]).lstrip()

                    full_md.append(md_text.strip())
                
            return "\n\n".join(full_md)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Detect if it's Formex or EASA
    if isinstance(data, dict):
        if data.get("format") == "formex":
            return render_formex(data, with_sections=with_sections)
        elif "topics" in data:
            return render_easa(data, title=data.get("title") or json_path.stem, with_sections=with_sections)
        else:
            return f"```json\n{json.dumps(data, indent=2)}\n```"
    elif isinstance(data, list):
        return render_easa(data, title=json_path.stem, with_sections=with_sections)
    else:
        return f"```json\n{json.dumps(data, indent=2)}\n```"

# ==============================================================================
# CLI Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Render a JSON regulation file to a Markdown document.")
    parser.add_argument("document_id", type=str, help="Document ID or path to the JSON file")
    parser.add_argument("--output", "-o", type=str, help="Output file path (optional)")
    parser.add_argument("--sections-json", "-j", type=str, help="Output path for parsed sections JSON (optional)")
    parser.add_argument("--no-sections", action="store_false", dest="with_sections", default=True,
                        help="Render without section breaks")
    args = parser.parse_args()
    
    json_path = find_json_file(args.document_id)
    if not json_path:
        print(f"Error: Could not find JSON file for document '{args.document_id}'")
        sys.exit(1)
        
    doc_text = render_document(json_path, with_sections=args.with_sections)
    
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = settings.DATA_DIR / "rendered_docs"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = str(args.document_id).replace("/", "_").replace("\\", "_")
        if safe_name.endswith(".json"):
            safe_name = safe_name[:-5]
        out_path = out_dir / f"{safe_name}.md"
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc_text)
            
        print(f"\nDocument rendered successfully as Markdown!")
        print(f"File saved to: {out_path.resolve()}\n")
        
        if args.sections_json:
            sections = parse_document_sections(doc_text)
            sec_path = Path(args.sections_json)
            sec_path.parent.mkdir(parents=True, exist_ok=True)
            sec_path.write_text(json.dumps(sections, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Saved {len(sections)} sections JSON to: {sec_path.resolve()}\n")
            
        import os
        if os.name == 'nt':
            try:
                os.startfile(out_path.resolve())
            except Exception:
                pass
    except PermissionError:
        print(f"\n[ERROR] Could not write to {out_path.resolve()}")
        print("The file might be open in another program (like a Markdown editor or Word). Please close it and try again.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
