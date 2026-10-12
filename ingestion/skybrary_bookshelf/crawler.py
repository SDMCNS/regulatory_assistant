from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin

import websocket
from bs4 import BeautifulSoup


BASE_URL = "https://skybrary.aero"
CDP_URL = "http://127.0.0.1:9222/json"
DEFAULT_DB = "skybrary.db"
DEFAULT_PDF_DIR = "pdfs"

# ---------------------------------------------------------------------------
# Adaptive pacing
# ---------------------------------------------------------------------------

INDEX_MIN_DELAY = 1.0
INDEX_MAX_DELAY = 15.0

SUMMARY_MIN_DELAY = 1.5
SUMMARY_MAX_DELAY = 60.0

BACKOFF_MULTIPLIER = 2.5
RECOVERY_FACTOR = 0.92

CLEAN_REQUESTS_FOR_RECOVERY = 25
CHALLENGE_WINDOW = 50

PAGE_TIMEOUT = 45
PDF_TIMEOUT = 120


# ===========================================================================
# GENERAL
# ===========================================================================

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


# ===========================================================================
# ADAPTIVE RATE CONTROLLER
# ===========================================================================

class AdaptiveRateController:

    def __init__(
        self,
        minimum: float,
        maximum: float,
    ):
        self.minimum = minimum
        self.maximum = maximum

        self.delay = random.uniform(
            minimum,
            maximum,
        )

        self.clean_requests = 0
        self.challenge_count = 0
        self.recent_requests: list[bool] = []

    def before_request(self) -> None:

        jitter = random.uniform(
            0.85,
            1.15,
        )

        delay = max(
            self.minimum,
            min(
                self.maximum,
                self.delay * jitter,
            ),
        )

        print(
            f"  pacing: {delay:.1f}s "
            f"(base {self.delay:.1f}s)"
        )

        time.sleep(delay)

    def record_success(self) -> None:

        self.recent_requests.append(False)

        if len(self.recent_requests) > CHALLENGE_WINDOW:
            self.recent_requests.pop(0)

        self.clean_requests += 1

        if self.clean_requests >= CLEAN_REQUESTS_FOR_RECOVERY:

            old_delay = self.delay

            self.delay *= RECOVERY_FACTOR

            self.delay = max(
                self.minimum,
                self.delay,
            )

            self.clean_requests = 0

            if self.delay < old_delay:
                print(
                    f"  clean run: reducing pacing "
                    f"{old_delay:.1f}s -> {self.delay:.1f}s"
                )

    def record_challenge(self) -> None:

        self.recent_requests.append(True)

        if len(self.recent_requests) > CHALLENGE_WINDOW:
            self.recent_requests.pop(0)

        self.challenge_count += 1
        self.clean_requests = 0

        old_delay = self.delay

        self.delay *= BACKOFF_MULTIPLIER

        self.delay = min(
            self.maximum,
            self.delay,
        )

        print(
            f"  ADAPTIVE BACKOFF: "
            f"{old_delay:.1f}s -> {self.delay:.1f}s"
        )

    def status(self) -> str:

        if not self.recent_requests:
            return (
                f"delay={self.delay:.1f}s, "
                "no challenge history"
            )

        challenges = sum(
            self.recent_requests
        )

        total = len(
            self.recent_requests
        )

        rate = (
            challenges / total * 100
            if total
            else 0
        )

        return (
            f"delay={self.delay:.1f}s, "
            f"{challenges}/{total} challenges "
            f"({rate:.1f}%)"
        )


# ===========================================================================
# SQLITE
# ===========================================================================

def ensure_column(
    db: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:

    columns = {
        row["name"]
        for row in db.execute(
            f"PRAGMA table_info({table})"
        )
    }

    if column not in columns:
        db.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {definition}
            """
        )

        db.commit()


def open_db(path: str) -> sqlite3.Connection:

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")

    db.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT,
            category TEXT,
            author TEXT,
            publication_date TEXT,

            summary_url TEXT NOT NULL UNIQUE,
            pdf_url TEXT,
            pdf_path TEXT,

            status TEXT NOT NULL DEFAULT 'discovered',
            download_status TEXT NOT NULL DEFAULT 'pending',

            attempts INTEGER NOT NULL DEFAULT 0,
            download_attempts INTEGER NOT NULL DEFAULT 0,

            error TEXT,
            download_error TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Migrate databases created by earlier versions.
    ensure_column(
        db,
        "publications",
        "pdf_path",
        "TEXT",
    )

    ensure_column(
        db,
        "publications",
        "download_status",
        "TEXT NOT NULL DEFAULT 'pending'",
    )

    ensure_column(
        db,
        "publications",
        "download_attempts",
        "INTEGER NOT NULL DEFAULT 0",
    )

    ensure_column(
        db,
        "publications",
        "download_error",
        "TEXT",
    )

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_publications_status
        ON publications(status)
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_publications_download_status
        ON publications(download_status)
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
    """, (
        utc_now(),
        row_id,
    ))

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


