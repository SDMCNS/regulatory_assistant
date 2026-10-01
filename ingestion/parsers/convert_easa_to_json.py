import xml.etree.ElementTree as ET
import re
import json
import glob
from pathlib import Path

# Namespaces
PKG = "{http://schemas.microsoft.com/office/2006/xmlPackage}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ER = "{http://www.easa.europa.eu/erules-export}"

def clean_text(text):
    # Strip citations like "[Amdt LSA/1]", "[Amdt 25/12]", "ED Decision 2013/015/R"
    text = re.sub(r'\[Amdt\s+[^\]]+\]', '', text)
    text = re.sub(r'ED Decision\s+\d{4}/\d{3}/R', '', text)
    # Remove extra spaces and blank lines
    lines = [line.strip() for line in text.split('\n')]
    return "\n".join(line for line in lines if line)

def parse_easa_xml(file_path):
    try:
        root = ET.parse(file_path).getroot()
    except Exception as e:
        print(f"Failed to parse {file_path}: {e}")
        return None
        
    toc_mapping = {}
    
    # 1. Find TOC
    for part in root.findall(f'.//{PKG}part'):
        for topic in part.findall(f'.//{ER}topic'):
            sdt_id = topic.get('sdt-id')
            if sdt_id:
                toc_mapping[sdt_id] = {
                    "title": topic.get('source-title', ''),
                    "type": topic.get('TypeOfContent', ''),
                    "subject": topic.get('RegulatorySubject', ''),
                    "id": topic.get('ERulesId', '')
                }
        for heading in part.findall(f'.//{ER}heading'):
            sdt_id = heading.get('sdt-id')
            if sdt_id:
                toc_mapping[sdt_id] = {
                    "title": heading.get('title', ''),
                    "type": 'heading',
                    "subject": '',
                    "id": ''
                }

    # 2. Find document.xml
    doc_part = None
    for part in root.findall(f'.//{PKG}part'):
        if part.get(f'{PKG}name') == '/word/document.xml':
            doc_part = part
            break
            
    if doc_part is None:
        return None
        
    def extract_text(element):
        return "".join(element.itertext())

    data = []
    
    for sdt in doc_part.findall(f'.//{W}sdt'):
        sdt_pr = sdt.find(f'{W}sdtPr')
        if sdt_pr is None: continue
        w_id = sdt_pr.find(f'{W}id')
        if w_id is None: continue
        sdt_id = w_id.get(f'{W}val')
        
        # Only include topics present in TOC, and ignore topics with empty titles (like the TOC itself)
        if sdt_id not in toc_mapping:
            continue
            
        meta = toc_mapping[sdt_id]
        if not meta.get("title") or meta.get("title").strip() == "":
            continue
        
        sdt_content = sdt.find(f'{W}sdtContent')
        if sdt_content is None: continue
        
        paragraphs = []
        for p in sdt_content.findall(f'.//{W}p'):
            text = extract_text(p).strip()
            if text:
                paragraphs.append(text)
                
        if paragraphs:
            raw_text = "\n".join(paragraphs)
            cleaned = clean_text(raw_text)
            if cleaned:
                data.append({
                    "meta": meta,
                    "text": cleaned
                })
            
    return data

def run(input_dir: Path, out_dir: Path, limit: int = None):
    xml_files = glob.glob(str(input_dir / "*.xml"))
    out_dir.mkdir(parents=True, exist_ok=True)
    
    count = 0
    for xml_file in xml_files:
        if limit and count >= limit:
            break
        print(f"Processing {xml_file}...")
        data = parse_easa_xml(xml_file)
        if data:
            base_name = Path(xml_file).stem
            out_file = out_dir / (base_name + ".json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"  -> Saved {len(data)} topics to {out_file}")
            count += 1

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=str, default=r"data\easaxml", help="Directory containing EASA XML files")
    parser.add_argument("--out_dir", type=str, default=r"data\json", help="Output directory for JSON files")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of files to process")
    args = parser.parse_args()
    
    run(Path(args.input_dir), Path(args.out_dir), args.limit)

if __name__ == "__main__":
    main()
