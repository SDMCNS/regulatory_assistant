from __future__ import annotations

import argparse
import json
import random
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import websocket
from bs4 import BeautifulSoup


BASE_URL = "https://skybrary.aero"
CDP_URL = "http://127.0.0.1:9222/json"

DEFAULT_DB = "skybrary.db"

INDEX_DELAY_MIN = 8
INDEX_DELAY_MAX = 15

SUMMARY_DELAY_MIN = 12
SUMMARY_DELAY_MAX = 25

LONG_PAUSE_EVERY = 25
LONG_PAUSE_MIN = 30
LONG_PAUSE_MAX = 60

PAGE_TIMEOUT = 45


# ============================================================================
# GENERAL
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def normalise_url(url: str) -> str:
    return url.rstrip("/")


def is_cloudflare_challenge(title: str, body: str) -> bool:
    text = f"{title}\n{body}".lower()

    indicators = (
        "just a moment",
        "verify you are human",
        "checking your browser",
        "performing security verification",
        "challenge-platform",
    )

    return any(item in text for item in indicators)


# ============================================================================
# SQLITE
# ============================================================================

def open_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row

    db.execute("""
        PRAGMA journal_mode = WAL
    """)

    db.execute("""
        PRAGMA synchronous = NORMAL
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT,
            category TEXT,
            author TEXT,
            publication_date TEXT,

            summary_url TEXT NOT NULL UNIQUE,
            pdf_url TEXT,

            status TEXT NOT NULL DEFAULT 'discovered',

            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_publications_status
        ON publications(status)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_publications_pdf
        ON publications(pdf_url)
    """)

    db.commit()

    return db


def upsert_publication(
    db: sqlite3.Connection,
    record: dict,
) -> None:

    now = utc_now()

    db.execute("""
        INSERT INTO publications (
            title,
            category,
            author,
            publication_date,
            summary_url,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'discovered', ?, ?)

        ON CONFLICT(summary_url) DO UPDATE SET
            title = excluded.title,
            category = excluded.category,
            author = excluded.author,
            publication_date = excluded.publication_date,
            updated_at = excluded.updated_at
    """, (
        record["title"],
        record["category"],
        record["author"],
        record["publication_date"],
        record["summary_url"],
        now,
        now,
    ))


def mark_attempt(
    db: sqlite3.Connection,
    row_id: int,
) -> None:

    db.execute("""
        UPDATE publications
        SET attempts = attempts + 1,
            updated_at = ?
        WHERE id = ?
    """, (utc_now(), row_id))

    db.commit()


def mark_complete(
    db: sqlite3.Connection,
    row_id: int,
    pdf_url: str,
) -> None:

    db.execute("""
        UPDATE publications
        SET pdf_url = ?,
            status = 'complete',
            error = NULL,
            updated_at = ?
        WHERE id = ?
    """, (
        pdf_url,
        utc_now(),
        row_id,
    ))

    db.commit()