# ===========================================================================
# EDGE / CDP
# ===========================================================================

def get_browser_target() -> dict:

    with urllib.request.urlopen(
        CDP_URL,
        timeout=10,
    ) as response:

        targets = json.load(response)

    for target in targets:

        if (
            target.get("type") == "page"
            and "skybrary.aero" in target.get("url", "")
        ):
            return target

    for target in targets:

        if target.get("type") == "page":
            return target

    raise RuntimeError(
        "No browser page found. "
        "Start Edge with remote debugging first."
    )


class EdgeCDP:

    def __init__(self):

        target = get_browser_target()

        print()
        print("Attaching to Edge:")
        print(
            f"  {target.get('url')}"
        )
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

        self.ws.send(
            json.dumps(message)
        )

        while True:

            response = json.loads(
                self.ws.recv()
            )

            if response.get("id") == command_id:
                return response

    def evaluate(
        self,
        expression: str,
    ):

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

    def navigate(
        self,
        url: str,
    ) -> None:

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

            url = state["url"]
            title = state["title"]
            body = state["body"]

            if is_cloudflare_challenge(
                title,
                body,
            ):
                raise CloudflareChallenge()

            if state["readyState"] == "complete":

                if expected_url is None:
                    return state

                if (
                    normalise_url(url)
                    == normalise_url(expected_url)
                ):
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


# ===========================================================================
# CLOUDFLARE HANDLING
# ===========================================================================

def wait_for_cloudflare_resolution(
    browser: EdgeCDP,
) -> None:

    print()
    print("=" * 80)
    print("CLOUDFLARE CHALLENGE DETECTED")
    print("=" * 80)
    print()
    print(
        "Complete the challenge manually in Edge."
    )
    print(
        "The crawler is paused."
    )
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

            print(
                "Challenge cleared."
            )

            time.sleep(5)

            return


# ===========================================================================
# BOOKSHELF INDEX
# ===========================================================================

