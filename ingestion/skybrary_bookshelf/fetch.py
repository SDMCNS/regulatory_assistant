#!/usr/bin/env python3
"""
SKYbrary Bookshelf crawler

Traverses:
    https://skybrary.aero/bookshelf-items?page=0
through the final available page.

For every bookshelf entry it finds:
    1. The publication/book page.
    2. The actual PDF/document link on that page.

The crawler is deliberately slow and polite:
    - One request at a time
    - Random delay between requests
    - Longer delay between pages
    - Exponential backoff for 429/403/5xx
    - Persistent results after every successful item
    - Resumes from previous progress
    - Does NOT download PDFs

Output:
    skybrary_bookshelf.csv
    skybrary_bookshelf.jsonl
    skybrary_progress.json
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://skybrary.aero/bookshelf-items?page={}"

START_PAGE = 0

# Set this to None to automatically continue until a page contains no
# publication entries.
#
# Alternatively, set:
# MAX_PAGE = 142
#
# The automatic mode is preferable because the site may grow.
MAX_PAGE: Optional[int] = None

OUTPUT_CSV = Path("skybrary_bookshelf.csv")
OUTPUT_JSONL = Path("skybrary_bookshelf.jsonl")
PROGRESS_FILE = Path("skybrary_progress.json")

# Deliberately conservative delays.
#
# A request is followed by a random delay between these values.
REQUEST_DELAY_MIN = 8.0
REQUEST_DELAY_MAX = 18.0

# Additional delay after completing a bookshelf page.
PAGE_DELAY_MIN = 20.0
PAGE_DELAY_MAX = 45.0

# If the server says "slow down", use substantially longer delays.
BACKOFF_START = 60.0
BACKOFF_MAX = 30 * 60.0

MAX_RETRIES = 8

# Request timeout.
TIMEOUT = 45

# We don't want to aggressively identify ourselves as a bot.
# This identifies the script honestly while behaving like a normal client.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36 "
    "SKYbraryBookshelfResearch/1.0"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Publication:
    bookshelf_page: int
    title: str
    publication_url: str
    pdf_url: str = ""
    pdf_filename: str = ""
    discovered_at: str = ""
    status: str = "found"
    error: str = ""


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def polite_sleep(minimum: float, maximum: float) -> None:
    delay = random.uniform(minimum, maximum)

    print(f"    sleeping {delay:.1f}s...", flush=True)
    time.sleep(delay)


def normalise_url(url: str, base_url: str) -> str:
    """Convert relative URLs to absolute URLs."""

    return urljoin(base_url, url.strip())


def get_filename_from_url(url: str) -> str:
    """Extract the filename from a PDF URL."""

    path = urlparse(url).path
    return Path(path).name


def looks_like_pdf(url: str) -> bool:
    """Identify SKYbrary PDF links."""

    parsed = urlparse(url)

    if parsed.netloc.lower() != "skybrary.aero":
        return False

    path = parsed.path.lower()

    return (
        path.endswith(".pdf")
        or "/sites/default/files/bookshelf/" in path
    )


# ---------------------------------------------------------------------------
# Persistent state
# ---------------------------------------------------------------------------

def load_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {
            "last_completed_page": START_PAGE - 1,
            "pages_completed": [],
        }

    try:
        with PROGRESS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        print("WARNING: Could not read progress file.")
        print("Starting again from the beginning.")
        return {
            "last_completed_page": START_PAGE - 1,
            "pages_completed": [],
        }


def save_progress(progress: dict) -> None:
    temporary = PROGRESS_FILE.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)

    temporary.replace(PROGRESS_FILE)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "bookshelf_page",
    "title",
    "publication_url",
    "pdf_url",
    "pdf_filename",
    "discovered_at",
    "status",
    "error",
]


def append_result(publication: Publication) -> None:
    """Append immediately to CSV and JSONL."""

    csv_exists = OUTPUT_CSV.exists()

    with OUTPUT_CSV.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
        )

        if not csv_exists:
            writer.writeheader()

        writer.writerow(asdict(publication))

    with OUTPUT_JSONL.open(
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            json.dumps(
                asdict(publication),
                ensure_ascii=False,
            )
            + "\n"
        )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def request_with_backoff(
    session: requests.Session,
    url: str,
    description: str,
) -> Optional[requests.Response]:

    delay = BACKOFF_START

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"    GET {description} "
            f"(attempt {attempt}/{MAX_RETRIES})",
            flush=True,
        )

        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
                allow_redirects=True,
            )

        except requests.RequestException as exc:

            print(
                f"    network error: {exc}",
                flush=True,
            )

            if attempt == MAX_RETRIES:
                return None

            print(
                f"    backing off for {delay:.0f}s",
                flush=True,
            )

            time.sleep(delay)

            delay = min(
                delay * 2,
                BACKOFF_MAX,
            )

            continue

        print(
            f"    HTTP {response.status_code} "
            f"({len(response.content):,} bytes)",
            flush=True,
        )

        # Successful request.
        if response.status_code == 200:
            return response

        # Rate limiting / bot protection / temporary server failure.
        if response.status_code in {
            403,
            408,
            425,
            429,
            500,
            502,
            503,
            504,
        }:

            print(
                f"    server returned {response.status_code}",
                flush=True,
            )

            if attempt == MAX_RETRIES:
                return None

            # Add substantial randomness to backoff.
            actual_delay = random.uniform(
                delay * 0.75,
                delay * 1.25,
            )

            print(
                f"    backing off for {actual_delay:.0f}s",
                flush=True,
            )

            time.sleep(actual_delay)

            delay = min(
                delay * 2,
                BACKOFF_MAX,
            )

            continue

        # Other HTTP errors aren't likely to recover.
        print(
            f"    unrecoverable HTTP status "
            f"{response.status_code}",
            flush=True,
        )

        return None

    return None


# ---------------------------------------------------------------------------
# Bookshelf page parsing
# ---------------------------------------------------------------------------

def find_publication_links(
    html: str,
    page_url: str,
) -> list[tuple[str, str]]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    publications: list[tuple[str, str]] = []

    seen: set[str] = set()

    # The Bookshelf currently presents publications as links in the
    # results table. We deliberately identify links by their destination
    # rather than depending on fragile CSS class names.
    for link in soup.find_all("a", href=True):

        href = normalise_url(
            link["href"],
            page_url,
        )

        parsed = urlparse(href)

        # We are looking for SKYbrary bookshelf item pages.
        if parsed.netloc.lower() != "skybrary.aero":
            continue

        path = parsed.path.rstrip("/")

        # Current SKYbrary Drupal structure.
        #
        # We intentionally allow several possible bookshelf paths so
        # that modest site changes don't immediately break the crawler.
        is_candidate = (
            path.startswith("/bookshelf/")
            or path.startswith("/bookshelf-items/")
            or "/bookshelf/" in path
        )

        if not is_candidate:
            continue

        title = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        if not title:
            continue

        # Ignore obvious navigation links.
        lower_title = title.lower()

        if lower_title in {
            "bookshelf",
            "view this book",
            "back",
            "next",
            "previous",
        }:
            continue

        key = href

        if key in seen:
            continue

        seen.add(key)

        publications.append(
            (
                title,
                href,
            )
        )

    return publications


# ---------------------------------------------------------------------------
# Publication page parsing
# ---------------------------------------------------------------------------

def find_pdf_link(
    html: str,
    publication_url: str,
) -> Optional[str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates: list[str] = []

    for link in soup.find_all("a", href=True):

        href = normalise_url(
            link["href"],
            publication_url,
        )

        if looks_like_pdf(href):
            candidates.append(href)

    if not candidates:
        return None

    # Prefer the exact SKYbrary bookshelf PDF location.
    for url in candidates:

        if "/sites/default/files/bookshelf/" in url:
            return url

    return candidates[0]


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------

def load_existing_publication_urls() -> set[str]:
    """Avoid duplicating records when restarting."""

    existing: set[str] = set()

    if not OUTPUT_CSV.exists():
        return existing

    try:

        with OUTPUT_CSV.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                url = row.get(
                    "publication_url",
                    "",
                ).strip()

                if url:
                    existing.add(url)

    except Exception as exc:

        print(
            f"WARNING: Could not read existing CSV: {exc}"
        )

    return existing


# ---------------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------------

def main() -> None:

    print()
    print("=" * 72)
    print("SKYbrary Bookshelf crawler")
    print("=" * 72)
    print()
    print("This crawler is deliberately slow.")
    print("It will NOT download the PDFs.")
    print()

    progress = load_progress()

    last_completed = progress.get(
        "last_completed_page",
        START_PAGE - 1,
    )

    existing_urls = load_existing_publication_urls()

    print(
        f"Last completed page: {last_completed}"
    )

    print(
        f"Existing publication records: "
        f"{len(existing_urls)}"
    )

    if MAX_PAGE is None:
        print(
            "Maximum page: automatic "
            "(continues until no publications are found)"
        )
    else:
        print(
            f"Maximum page: {MAX_PAGE}"
        )

    print()

    session = requests.Session()

    # Keep cookies between requests. This is both more natural and less
    # likely to look like a collection of independent clients.
    session.headers.update(HEADERS)

    page = max(
        START_PAGE,
        last_completed + 1,
    )

    total_publications = len(existing_urls)

    try:

        while True:

            if MAX_PAGE is not None and page > MAX_PAGE:
                print()
                print(
                    f"Reached configured final page: {MAX_PAGE}"
                )
                break

            page_url = BASE_URL.format(page)

            print()
            print("=" * 72)
            print(f"BOOKSHELF PAGE {page}")
            print(page_url)
            print("=" * 72)

            # Slow down before requesting the page.
            polite_sleep(
                REQUEST_DELAY_MIN,
                REQUEST_DELAY_MAX,
            )

            response = request_with_backoff(
                session,
                page_url,
                f"bookshelf page {page}",
            )

            if response is None:

                print()
                print(
                    f"Could not retrieve page {page}."
                )

                print(
                    "Progress up to the previous page has been saved."
                )

                print(
                    "Run the script again later to retry."
                )

                break

            publications = find_publication_links(
                response.text,
                page_url,
            )

            print(
                f"    Found {len(publications)} "
                f"candidate publications"
            )

            # If there are no publications, we have probably reached
            # the end of the collection.
            if not publications:

                print()
                print(
                    "No publication links found."
                )

                print(
                    "Assuming this is beyond the end "
                    "of the bookshelf."
                )

                break

            page_new = 0

            for index, (
                title,
                publication_url,
            ) in enumerate(
                publications,
                start=1,
            ):

                print()
                print(
                    f"[{index}/{len(publications)}] "
                    f"{title}"
                )

                # Avoid processing an item already collected.
                if publication_url in existing_urls:

                    print(
                        "    already collected; skipping"
                    )

                    continue

                print(
                    f"    publication: "
                    f"{publication_url}"
                )

                polite_sleep(
                    REQUEST_DELAY_MIN,
                    REQUEST_DELAY_MAX,
                )

                publication_response = request_with_backoff(
                    session,
                    publication_url,
                    "publication page",
                )

                if publication_response is None:

                    result = Publication(
                        bookshelf_page=page,
                        title=title,
                        publication_url=publication_url,
                        discovered_at=utc_now(),
                        status="publication_page_failed",
                        error="Could not retrieve publication page",
                    )

                    append_result(result)

                    existing_urls.add(
                        publication_url
                    )

                    continue

                pdf_url = find_pdf_link(
                    publication_response.text,
                    publication_url,
                )

                if pdf_url:

                    pdf_filename = get_filename_from_url(
                        pdf_url
                    )

                    print(
                        f"    PDF: {pdf_url}"
                    )

                    result = Publication(
                        bookshelf_page=page,
                        title=title,
                        publication_url=publication_url,
                        pdf_url=pdf_url,
                        pdf_filename=pdf_filename,
                        discovered_at=utc_now(),
                        status="found",
                    )

                    page_new += 1
                    total_publications += 1

                else:

                    print(
                        "    WARNING: no PDF link found"
                    )

                    result = Publication(
                        bookshelf_page=page,
                        title=title,
                        publication_url=publication_url,
                        discovered_at=utc_now(),
                        status="no_pdf_found",
                    )

                append_result(result)

                existing_urls.add(
                    publication_url
                )

                # Save after every item.
                progress["last_completed_page"] = page
                save_progress(progress)

            # Page completed.
            progress["last_completed_page"] = page

            completed_pages = progress.setdefault(
                "pages_completed",
                [],
            )

            if page not in completed_pages:
                completed_pages.append(page)

            save_progress(progress)

            print()
            print(
                f"Page {page} complete."
            )

            print(
                f"New publications collected: "
                f"{page_new}"
            )

            print(
                f"Total publication records: "
                f"{total_publications}"
            )

            # Deliberately long pause between pages.
            polite_sleep(
                PAGE_DELAY_MIN,
                PAGE_DELAY_MAX,
            )

            page += 1

    except KeyboardInterrupt:

        print()
        print("Interrupted by user.")
        print(
            f"Progress saved through page "
            f"{progress.get('last_completed_page')}"
        )

    finally:

        session.close()

    print()
    print("=" * 72)
    print("CRAWLER FINISHED")
    print("=" * 72)
    print()
    print(
        f"CSV:    {OUTPUT_CSV.resolve()}"
    )
    print(
        f"JSONL:  {OUTPUT_JSONL.resolve()}"
    )
    print(
        f"State:  {PROGRESS_FILE.resolve()}"
    )
    print()


if __name__ == "__main__":
    main()
