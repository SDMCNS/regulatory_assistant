"""
Script to list and download ICAO PDFs from peter2000.co.uk into import_pdfs/
"""
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://peter2000.co.uk/aviation/icao-documents/"
IMPORT_DIR = Path("import_pdfs")
IMPORT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def list_available_pdfs():
    req = urllib.request.Request(BASE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    
    pattern = re.compile(r'href=["\']([^"\']+\.pdf)["\']', re.IGNORECASE)
    matches = pattern.findall(html)
    
    unique_links = []
    seen = set()
    for m in matches:
        filename = m.split("/")[-1]
        decoded = urllib.parse.unquote(filename)
        # Sanitize any characters forbidden on Windows
        clean_filename = re.sub(r'[<>:"/\\|?*]', '_', decoded).strip()
        if clean_filename.lower() not in seen and clean_filename.lower() != "icaolist.pdf":
            seen.add(clean_filename.lower())
            unique_links.append((m, clean_filename))
    return unique_links


PRIORITY_DOCS = [
    # Annex 2 - Rules of the Air
    "icao_annex_2_rulesoftheair.pdf",
    # Annex 12 - Search and Rescue
    "icao_annex_12_searchandrescue.pdf",
    # Annex 13 - Aircraft Accident and Incident Investigation
    "AN13_cons.pdf",
    # Annex 17 - Security - Safeguarding International Civil Aviation
    "icao_annex_17_security.pdf",
    # Annex 18 - Safe Transport of Dangerous Goods by Air
    "icao_annex_18_thesafetransportofdangerousgoodsbyair.pdf",
    # Doc 4444 - Procedures for Air Navigation Services - Air Traffic Management (PANS-ATM)
    "Doc-4444-PANS-ATM.pdf",
    # Doc 9432 - Manual of Radiotelephony
    "DOC-9432-4-ed.-2007.pdf",
    # Doc 9574 - Manual on Implementation of a 300 m (1,000 ft) Vertical Separation Minimum (RVSM)
    "DOC-9574_MANUAL-ON-IMPLEMENTATION-OF-RVSM_R03_01JAN12.pdf",
    # Doc 9613 - Performance-based Navigation (PBN) Manual
    "DOC-9613_PBN-MANUA_R04_01JAN13.pdf",
    # Doc 9859 - Safety Management Manual (SMM)
    "DOC_9859_SAFETY_MANAGEMENT_MANUAL__E03_R01JAN13.pdf",
]


def download_pdf_worker(item):
    href, target_filename = item
    full_url = urllib.parse.urljoin(BASE_URL, href)
    target_path = IMPORT_DIR / target_filename
    
    if target_path.exists() and target_path.stat().st_size > 1024:
        return (target_filename, "SKIPPED", target_path.stat().st_size)
    
    req = urllib.request.Request(full_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            with open(target_path, "wb") as f:
                f.write(data)
        return (target_filename, "DOWNLOADED", len(data))
    except Exception as e:
        return (target_filename, f"FAILED: {e}", 0)


def main():
    import argparse
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parser = argparse.ArgumentParser(description="Download ICAO PDFs from peter2000.co.uk into import_pdfs/")
    parser.add_argument("--all", action="store_true", help="Download all ~60 available PDFs")
    parser.add_argument("--count", type=int, default=None, help="Number of files to download")
    parser.add_argument("--threads", type=int, default=6, help="Concurrent download threads (default: 6)")
    args = parser.parse_args()

    pdfs = list_available_pdfs()
    print(f"Discovered {len(pdfs)} available ICAO PDFs on {BASE_URL}")
    
    if args.all:
        to_download = pdfs
    elif args.count:
        to_download = pdfs[:args.count]
    else:
        # If neither --all nor --count is specified, default to all if user requested
        to_download = pdfs
    
    print(f"Downloading {len(to_download)} files into '{IMPORT_DIR.resolve()}' using {args.threads} worker threads ...\n")
    
    downloaded = 0
    skipped = 0
    failed = 0
    total_bytes = 0
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(download_pdf_worker, item): item for item in to_download}
        for future in as_completed(futures):
            filename, status, size = future.result()
            if status == "DOWNLOADED":
                downloaded += 1
                total_bytes += size
                print(f"  [+] Downloaded: {filename} ({size / 1024:.1f} KB)")
            elif status == "SKIPPED":
                skipped += 1
                print(f"  [=] Skipped (exists): {filename} ({size / 1024:.1f} KB)")
            else:
                failed += 1
                print(f"  [!] {status}: {filename}")
                
    print(f"\n==========================================")
    print(f"Download Summary:")
    print(f"  Downloaded: {downloaded}")
    print(f"  Already existed: {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total transferred: {total_bytes / (1024 * 1024):.2f} MB")
    print(f"  Target Directory: {IMPORT_DIR.resolve()}")
    print(f"==========================================")


if __name__ == "__main__":
    main()