def parse_bookshelf_index(
    html: str,
) -> list[dict]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    records = []

    for row in soup.select(
        "table tbody tr"
    ):

        cells = row.find_all("td")

        link = row.find(
            "a",
            href=True,
        )

        if not link:
            continue

        href = link["href"]

        if not href.startswith(
            "/bookshelf/"
        ):
            continue

        title = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        if not title:
            continue

        values = [
            " ".join(
                cell.get_text(
                    " ",
                    strip=True,
                ).split()
            )
            for cell in cells
        ]

        records.append({
            "title": title,
            "category": (
                values[1]
                if len(values) > 1
                else ""
            ),
            "author": (
                values[2]
                if len(values) > 2
                else ""
            ),
            "publication_date": (
                values[3]
                if len(values) > 3
                else ""
            ),
            "summary_url": absolute_url(
                href
            ),
        })

    if not records:

        for link in soup.find_all(
            "a",
            href=True,
        ):

            href = link["href"]

            if not href.startswith(
                "/bookshelf/"
            ):
                continue

            title = " ".join(
                link.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if title:

                records.append({
                    "title": title,
                    "category": "",
                    "author": "",
                    "publication_date": "",
                    "summary_url": absolute_url(
                        href
                    ),
                })

    unique = {}

    for record in records:
        unique[
            record["summary_url"]
        ] = record

    return list(
        unique.values()
    )


# ===========================================================================
# SUMMARY PAGE → PDF URL
# ===========================================================================

def find_pdf_url(
    html: str,
) -> str | None:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = []

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link["href"]

        text = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        href_lower = href.lower()
        text_lower = text.lower()

        score = 0

        if ".pdf" in href_lower:
            score += 100

        if (
            "/sites/default/files/bookshelf/"
            in href_lower
        ):
            score += 100

        if "view publication" in text_lower:
            score += 50

        if "download" in text_lower:
            score += 20

        if "publication" in text_lower:
            score += 10

        if score:

            candidates.append(
                (
                    score,
                    absolute_url(href),
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


# ===========================================================================
# STAGE 1 — INDEX
# ===========================================================================

def crawl_index(
    browser: EdgeCDP,
    db: sqlite3.Connection,
    rate: AdaptiveRateController,
    start_page: int,
    max_pages: int | None,
) -> None:

    print()
    print("=" * 80)
    print("STAGE 1 — DISCOVER BOOKSHELF ENTRIES")
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
        print(
            f"[INDEX] page {page}"
        )
        print(url)

        rate.before_request()

        try:

            browser.navigate(url)

            try:

                browser.wait_for_page(url)

            except CloudflareChallenge:

                rate.record_challenge()

                wait_for_cloudflare_resolution(
                    browser
                )

                browser.navigate(url)

                browser.wait_for_page(url)

            html = browser.html()

            records = parse_bookshelf_index(
                html
            )

            rate.record_success()

            if not records:

                empty_pages += 1

                print(
                    "  No records found "
                    f"(empty={empty_pages})"
                )

                if empty_pages >= 2:

                    print(
                        "Two consecutive empty "
                        "pages. Index complete."
                    )

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
                    """
                    SELECT COUNT(*)
                    FROM publications
                    """
                ).fetchone()[0]

                print(
                    f"  Found: {len(records)}"
                )

                print(
                    f"  SQLite total: {total:,}"
                )

        except Exception as exc:

            print(
                f"  ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

            print(
                "  Retrying after 30 seconds."
            )

            time.sleep(30)

            continue

        page += 1

        print(
            f"  {rate.status()}"
        )


# ===========================================================================
# STAGE 2 — SUMMARY PAGES
# ===========================================================================

def get_pending_publications(
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
    rate: AdaptiveRateController,
) -> None:

    rows = get_pending_publications(db)

    total = len(rows)

    print()
    print("=" * 80)
    print("STAGE 2 — SUMMARY PAGES → PDF URLS")
    print("=" * 80)
    print()
    print(
        f"Pending: {total:,}"
    )

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
            f"[PDF URL] {position:,}/{total:,}"
        )

        print(title)
        print(summary_url)

        mark_attempt(
            db,
            row_id,
        )

        rate.before_request()

        try:

            browser.navigate(
                summary_url
            )

            try:

                browser.wait_for_page(
                    summary_url
                )

            except CloudflareChallenge:

                rate.record_challenge()

                wait_for_cloudflare_resolution(
                    browser
                )

                recovery_delay = random.uniform(
                    rate.delay,
                    min(
                        rate.maximum,
                        rate.delay * 1.5,
                    ),
                )

                print(
                    f"  Post-challenge pause: "
                    f"{recovery_delay:.1f}s"
                )

                time.sleep(
                    recovery_delay
                )

                browser.navigate(
                    summary_url
                )

                browser.wait_for_page(
                    summary_url
                )

            html = browser.html()

            pdf_url = find_pdf_url(
                html
            )

            if pdf_url:

                mark_complete(
                    db,
                    row_id,
                    pdf_url,
                )

                rate.record_success()

                print(
                    "  PDF:"
                )

                print(
                    f"  {pdf_url}"
                )

            else:

                rate.record_success()

                mark_error(
                    db,
                    row_id,
                    "No PDF link found",
                )

                print(
                    "  WARNING: no PDF link found"
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
                f"  ERROR: {error}"
            )

        print(
            f"  {rate.status()}"
        )


# ===========================================================================
# STAGE 3 — PDF DOWNLOAD
# ===========================================================================

def safe_filename(text: str) -> str:

    text = unquote(text)

    text = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    text = text.rstrip(".")

    if not text:
        text = "publication"

    return text[:180]


def pdf_filename(
    row: sqlite3.Row,
) -> Path:

    title = safe_filename(
        row["title"] or "publication"
    )
    
    category = safe_filename(
        row["category"] or "Uncategorised"
    )

    return Path(category) / f"{row['id']:06d}_{title}.pdf"


def download_pdf(
    row: sqlite3.Row,
    output_dir: Path,
    cookies: str | None = None,
    user_agent: str | None = None,
) -> Path:

    destination = (
        output_dir
        / pdf_filename(row)
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_suffix(
        ".pdf.part"
    )

    if (
        destination.exists()
        and destination.stat().st_size > 0
    ):

        with open(
            destination,
            "rb",
        ) as check:

            if check.read(5) == b"%PDF-":
                return destination

        destination.unlink(
            missing_ok=True
        )

    headers = {
        "User-Agent": user_agent or (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/154.0 Safari/537.36"
        ),
        "Accept": (
            "application/pdf,"
            "application/octet-stream,"
            "*/*"
        ),
        "Referer": row["summary_url"],
    }

    if cookies:
        headers["Cookie"] = cookies

    request = urllib.request.Request(
        row["pdf_url"],
        headers=headers,
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=PDF_TIMEOUT,
        ) as response:

            with open(
                temporary,
                "wb",
            ) as output:

                while True:

                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    output.write(chunk)

        if not temporary.exists():

            raise RuntimeError(
                "Temporary PDF was not created"
            )

        size = temporary.stat().st_size

        if size < 1000:

            temporary.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                f"Downloaded file is "
                f"suspiciously small "
                f"({size} bytes)"
            )

        with open(
            temporary,
            "rb",
        ) as check:

            magic = check.read(5)

        if magic != b"%PDF-":

            temporary.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                "Downloaded content "
                "is not a PDF"
            )

        temporary.replace(
            destination
        )

        return destination

    except Exception:

        temporary.unlink(
            missing_ok=True
        )

        raise


def crawl_downloads(
    db: sqlite3.Connection,
    output_dir: Path,
    browser: EdgeCDP | None = None,
) -> None:

    rows = db.execute("""
        SELECT *
        FROM publications
        WHERE pdf_url IS NOT NULL
          AND (
              download_status != 'complete'
              OR pdf_path IS NULL
          )
        ORDER BY id
    """).fetchall()

    total = len(rows)

    print()
    print("=" * 80)
    print("STAGE 3 — DOWNLOAD PDFS")
    print("=" * 80)
    print()
    print(
        f"PDFs pending: {total:,}"
    )
    print(
        f"Destination: {output_dir.resolve()}"
    )

    cookies = None
    user_agent = None
    if browser:
        try:
            res = browser.command("Network.getCookies", {"urls": [BASE_URL]})
            cookie_list = [
                f"{c['name']}={c['value']}"
                for c in res.get("result", {}).get("cookies", [])
            ]
            if cookie_list:
                cookies = "; ".join(cookie_list)
            
            user_agent = browser.evaluate("navigator.userAgent")
        except Exception as e:
            print(f"Warning: Failed to get cookies/user-agent from browser: {e}")

    for position, row in enumerate(
        rows,
        start=1,
    ):

        print()
        print("-" * 80)

        print(
            f"[DOWNLOAD] "
            f"{position:,}/{total:,}"
        )

        print(
            row["title"]
        )

        print(
            row["pdf_url"]
        )

        db.execute("""
            UPDATE publications
            SET download_attempts =
                    download_attempts + 1,
                updated_at = ?
            WHERE id = ?
        """, (
            utc_now(),
            row["id"],
        ))

        db.commit()

        try:

            path = download_pdf(
                row,
                output_dir,
                cookies=cookies,
                user_agent=user_agent,
            )

            size = path.stat().st_size

            db.execute("""
                UPDATE publications
                SET pdf_path = ?,
                    download_status = 'complete',
                    download_error = NULL,
                    updated_at = ?
                WHERE id = ?
            """, (
                str(path),
                utc_now(),
                row["id"],
            ))

            db.commit()

            print(
                f"  Downloaded: "
                f"{path.name}"
            )

            print(
                f"  Size: {size:,} bytes"
            )

        except Exception as exc:

            error = (
                f"{type(exc).__name__}: {exc}"
            )

            db.execute("""
                UPDATE publications
                SET download_status = 'error',
                    download_error = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                error[:4000],
                utc_now(),
                row["id"],
            ))

            db.commit()

            print(
                f"  ERROR: {error}"
            )


# ===========================================================================
# SQLITE STATUS
# ===========================================================================

def show_stats(
    db: sqlite3.Connection,
) -> None:

    total = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        """
    ).fetchone()[0]

    discovered = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'discovered'
        """
    ).fetchone()[0]

    complete = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'complete'
        """
    ).fetchone()[0]

    errors = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE status = 'error'
        """
    ).fetchone()[0]

    pdfs = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE pdf_url IS NOT NULL
        """
    ).fetchone()[0]

    downloaded = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE download_status = 'complete'
        """
    ).fetchone()[0]

    download_errors = db.execute(
        """
        SELECT COUNT(*)
        FROM publications
        WHERE download_status = 'error'
        """
    ).fetchone()[0]

    print()
    print("=" * 80)
    print("SKYBRARY SQLITE STATUS")
    print("=" * 80)

    print(
        f"Publications discovered : {total:,}"
    )

    print(
        f"Awaiting PDF resolution : {discovered:,}"
    )

    print(
        f"PDF URLs found          : {pdfs:,}"
    )

    print(
        f"Summary pages complete  : {complete:,}"
    )

    print(
        f"Summary page errors     : {errors:,}"
    )

    print(
        f"PDFs downloaded         : {downloaded:,}"
    )

    print(
        f"PDF download errors     : {download_errors:,}"
    )

    print("=" * 80)


def list_errors(
    db: sqlite3.Connection,
) -> None:

    rows = db.execute(
        """
        SELECT
            id,
            title,
            summary_url,
            attempts,
            error,
            download_attempts,
            download_error
        FROM publications
        WHERE status = 'error'
           OR download_status = 'error'
        ORDER BY id
        """
    ).fetchall()

    if not rows:

        print(
            "No errors."
        )

        return

    print()
    print("=" * 80)
    print("ERRORS")
    print("=" * 80)

    for row in rows:

        print()
        print(
            f"ID       : {row['id']}"
        )

        print(
            f"Title    : {row['title']}"
        )

        if row["status"] == "error":

            print(
                f"Attempts : {row['attempts']}"
            )

            print(
                f"URL      : {row['summary_url']}"
            )

            print(
                f"Error    : {row['error']}"
            )

        if row["download_status"] == "error":

            print(
                f"Downloads: "
                f"{row['download_attempts']}"
            )

            print(
                f"PDF error: "
                f"{row['download_error']}"
            )


# ===========================================================================
# HELP
# ===========================================================================

HELP_EPILOG = r"""
EDGE SETUP
----------

