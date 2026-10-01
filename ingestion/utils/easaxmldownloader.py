"""
Download EASA Easy Access Rules XML files listed in an RSS feed.

For each RSS item:
    RSS title -> document filename
    RSS link  -> EASA publication page
    publication page -> XML download (direct or ZIP containing XML)
    XML download -> saved locally as "<title>.xml"

Requirements:
    pip install requests beautifulsoup4

Usage:
    python download_easa_xml.py path/to/feed.xml output_directory
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


DEFAULT_FEED_URL = (
    "https://www.easa.europa.eu/"
    "document-library/easy-access-rules/feed.xml"
)

USER_AGENT = (
    "RegulationAssistant/1.0 "
    "(EASA Easy Access Rules XML downloader)"
)

REQUEST_TIMEOUT = 60
DELAY_SECONDS = 1.0


def sanitise_filename(name: str) -> str:
    """Make an RSS title safe for Windows/Linux/macOS filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")

    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if name.upper() in reserved:
        name = f"_{name}"
    return name


def load_rss(source: str, session: requests.Session) -> bytes:
    path = Path(source)
    if path.exists():
        print(f"Reading RSS from: {path}")
        return path.read_bytes()

    print(f"Downloading RSS: {source}")
    response = session.get(source, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def parse_rss(data: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(data)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        link = item.findtext("link")
        if title and link:
            items.append({"title": title.strip(), "url": link.strip()})
    return items


def get_candidate_download_urls(page_url: str, html: bytes) -> list[str]:
    """
    Locates candidate download URLs on the publication page.
    Filters out obvious PDFs, EPUBs, and guide/documentation links.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Target download and file sections first; fallback to main or body
    containers = soup.select(
        ".field--name-field-document-files, "
        ".field--name-field-publications, "
        ".publications-list, "
        ".downloads, "
        "main, "
        "article"
    ) or [soup]

    candidates = []
    seen = set()

    # File extensions to ignore
    ignore_extensions = {".pdf", ".epub", ".docx", ".doc", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"}

    # Keyword filters for documentation/guides about XML rather than actual datasets
    negative_patterns = re.compile(
        r"\b(guide|guidance|instruction|instructions|manual|spec|specification|specs|how\s+to|about)\b",
        re.IGNORECASE,
    )

    for container in containers:
        for link in container.find_all("a", href=True):
            href = link["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            absolute_url = urljoin(page_url, href)
            if absolute_url in seen:
                continue

            parsed = urlparse(absolute_url)
            path_lower = parsed.path.lower()

            if any(path_lower.endswith(ext) for ext in ignore_extensions):
                continue

            text = link.get_text(" ", strip=True)
            parent_text = link.parent.get_text(" ", strip=True) if link.parent else ""
            combined_text = f"{text} {parent_text}".strip()

            # Skip informational guides discussing XML
            if negative_patterns.search(combined_text) or negative_patterns.search(path_lower):
                continue

            score = 0

            # Direct XML file or endpoint
            if path_lower.endswith(".xml") or "/xml" in path_lower:
                score += 100
            elif path_lower.endswith(".zip"):
                score += 70

            # Anchor or surrounding text mentions XML
            if re.search(r"\bxml\b", combined_text, re.IGNORECASE):
                score += 50
            if re.search(r"\bzip\b", combined_text, re.IGNORECASE):
                score += 20

            if score > 0:
                seen.add(absolute_url)
                candidates.append((score, absolute_url))

    # Highest score first
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in candidates]


def extract_xml_from_payload(content: bytes) -> bytes | None:
    """
    Checks if raw bytes are valid XML or a ZIP containing valid XML.
    Returns the parsed XML bytes, or None if neither matches.
    """
    stripped = content.lstrip()

    # Case 1: Plain XML
    if stripped.startswith(b"<?xml") or (stripped.startswith(b"<") and b">" in stripped[:100]):
        try:
            ET.fromstring(content)
            return content
        except ET.ParseError:
            pass

    # Case 2: ZIP containing XML
    if zipfile.is_zipfile(io.BytesIO(content)):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml_files = [
                    name for name in archive.namelist()
                    if name.lower().endswith(".xml") and not name.startswith("__MACOSX/") and not name.endswith("/")
                ]
                if not xml_files:
                    return None

                # Prioritize root or primary document files over auxiliary schemas
                xml_files.sort(
                    key=lambda x: (
                        "schema" in x.lower() or "dtd" in x.lower(),
                        "metadata" in x.lower(),
                        len(x)
                    )
                )

                for candidate in xml_files:
                    try:
                        data = archive.read(candidate)
                        ET.fromstring(data)
                        return data
                    except ET.ParseError:
                        continue
        except (zipfile.BadZipFile, RuntimeError):
            return None

    return None


def download_document(
    session: requests.Session,
    title: str,
    page_url: str,
    output_dir: Path,
    overwrite: bool = False,
) -> str:
    filename = sanitise_filename(title) + ".xml"
    output_path = output_dir / filename

    print()
    print("=" * 80)
    print(f"DOCUMENT: {title}")
    print(f"PAGE:     {page_url}")

    if output_path.exists() and not overwrite:
        print(f"SKIP:     {output_path.name} already exists")
        return "exists"

    page_response = session.get(page_url, timeout=REQUEST_TIMEOUT)
    page_response.raise_for_status()

    candidate_urls = get_candidate_download_urls(page_url, page_response.content)

    if not candidate_urls:
        raise RuntimeError("No candidate XML/ZIP download links identified on the page.")

    xml_content = None
    successful_url = None

    for url in candidate_urls:
        print(f"Trying:   {url}")
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if resp.status_code != 200:
                continue

            extracted = extract_xml_from_payload(resp.content)
            if extracted:
                xml_content = extracted
                successful_url = url
                break
        except requests.RequestException as req_err:
            print(f"          Warning: failed request to {url}: {req_err}")
            continue

    if not xml_content:
        raise RuntimeError("None of the candidate links contained a valid XML document or ZIP archive.")

    print(f"MATCH:    {successful_url} ({len(xml_content):,} bytes extracted)")

    # Save raw download for backup/inspection
    raw_dir = output_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / (sanitise_filename(title) + ".raw")
    raw_path.write_bytes(xml_content)

    # Atomic write to final destination
    temp_path = output_path.with_suffix(".xml.tmp")
    temp_path.write_bytes(xml_content)
    temp_path.replace(output_path)

    print(f"SAVED:    {output_path}")
    return "downloaded"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download XML versions of EASA Easy Access Rules listed in an RSS feed."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_FEED_URL,
        help="RSS feed URL or local RSS/XML file.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="easa_xml",
        help="Directory in which XML files will be saved.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite XML files that already exist.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_SECONDS,
        help="Delay between documents in seconds.",
    )

    args = parser.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    try:
        rss_data = load_rss(args.source, session)
        documents = parse_rss(rss_data)
    except Exception as exc:
        print(f"ERROR: Could not load/parse RSS: {exc}", file=sys.stderr)
        return 1

    print(f"\nFound {len(documents)} RSS documents.")
    print(f"Output directory: {output_dir.resolve()}")

    downloaded = 0
    skipped = 0
    failed = 0
    failures = []

    for index, document in enumerate(documents, start=1):
        print(f"\n[{index}/{len(documents)}]")
        try:
            result = download_document(
                session=session,
                title=document["title"],
                page_url=document["url"],
                output_dir=output_dir,
                overwrite=args.overwrite,
            )
            if result == "downloaded":
                downloaded += 1
            elif result == "exists":
                skipped += 1
        except Exception as exc:
            failed += 1
            failures.append({"title": document["title"], "url": document["url"], "error": str(exc)})
            print(f"FAILED:   {exc}", file=sys.stderr)

        if index < len(documents):
            time.sleep(args.delay)

    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"RSS documents : {len(documents)}")
    print(f"Downloaded    : {downloaded}")
    print(f"Already exist : {skipped}")
    print(f"Failed        : {failed}")

    if failures:
        print("\nFAILURES")
        print("-" * 80)
        for failure in failures:
            print(f"Document: {failure['title']}\nURL:      {failure['url']}\nError:    {failure['error']}\n")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
