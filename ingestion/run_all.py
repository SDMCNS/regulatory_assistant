import sys
import subprocess
import argparse
from pathlib import Path

# Add project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.core.config import settings

def main():
    parser = argparse.ArgumentParser(description="Run the full ingestion pipeline for Formex and EASA documents.")
    parser.add_argument("--formex_dir", type=str, default=str(settings.DATA_DIR / "formex"), help="Directory containing Formex XML files")
    parser.add_argument("--easa_feed", type=str, default="https://www.easa.europa.eu/document-library/easy-access-rules/feed.xml", help="EASA RSS feed URL")
    parser.add_argument("--easa_xml_dir", type=str, default=str(settings.DATA_DIR / "easaxml"), help="Directory for downloaded EASA XML files")
    parser.add_argument("--easa_json_dir", type=str, default=str(settings.DATA_DIR / "easa_json"), help="Directory for parsed EASA JSON files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to process for each pipeline")
    parser.add_argument("--reset", action="store_true", help="Reset the environment before running")
    parser.add_argument("--download_easa", action="store_true", help="Run the EASA XML downloader step (optional)")
    args = parser.parse_args()

    # Pre-flight checks and counting
    print("\nScanning directories to count files...")
    
    # Count Formex files
    formex_path = Path(args.formex_dir)
    formex_path.mkdir(parents=True, exist_ok=True)
    try:
        from ingestion.pipelines.ingest_formex import find_xml_files
        formex_files = find_xml_files(formex_path, extract_zips=True)
        formex_count = len(formex_files)
    except Exception as e:
        print(f"Warning: Could not count Formex files: {e}")
        formex_count = 0
        
    # Count EASA files
    easa_xml_path = Path(args.easa_xml_dir)
    if easa_xml_path.exists():
        easa_count = len(list(easa_xml_path.glob("*.xml")))
    else:
        easa_count = 0

    print("\n" + "="*80)
    print("PIPELINE SUMMARY")
    print("="*80)
    print(f"EU (Formex) files to process : {formex_count}")
    if args.download_easa:
        print(f"EASA files to process        : {easa_count} (currently present, more may be downloaded)")
    else:
        print(f"EASA files to process        : {easa_count}")
    print("="*80)
    
    proceed = input("\nDo you want to proceed with ingestion? (y/n): ")
    if proceed.lower() not in ['y', 'yes']:
        print("Aborting.")
        return

    # 1. Formex Pipeline
    print("\n" + "="*80)
    print("1. RUNNING FORMEX INGESTION PIPELINE")
    print("="*80)
    
    cmd_formex = [sys.executable, "-m", "ingestion.pipelines.ingest_formex", args.formex_dir]
    if args.limit:
        cmd_formex.extend(["--limit", str(args.limit)])
    if args.reset:
        cmd_formex.append("--reset")
        
    subprocess.run(cmd_formex, check=False)

    # 2. EASA XML Downloader
    if args.download_easa:
        print("\n" + "="*80)
        print("2. DOWNLOADING EASA XML FILES")
        print("="*80)
        
        cmd_easa_download = [sys.executable, "-m", "ingestion.utils.easaxmldownloader", args.easa_feed, args.easa_xml_dir]
        subprocess.run(cmd_easa_download, check=False)
    else:
        print("\n" + "="*80)
        print("2. SKIPPING EASA XML DOWNLOADER")
        print("="*80)

    # 3. EASA to JSON Converter
    print("\n" + "="*80)
    print("3. CONVERTING EASA XML TO JSON")
    print("="*80)
    
    cmd_easa_convert = [sys.executable, "-m", "ingestion.parsers.convert_easa_to_json", "--input_dir", args.easa_xml_dir, "--out_dir", args.easa_json_dir]
    if args.limit:
        cmd_easa_convert.extend(["--limit", str(args.limit)])
    subprocess.run(cmd_easa_convert, check=False)

    # 4. EASA Chunker Pipeline
    print("\n" + "="*80)
    print("4. RUNNING EASA CHUNKER PIPELINE")
    print("="*80)
    
    cmd_easa_chunk = [sys.executable, "-m", "ingestion.pipelines.chunk_easa_pipeline", args.easa_json_dir]
    if args.limit:
        cmd_easa_chunk.extend(["--limit", str(args.limit)])
    subprocess.run(cmd_easa_chunk, check=False)

    # 5. Generate Embeddings for all new chunks
    print("\n" + "="*80)
    print("5. GENERATING EMBEDDINGS")
    print("="*80)
    
    cmd_embed = [sys.executable, "-m", "ingestion.retrieval.embed_chunks"]
    subprocess.run(cmd_embed, check=False)
    
    print("\n" + "="*80)
    print("ALL PIPELINES COMPLETED SUCCESSFULLY")
    print("="*80)

if __name__ == "__main__":
    main()