Close normal Edge:

    taskkill /F /IM msedge.exe

Launch the dedicated crawler browser:

    & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
        --remote-debugging-port=9222 `
        --remote-allow-origins=http://127.0.0.1:9222 `
        --user-data-dir="$env:TEMP\skybrary-edge"

Or, if Edge is installed here:

    & "C:\Program Files\Microsoft\Edge\Application\msedge.exe" `
        --remote-debugging-port=9222 `
        --remote-allow-origins=http://127.0.0.1:9222 `
        --user-data-dir="$env:TEMP\skybrary-edge"

Leave that Edge window open while Stages 1 and 2 run.

If Cloudflare presents a challenge, complete it manually.
The crawler will pause and then continue.

WORKFLOW
--------

Stage 1:
Discover all SKYbrary bookshelf publications.

    python skybrary_crawler.py --index-only

Stage 2:
Visit the publication pages and find their PDF URLs.

    python skybrary_crawler.py --summary-only

Stage 3:
Download all discovered PDFs.

    python skybrary_crawler.py --download-only

The three stages can be run independently and safely resumed.

DATABASE
--------

Default database:

    skybrary.db

PDF directory:

    skybrary_pdfs

Show progress:

    python skybrary_crawler.py --stats

Show errors:

    python skybrary_crawler.py --list-errors

