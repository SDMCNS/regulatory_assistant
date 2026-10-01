import sys
import json
import argparse
from pathlib import Path
from ingestion.core.config import settings

def find_json_file(document_id: str) -> Path:
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
        lines.append(f"\n## {num}\n\n")
        if "text" in node:
            lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "section":
        title = node.get("title", "")
        num = node.get("number", "")
        heading = f"{num} {title}".strip()
        if heading:
            lines.append(f"\n{'#' * min(level + 1, 6)} {heading}\n\n")
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
        # Include content within items if present
        prefix = f"{num} " if num else ""
        lines.append(f"* {prefix}{text}\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level + 1))
            
    elif node_type == "list":
        if "items" in node:
            for item in node["items"]:
                lines.extend(render_formex_content(item, level + 1))
        # Sometimes lists might just have content instead of items
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
        lines.append("\n---\n")
        lines.append(node.get("place_and_date", "") + "\n\n")
        for sig in node.get("signatories", []):
            lines.append(sig + "\n")
            
    elif "text" in node:
        lines.append(node["text"] + "\n\n")
        if "content" in node:
            lines.extend(render_formex_content(node["content"], level))
            
    return lines

def render_formex(data):
    lines = []
    lines.append(f"# DOCUMENT: {data.get('title', 'Unknown Title')}\n\n")
    
    metadata = data.get("metadata", {})
    if metadata.get('date'):
        lines.append(f"**Date:** {metadata.get('date')}\n\n")
        
    preamble = data.get("preamble", {})
    if preamble:
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
    for annex in annexes:
        lines.append(f"\n# ANNEX: {annex.get('title', '')}\n\n")
        if "content" in annex:
            lines.extend(render_formex_content(annex["content"]))
            
    final = data.get("final", {})
    if final:
        lines.extend(render_formex_content(final.get("content", [])))
        
    notes = data.get("notes", {})
    if notes:
        lines.append("\n## Notes\n\n")
        for k, v in notes.items():
            lines.append(f"[{k}]: {v}\n\n")
            
    return "".join(lines)

def render_easa(data):
    lines = []
    lines.append(f"# DOCUMENT: {data.get('title', 'Unknown EASA Title')}\n\n")
    
    if data.get('raw_text'):
        lines.append(data.get('raw_text') + "\n\n")
        
    for topic in data.get("topics", []):
        topic_title = topic.get('title', '')
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

def render_document(json_path: Path) -> str:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Detect if it's Formex or EASA
    if data.get("format") == "formex":
        return render_formex(data)
    elif "topics" in data:
        return render_easa(data)
    else:
        # Generic fallback
        return f"```json\n{json.dumps(data, indent=2)}\n```"

def main():
    parser = argparse.ArgumentParser(description="Render a JSON regulation file to a Markdown document.")
    parser.add_argument("document_id", type=str, help="Document ID or path to the JSON file")
    parser.add_argument("--output", "-o", type=str, help="Output file path (optional)")
    args = parser.parse_args()
    
    json_path = find_json_file(args.document_id)
    if not json_path:
        print(f"Error: Could not find JSON file for document '{args.document_id}'")
        sys.exit(1)
        
    doc_text = render_document(json_path)
    
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = settings.DATA_DIR / "rendered_docs"
        out_dir.mkdir(parents=True, exist_ok=True)
        # Avoid Path.stem here because document_id may contain dots (e.g. L_2015063EN.01003901)
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
        
        import os
        # Automatically open the file on Windows if possible
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