def mark_error(
    db: sqlite3.Connection,
    row_id: int,
    error: str,
) -> None:

    db.execute("""
        UPDATE publications
        SET status = 'error',
            error = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        error[:4000],
        utc_now(),
        row_id,
    ))

    db.commit()


# ============================================================================
# EDGE CDP
# ============================================================================

def get_browser_target() -> dict:

    with urllib.request.urlopen(CDP_URL, timeout=10) as response:
        targets = json.load(response)

    # Prefer SKYbrary.
    for target in targets:
        if (
            target.get("type") == "page"
            and "skybrary.aero" in target.get("url", "")
        ):
            return target

    # Otherwise use a normal browser tab.
    for target in targets:
        if target.get("type") == "page":
            return target

    raise RuntimeError(
        "No browser page found. Start Edge with remote debugging."
    )


class EdgeCDP:

    def __init__(self):

        target = get_browser_target()

        print()
        print("Attaching to Edge:")
        print(f"  {target.get('url')}")
        print()

        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"],
            origin="http://127.0.0.1:9222",
            timeout=60,
        )

        self.command_id = 0

        self.command("Page.enable")
        self.command("Runtime.enable")

    def command(
        self,
        method: str,
        params: dict | None = None,
    ) -> dict:

        self.command_id += 1
        command_id = self.command_id

        message = {
            "id": command_id,
            "method": method,
        }

        if params is not None:
            message["params"] = params

        self.ws.send(json.dumps(message))

        while True:

            response = json.loads(self.ws.recv())

            if response.get("id") == command_id:
                return response

    def evaluate(self, expression: str):

        response = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )

        result = response.get(
            "result",
            {},
        ).get(
            "result",
            {},
        )

        if "value" in result:
            return result["value"]

        return None

    def navigate(self, url: str):

        self.command(
            "Page.navigate",
            {
                "url": url,
            },
        )

    def wait_for_page(
        self,
        expected_url: str | None = None,
        timeout: int = PAGE_TIMEOUT,
    ) -> dict:

        start = time.time()

        while time.time() - start < timeout:

            state = self.evaluate("""
                ({
                    url: location.href,
                    title: document.title,
                    readyState: document.readyState,
                    body: document.body
                        ? document.body.innerText.substring(0, 10000)
                        : ""
                })
            """)

            if not state:
                time.sleep(1)
                continue

            title = state["title"]
            body = state["body"]
            url = state["url"]

            if is_cloudflare_challenge(title, body):
                raise CloudflareChallenge()

            if state["readyState"] == "complete":

                if expected_url is None:
                    return state

                if normalise_url(url) == normalise_url(expected_url):
                    return state

                if expected_url.rstrip("/") in url:
                    return state

            time.sleep(1)

        raise TimeoutError(
            f"Timed out waiting for {expected_url}"
        )

    def html(self) -> str:

        return self.evaluate(
            "document.documentElement.outerHTML"
        )

    def close(self):

        try:
            self.ws.close()
        except Exception:
            pass


class CloudflareChallenge(Exception):
    pass


# ============================================================================
# CLOUDFLARE
# ============================================================================

def wait_for_cloudflare_resolution(
    browser: EdgeCDP,
) -> None:

    print()
    print("=" * 80)
    print("CLOUDFLARE CHALLENGE")
    print("=" * 80)
    print()
    print("Complete the challenge manually in the Edge window.")
    print("The crawler is paused.")
    print()

    while True:

        time.sleep(3)

        state = browser.evaluate("""
            ({
                title: document.title,
                body: document.body
                    ? document.body.innerText.substring(0, 10000)
                    : ""
            })
        """)

        if not is_cloudflare_challenge(
            state.get("title", ""),
            state.get("body", ""),
        ):
            print("Challenge cleared.")
            time.sleep(5)
            return


# ============================================================================
# INDEX PARSING
# ============================================================================

def parse_bookshelf_index(
    html: str,
) -> list[dict]:

    soup = BeautifulSoup(html, "html.parser")

    records = []

    for row in soup.select("table tbody tr"):

        cells = row.find_all("td")

        link = row.find(
            "a",
            href=True,
        )

        if not link:
            continue

        href = link["href"]

        if not href.startswith("/bookshelf/"):
            continue

        title = " ".join(
            link.get_text(" ", strip=True).split()
        )

        if not title:
            continue

        values = [
            " ".join(
                cell.get_text(" ", strip=True).split()
            )
            for cell in cells
        ]

        records.append({
            "title": title,
            "category": values[1] if len(values) > 1 else "",
            "author": values[2] if len(values) > 2 else "",
            "publication_date": values[3] if len(values) > 3 else "",
            "summary_url": absolute_url(href),
        })

    # Defensive fallback.
    if not records:

        for link in soup.find_all(
            "a",
            href=True,
        ):

            href = link["href"]

            if not href.startswith("/bookshelf/"):
                continue

            title = " ".join(
                link.get_text(" ", strip=True).split()
            )

            if title:

                records.append({
                    "title": title,
                    "category": "",
                    "author": "",
                    "publication_date": "",
                    "summary_url": absolute_url(href),
                })

    unique = {}

    for record in records:
        unique[record["summary_url"]] = record

    return list(unique.values())


# ============================================================================
# PDF LINK PARSING
# ============================================================================

def find_pdf_url(html: str) -> str | None:

    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link["href"]

        text = " ".join(
            link.get_text(" ", strip=True).split()
        )

        href_lower = href.lower()
        text_lower = text.lower()

        score = 0

        if ".pdf" in href_lower:
            score += 100

        if "/sites/default/files/bookshelf/" in href_lower:
            score += 100

        if "view publication" in text_lower:
            score += 50

        if "download" in text_lower:
            score += 20

        if "publication" in text_lower:
            score += 10

        if score:

            candidates.append((
                score,
                absolute_url(href),
            ))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


# ============================================================================
# STAGE 1
# ============================================================================

def crawl_index(
    browser: EdgeCDP,
    db: sqlite3.Connection,
    start_page: int,
    max_pages: int | None,
) -> None:

    print()
    print("=" * 80)
    print("STAGE 1 — BOOKSHELF INDEX")
    print("=" * 80)

    page = start_page
    empty_pages = 0

    while True:

        if (
            max_pages is not None
            and page >= start_page + max_pages
        ):
            break

        url = (
            f"{BASE_URL}/bookshelf-items"
            f"?page={page}"
        )

        print()
        print(f"[INDEX] page {page}")
        print(url)

        try:

            browser.navigate(url)

            try:
                browser.wait_for_page(url)

            except CloudflareChallenge:
                wait_for_cloudflare_resolution(browser)

                browser.navigate(url)
                browser.wait_for_page(url)

            html = browser.html()

            records = parse_bookshelf_index(html)

            if not records:

                empty_pages += 1

                print(
                    f"  No records found "
                    f"(consecutive empty pages: {empty_pages})"
                )

                if empty_pages >= 2:
                    print("Index appears complete.")
                    break

            else:

                empty_pages = 0

                for record in records:
                    upsert_publication(
                        db,
                        record,
                    )

                db.commit()

                total = db.execute(
                    "SELECT COUNT(*) FROM publications"
                ).fetchone()[0]

                print(
                    f"  Found: {len(records)}"
                )

                print(
                    f"  SQLite total: {total:,}"
                )

        except Exception as exc:

            print(
                f"  ERROR: {type(exc).__name__}: {exc}"
            )

            print(
                "  Waiting 60 seconds before retry."
            )

            time.sleep(60)
            continue

        page += 1

        delay = random.uniform(
            INDEX_DELAY_MIN,
            INDEX_DELAY_MAX,
        )

        print(
            f"  Sleeping {delay:.1f}s"
        )

        time.sleep(delay)


# ============================================================================
# STAGE 2
# ============================================================================

def get_pending(
    db: sqlite3.Connection,
) -> list[sqlite3.Row]:

    return db.execute("""
        SELECT *
        FROM publications
        WHERE status != 'complete'
           OR pdf_url IS NULL
        ORDER BY id
    """).fetchall()


def crawl_summaries(
    browser: EdgeCDP,
    db: sqlite3.Connection,
) -> None:

    rows = get_pending(db)

    total = len(rows)

    print()
    print("=" * 80)
    print("STAGE 2 — SUMMARY PAGES → PDF URL")
    print("=" * 80)
    print()
    print(f"Pending: {total:,}")

    completed = 0

    for position, row in enumerate(
        rows,
        start=1,
    ):

        row_id = row["id"]
        title = row["title"]
        summary_url = row["summary_url"]

        print()
        print("-" * 80)
        print(
            f"[PDF] {position:,}/{total:,}"
        )
        print(title)
        print(summary_url)

        mark_attempt(
            db,
            row_id,
        )

        try:

            browser.navigate(summary_url)

            try:

                browser.wait_for_page(
                    summary_url
                )

            except CloudflareChallenge:

                wait_for_cloudflare_resolution(
                    browser
                )

                browser.navigate(
                    summary_url
                )

                browser.wait_for_page(
                    summary_url
                )

            html = browser.html()

            pdf_url = find_pdf_url(html)

            if pdf_url:

                mark_complete(
                    db,
                    row_id,
                    pdf_url,
                )

                completed += 1

                print("PDF:")
                print(pdf_url)

            else:

                mark_error(
                    db,
                    row_id,
                    "No PDF link found",
                )

                print(
                    "WARNING: no PDF link found"
                )

        except Exception as exc:

            error = (
                f"{type(exc).__name__}: {exc}"
            )

            mark_error(
                db,
                row_id,
                error,
            )

            print(
                f"ERROR: {error}"
            )

        if completed > 0 and (
            completed % LONG_PAUSE_EVERY == 0
        ):

            delay = random.uniform(
                LONG_PAUSE_MIN,
                LONG_PAUSE_MAX,
            )

            print(
                f"Long pause: {delay:.1f}s"
            )

        else:

            delay = random.uniform(
                SUMMARY_DELAY_MIN,
                SUMMARY_DELAY_MAX,
            )

        time.sleep(delay)


# ============================================================================
# SQLITE STATUS
# ============================================================================

def show_stats(
    db: sqlite3.Connection,
) -> None:

    total = db.execute(
        "SELECT COUNT(*) FROM publications"
    ).fetchone()[0]

    discovered = db.execute("""
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'discovered'
    """).fetchone()[0]

    complete = db.execute("""
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'complete'
    """).fetchone()[0]

    errors = db.execute("""
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'error'
    """).fetchone()[0]

    pdfs = db.execute("""
        SELECT COUNT(*)
        FROM publications
        WHERE pdf_url IS NOT NULL
    """).fetchone()[0]

    print()
    print("=" * 80)
    print("SKYBRARY SQLITE STATUS")
    print("=" * 80)
    print(f"Publications discovered : {total:,}")
    print(f"Awaiting PDF resolution : {discovered:,}")
    print(f"PDF URLs found          : {pdfs:,}")
    print(f"Completed               : {complete:,}")
    print(f"Errors                  : {errors:,}")
    print("=" * 80)


def list_errors(
    db: sqlite3.Connection,
) -> None:

    rows = db.execute("""
        SELECT
            id,
            title,
            summary_url,
            attempts,
            error
        FROM publications
        WHERE status = 'error'
        ORDER BY id
    """).fetchall()

    if not rows:

        print("No errors.")
        return

    print()
    print("=" * 80)
    print("ERRORS")
    print("=" * 80)

    for row in rows:

        print()
        print(f"ID       : {row['id']}")
        print(f"Title    : {row['title']}")
        print(f"Attempts : {row['attempts']}")
        print(f"URL      : {row['summary_url']}")
        print(f"Error    : {row['error']}")


# ============================================================================
# HELP
# ============================================================================

HELP_EPILOG = r"""
EDGE SETUP
----------

The crawler does NOT use requests to access SKYbrary. It controls a normal
Microsoft Edge session through the Chrome DevTools Protocol (CDP).

First close normal Edge windows:

    taskkill /F /IM msedge.exe

Then launch the dedicated crawler browser:

    & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
        --remote-debugging-port=9222 `
        --remote-allow-origins=http://127.0.0.1:9222 `
        --user-data-dir="$env:TEMP\skybrary-edge"

If Edge is installed in the other standard location, use:

    & "C:\Program Files\Microsoft\Edge\Application\msedge.exe" `
        --remote-debugging-port=9222 `
        --remote-allow-origins=http://127.0.0.1:9222 `
        --user-data-dir="$env:TEMP\skybrary-edge"

Once Edge opens, visit SKYbrary normally. If Cloudflare presents a
challenge, complete it manually. The crawler will pause and wait if another
challenge appears later.

STAGES
------

Stage 1 discovers the bookshelf entries:

    python skybrary_crawler.py --index-only

This populates skybrary.db with the publication title, category, author,
date and summary-page URL.

Stage 2 visits every summary page and extracts its actual PDF URL:

    python skybrary_crawler.py --summary-only

The PDF files themselves are NOT downloaded.

Run both stages:

    python skybrary_crawler.py

RESUMING
--------

The SQLite database is the persistent state.

You can stop the crawler with Ctrl+C and restart it later.

Completed summary pages are not processed again.

The crawler does not need to start from the beginning after interruption.

DATABASE STATUS
----------------

Show the current database state:

    python skybrary_crawler.py --stats

Show summary-page errors:

    python skybrary_crawler.py --list-errors

DATABASE
--------

SQLite database:

    skybrary.db

Useful direct SQLite queries:

    sqlite3 skybrary.db

    SELECT COUNT(*) FROM publications;

    SELECT status, COUNT(*)
    FROM publications
    GROUP BY status;

    SELECT COUNT(*)
    FROM publications
    WHERE pdf_url IS NOT NULL;

    SELECT title, pdf_url
    FROM publications
    WHERE pdf_url IS NOT NULL
    LIMIT 20;

    SELECT id, title, error
    FROM publications
    WHERE status = 'error';

The database uses WAL mode and commits progress after each publication.

INDEX OPTIONS
-------------

Start at a particular bookshelf page:

    python skybrary_crawler.py --index-start 20

Only process a limited number of index pages:

    python skybrary_crawler.py --index-start 0 --index-pages 5

CUSTOM DATABASE
---------------

    python skybrary_crawler.py --db another.db

IMPORTANT
---------

Keep the dedicated Edge window open while the crawler is running.

Do not use the normal Edge profile for this. The crawler uses the
dedicated profile created with --user-data-dir.

The crawler deliberately does not attempt to defeat Cloudflare. If a
challenge appears, it pauses until you complete it manually.
"""


# ============================================================================
# MAIN
# ============================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Resumable SKYbrary bookshelf crawler using "
            "a real Edge browser session and SQLite."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help="SQLite database path (default: skybrary.db).",
    )

    parser.add_argument(
        "--index-start",
        type=int,
        default=0,
        help="First bookshelf page to process.",
    )

    parser.add_argument(
        "--index-pages",
        type=int,
        default=None,
        help="Maximum number of index pages to process.",
    )

    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Run only Stage 1.",
    )

    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Run only Stage 2.",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show SQLite progress and exit.",
    )

    parser.add_argument(
        "--list-errors",
        action="store_true",
        help="Show failed summary-page records and exit.",
    )

    args = parser.parse_args()

    db = open_db(args.db)

    try:

        if args.stats:

            show_stats(db)
            return

        if args.list_errors:

            list_errors(db)
            return

        show_stats(db)

        browser = None

        try:

            browser = EdgeCDP()

            if not args.summary_only:

                crawl_index(
                    browser,
                    db,
                    args.index_start,
                    args.index_pages,
                )

            if not args.index_only:

                crawl_summaries(
                    browser,
                    db,
                )

        except KeyboardInterrupt:

            print()
            print("Interrupted.")
            print("SQLite progress has been committed.")

        finally:

            if browser:
                browser.close()

        show_stats(db)

    finally:

        db.close()


if __name__ == "__main__":
    main()