Custom database:

    python skybrary_crawler.py --db my.db

Custom PDF directory:

    python skybrary_crawler.py --download-only --pdf-dir pdfs

INDEX OPTIONS
-------------

Start at page 20:

    python skybrary_crawler.py --index-start 20

Process only five index pages:

    python skybrary_crawler.py --index-start 0 --index-pages 5

ADAPTIVE PACING
---------------

Index pages start at approximately 1–2.5 seconds.

Summary pages start at approximately 1.5–4 seconds.

If Cloudflare challenges the crawler, the relevant delay is
multiplied by 2.5.

Repeated challenges increase the delay up to the configured maximum.

After 25 clean requests, the delay gradually decreases.

There is no artificial long pause every N requests.

PDF downloads are performed separately using normal HTTP requests
after the PDF URL has been discovered.

RESUMING
--------

SQLite is the persistent state.

Ctrl+C is safe.

Run the same command again to continue.

Completed records are skipped.

Partial PDF downloads use .pdf.part and are not treated as
completed downloads.

USEFUL SQLITE QUERIES
---------------------

    sqlite3 skybrary.db

    SELECT COUNT(*)
    FROM publications;

    SELECT status, COUNT(*)
    FROM publications
    GROUP BY status;

    SELECT download_status, COUNT(*)
    FROM publications
    GROUP BY download_status;

    SELECT COUNT(*)
    FROM publications
    WHERE pdf_url IS NOT NULL;

    SELECT COUNT(*)
    FROM publications
    WHERE download_status = 'complete';

    SELECT title, pdf_url
    FROM publications
    WHERE pdf_url IS NOT NULL
    LIMIT 20;

    SELECT id, title, attempts, error
    FROM publications
    WHERE status = 'error';

    SELECT id, title, download_attempts, download_error
    FROM publications
    WHERE download_status = 'error';

IMPORTANT
---------

The crawler does not attempt to bypass Cloudflare.

If a Cloudflare challenge appears during browser crawling,
complete it manually.

If a PDF download returns something other than a PDF, the
download is marked as an error and can be retried later.

PDF files are never considered complete unless their contents
begin with the PDF magic header: %PDF-.
"""


# ===========================================================================
# MAIN
# ===========================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Resumable SKYbrary bookshelf crawler "
            "using Edge CDP, SQLite and PDF downloading."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=(
            "SQLite database path "
            "(default: skybrary.db)"
        ),
    )

    parser.add_argument(
        "--pdf-dir",
        default=DEFAULT_PDF_DIR,
        help=(
            "PDF output directory "
            "(default: skybrary_pdfs)"
        ),
    )

    parser.add_argument(
        "--index-start",
        type=int,
        default=0,
        help=(
            "First bookshelf page "
            "(default: 0)"
        ),
    )

    parser.add_argument(
        "--index-pages",
        type=int,
        default=None,
        help=(
            "Maximum number of index pages "
            "to process."
        ),
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
        "--download-only",
        action="store_true",
        help="Run only Stage 3.",
    )

    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip Stage 1 (Index) and start from Stage 2.",
    )

    parser.add_argument(
        "--download",
        action="store_true",
        help="Run Stage 3 (Download) after browser stages.",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show SQLite progress and exit.",
    )

    parser.add_argument(
        "--list-errors",
        action="store_true",
        help="Show failed records and exit.",
    )

    parser.add_argument(
        "--fast-pacing",
        action="store_true",
        help="Override all pacing to a flat 1s delay for testing.",
    )

    args = parser.parse_args()

    selected_modes = sum([
        args.index_only,
        args.summary_only,
        args.download_only,
    ])

    if selected_modes > 1:

        parser.error(
            "--index-only, --summary-only and "
            "--download-only are mutually exclusive."
        )

    db = open_db(args.db)

    try:

        if args.stats:

            show_stats(db)
            return

        if args.list_errors:

            list_errors(db)
            return

        # ---------------------------------------------------------------
        # Stage 3 only
        # ---------------------------------------------------------------

        if args.download_only:

            browser = EdgeCDP()
            try:
                crawl_downloads(
                    db,
                    Path(args.pdf_dir),
                    browser,
                )
            finally:
                browser.close()

            show_stats(db)
            return

        # ---------------------------------------------------------------
        # Browser stages
        # ---------------------------------------------------------------

        browser = None

        try:

            browser = EdgeCDP()

            # -----------------------------------------------------------
            # Stage 1
            # -----------------------------------------------------------

            if not args.summary_only and not args.skip_index:

                index_rate = AdaptiveRateController(
                    minimum=1.0 if args.fast_pacing else INDEX_MIN_DELAY,
                    maximum=1.0 if args.fast_pacing else INDEX_MAX_DELAY,
                )

                crawl_index(
                    browser,
                    db,
                    index_rate,
                    args.index_start,
                    args.index_pages,
                )

            # -----------------------------------------------------------
            # Stage 2
            # -----------------------------------------------------------

            if not args.index_only:

                summary_rate = AdaptiveRateController(
                    minimum=1.0 if args.fast_pacing else SUMMARY_MIN_DELAY,
                    maximum=1.0 if args.fast_pacing else SUMMARY_MAX_DELAY,
                )

                crawl_summaries(
                    browser,
                    db,
                    summary_rate,
                )

            # -----------------------------------------------------------
            # Stage 3 (if requested)
            # -----------------------------------------------------------

            if args.download and not args.index_only:
                crawl_downloads(
                    db,
                    Path(args.pdf_dir),
                    browser,
                )

        except KeyboardInterrupt:

            print()
            print(
                "Interrupted by user."
            )

            print(
                "Committed SQLite progress is safe."
            )

        finally:

            if browser:
                browser.close()

        show_stats(db)

    finally:

        db.close()


if __name__ == "__main__":
    main()