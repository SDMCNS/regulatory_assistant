#!/usr/bin/env python3
"""
fast_pdf_downloader.py - High-Speed Cloudflare-Bypassing PDF Downloader.

Leverages the active Edge/Chrome session (port 9222) to extract the golden
Cloudflare clearance cookies (cf_clearance) and User-Agent, allowing fast
multi-streamed downloads without navigating browser tabs.

Includes:
- Thread-safe unique temporary files (prevents Windows file lock collisions)
- Automatic pre-flight sync of files already downloaded to disk
- Duplicate title collision disambiguation
- In-flight retries with backoff for transient network errors
- Persistent retry tracking in DB (re-attempts failed files on subsequent runs)
- --retry-failed option to reset and re-attempt all previously failed files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import websocket


HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE / "skybrary.db"
DEFAULT_OUT_DIR = HERE / "pdfs"
CDP_URL = "http://127.0.0.1:9222/json"
DEFAULT_MAX_ATTEMPTS = 3


def sanitize_filename(name: str, default: str = "document") -> str:
    if not name:
        return default
    clean = re.sub(r'[\\/*?:"<>|]', "", str(name))
    return clean.strip() or default


def safe_unlink(path: Path) -> None:
    """Silently attempts to remove a file, suppressing Windows file lock errors."""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


class CDPCookieExtractor:
    """Extracts authenticated cookies and browser fingerprints from running browser."""

    @staticmethod
    def is_browser_available(cdp_url: str = CDP_URL) -> bool:
        try:
            with urllib.request.urlopen(cdp_url, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    @classmethod
    def get_session_credentials(cls, cdp_url: str = CDP_URL) -> Tuple[List[Dict[str, Any]], str]:
        with urllib.request.urlopen(cdp_url, timeout=5) as resp:
            targets = json.loads(resp.read().decode("utf-8"))

        target = None
        for t in targets:
            if t.get("type") == "page" and "skybrary" in t.get("url", ""):
                target = t
                break
        if not target:
            for t in targets:
                if t.get("type") == "page":
                    target = t
                    break

        if not target:
            raise RuntimeError("No open browser page target found on port 9222.")

        ws_url = target["webSocketDebuggerUrl"]
        ws = websocket.create_connection(ws_url, timeout=10)

        # 1. Fetch cookies
        ws.send(json.dumps({
            "id": 101,
            "method": "Network.getCookies",
            "params": {"urls": ["https://skybrary.aero"]}
        }))
        res1 = json.loads(ws.recv())
        cookies = res1.get("result", {}).get("cookies", [])

        # 2. Fetch User-Agent
        ws.send(json.dumps({
            "id": 102,
            "method": "Runtime.evaluate",
            "params": {"expression": "navigator.userAgent"}
        }))
        res2 = json.loads(ws.recv())
        user_agent = res2.get("result", {}).get("result", {}).get("value") or ""

        ws.close()
        return cookies, user_agent


def build_authenticated_session(cookies: List[Dict[str, Any]], user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Referer": "https://skybrary.aero/bookshelf",
        "Sec-Ch-Ua": '"Chromium";v="154", "Not A(Brand";v="24", "Microsoft Edge";v="154"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    })

    for c in cookies:
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", ".skybrary.aero"),
            path=c.get("path", "/"),
        )

    return session


def sync_existing_files(db_path: Path, out_dir: Path) -> int:
    """
    Checks if files already exist on disk and updates skybrary.db accordingly.
    Avoids re-downloading files that were already completed.
    """
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, category, pdf_url, pdf_path, download_status 
        FROM publications 
        WHERE (download_status != 'complete' OR download_status IS NULL)
          AND pdf_url IS NOT NULL AND pdf_url != ''
    """)
    rows = cur.fetchall()

    synced = 0
    updates = []

    for r in rows:
        doc_id = r["id"]
        title = r["title"] or f"doc_{doc_id}"
        cat = sanitize_filename(r["category"], default="Uncategorized")
        safe_title = sanitize_filename(title, default=f"document_{doc_id}")

        candidate_paths = [
            out_dir / cat / f"{safe_title}.pdf",
            out_dir / cat / f"{safe_title}_{doc_id}.pdf",
            out_dir / "Uncategorized" / f"{safe_title}.pdf",
            out_dir / "Uncategorized" / f"{safe_title}_{doc_id}.pdf",
            out_dir / cat / f"{safe_title}.docx",
            out_dir / cat / f"{safe_title}.xlsx",
            out_dir / cat / f"{safe_title}.pptx",
        ]

        found_path = None
        for p in candidate_paths:
            if p.exists() and p.stat().st_size > 0:
                try:
                    with open(p, "rb") as f:
                        header = f.read(5)
                        if header == b"%PDF-" or header.startswith(b"PK\x03\x04"):
                            found_path = p
                            break
                except OSError:
                    pass

        if found_path:
            rel = str(found_path.relative_to(out_dir.parent))
            updates.append((rel, doc_id))
            synced += 1

    if updates:
        cur.executemany("""
            UPDATE publications 
            SET pdf_path = ?, download_status = 'complete', download_error = NULL
            WHERE id = ?
        """, updates)
        conn.commit()

    conn.close()
    return synced


def download_single_pdf(
    session: requests.Session,
    row: Dict[str, Any],
    out_dir: Path,
    timeout: int = 30,
    max_retries: int = 2,
) -> Tuple[int, bool, str, Optional[str]]:
    doc_id = row["id"]
    title = row["title"] or f"doc_{doc_id}"
    category = row.get("category") or "Uncategorized"
    pdf_url = row["pdf_url"]

    safe_cat = sanitize_filename(category, default="Uncategorized")
    target_dir = out_dir / safe_cat
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_title = sanitize_filename(title, default=f"document_{doc_id}")
    dest_path = target_dir / f"{safe_title}.pdf"

    # Non-PDF extension handling
    url_ext = Path(pdf_url.split("?")[0].rstrip("/")).suffix.lower()
    if url_ext and url_ext not in [".pdf", ""]:
        dest_path = target_dir / f"{safe_title}{url_ext}"

    # Check if primary dest exists and is valid
    if dest_path.exists() and dest_path.stat().st_size > 0:
        try:
            with open(dest_path, "rb") as f:
                header = f.read(5)
                if header == b"%PDF-" or header.startswith(b"PK\x03\x04"):
                    rel_path = str(dest_path.relative_to(out_dir.parent))
                    return doc_id, True, rel_path, None
        except OSError:
            pass

    # Thread-unique temporary file
    part_path = target_dir / f".tmp_{doc_id}_{os.getpid()}_{time.time_ns()}.part"

    last_error = "Unknown error"

    # Immediate in-flight retries with backoff for transient network issues
    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(1.5 * attempt)

        try:
            resp = session.get(pdf_url, stream=True, timeout=timeout)
            if resp.status_code == 403:
                last_error = "Cloudflare 403 Challenge - Cookie may need refresh"
                break
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue

            # Write to thread-unique temporary file
            with open(part_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)

            # Validate magic header if expected to be PDF
            if url_ext in [".pdf", ""]:
                with open(part_path, "rb") as f:
                    magic = f.read(5)
                    if magic != b"%PDF-":
                        safe_unlink(part_path)
                        last_error = "Downloaded file is not a valid PDF (HTML/challenge error)"
                        continue

            # Disambiguate if dest_path already exists (duplicate titles across DB)
            if dest_path.exists():
                dest_path = target_dir / f"{safe_title}_{doc_id}{dest_path.suffix}"

            # Atomic replace / rename
            safe_unlink(dest_path)
            os.replace(part_path, dest_path)

            rel_path = str(dest_path.relative_to(out_dir.parent))
            return doc_id, True, rel_path, None

        except requests.exceptions.RequestException as exc:
            safe_unlink(part_path)
            last_error = f"Network error: {exc}"
            continue
        except Exception as exc:
            safe_unlink(part_path)
            last_error = str(exc)[:200]
            continue

    safe_unlink(part_path)
    return doc_id, False, "", last_error


def reset_failed_downloads(db_path: Path) -> int:
    """Resets error status so previously failed files can be retried fresh."""
    conn = sqlite3.connect(db_path, timeout=60.0)
    with conn:
        cur = conn.cursor()
        cur.execute("UPDATE publications SET download_status = 'pending', download_error = NULL, download_attempts = 0 WHERE download_status = 'error'")
        count = cur.rowcount
    conn.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast PDF Downloader leveraging active Edge session cookies."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to skybrary.db")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Destination directory for PDFs")
    parser.add_argument("--limit", type=int, default=0, help="Number of PDFs to download (0 = all pending)")
    parser.add_argument("--workers", type=int, default=3, help="Concurrent download threads (default: 3)")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help=f"Max total retry attempts per file (default: {DEFAULT_MAX_ATTEMPTS})")
    parser.add_argument("--dry-run", action="store_true", help="Inspect pending count without downloading")
    parser.add_argument("--sync-only", action="store_true", help="Only sync files already on disk to DB without downloading")
    parser.add_argument("--retry-failed", action="store_true", help="Reset all previous error statuses to retry them immediately")
    args = parser.parse_args()

    db_path = args.db.resolve()
    out_dir = args.out_dir.resolve()

    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    # Optional reset of failed downloads
    if args.retry_failed:
        reset_count = reset_failed_downloads(db_path)
        print(f"Reset {reset_count} previously failed publications to pending.")

    # Step 1: Pre-flight disk synchronization
    print(f"Checking disk for already-downloaded files in: {out_dir}")
    synced = sync_existing_files(db_path, out_dir)
    if synced > 0:
        print(f"SUCCESS: Synchronized {synced} existing files from disk to skybrary.db!")

    if args.sync_only:
        return 0

    # Step 2: Check browser status
    if not CDPCookieExtractor.is_browser_available():
        print("ERROR: Edge/Chrome is not detected on port 9222.", file=sys.stderr)
        print("Please ensure the browser is running with remote debugging:", file=sys.stderr)
        print("  msedge.exe --remote-debugging-port=9222 --user-data-dir=\"skybrary_browser_profile\"", file=sys.stderr)
        return 1

    print("Connecting to Edge on port 9222 to extract Cloudflare clearance...")
    try:
        cookies, user_agent = CDPCookieExtractor.get_session_credentials()
        cf_cookie = next((c for c in cookies if c["name"] == "cf_clearance"), None)
        if not cf_cookie:
            print("WARNING: 'cf_clearance' cookie not found in browser session.")
            print("Make sure you visited skybrary.aero and passed any human challenge first.")
        else:
            print(f"SUCCESS: Extracted cf_clearance cookie ({cf_cookie['value'][:15]}...)")
    except Exception as exc:
        print(f"ERROR extracting cookies: {exc}", file=sys.stderr)
        return 1

    session = build_authenticated_session(cookies, user_agent)

    # Step 3: Query remaining pending and eligible-for-retry files from skybrary.db
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Automatically re-includes failed downloads where download_attempts < max_attempts
    # Fresh downloads (download_attempts = 0) are attempted first.
    query = f"""
        SELECT id, title, category, pdf_url, download_attempts 
        FROM publications 
        WHERE pdf_url IS NOT NULL 
          AND pdf_url != ''
          AND download_status != 'complete'
          AND COALESCE(download_attempts, 0) < {args.max_attempts}
        ORDER BY COALESCE(download_attempts, 0) ASC, id ASC
    """
    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    cur.execute(query)
    rows = [dict(r) for r in cur.fetchall()]

    print(f"Found {len(rows)} eligible files to download (Max attempts: {args.max_attempts}, Limit: {args.limit}).")
    if args.dry_run or not rows:
        conn.close()
        return 0

    print(f"Starting downloads with {args.workers} worker(s)...")
    success_count = 0
    failure_count = 0
    t0 = time.time()

    def process_row(r: Dict[str, Any]) -> Tuple[int, bool, str, Optional[str]]:
        return download_single_pdf(session, r, out_dir)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_row, r): r for r in rows}

        for idx, future in enumerate(as_completed(futures), 1):
            r = futures[future]
            try:
                doc_id, success, saved_path, err = future.result()
            except Exception as exc:
                doc_id = r["id"]
                success = False
                saved_path = ""
                err = f"Worker exception: {exc}"

            title_preview = (r.get("title") or f"Doc {doc_id}")[:45]
            if success:
                success_count += 1
                cur.execute("""
                    UPDATE publications 
                    SET pdf_path = ?, download_status = 'complete', download_error = NULL
                    WHERE id = ?
                """, (saved_path, doc_id))
                conn.commit()
                print(f"[{idx}/{len(rows)}] [SUCCESS] #{doc_id:04d} {title_preview} -> {saved_path}")
            else:
                failure_count += 1
                cur.execute("""
                    UPDATE publications 
                    SET download_status = 'error', 
                        download_error = ?,
                        download_attempts = COALESCE(download_attempts, 0) + 1
                    WHERE id = ?
                """, (err, doc_id))
                conn.commit()
                print(f"[{idx}/{len(rows)}] [RETRY LATER] #{doc_id:04d} {title_preview} (Attempt {r.get('download_attempts', 0) + 1}/{args.max_attempts}) -> {err}")

            time.sleep(0.2)

    conn.close()
    elapsed = time.time() - t0

    print()
    print("=" * 60)
    print("FAST DOWNLOAD SUMMARY")
    print("=" * 60)
    print(f"Pre-flight Synced: {synced}")
    print(f"New Downloaded   : {success_count}")
    print(f"Failed (Retried) : {failure_count}")
    print(f"Elapsed Time     : {elapsed:.2f}s")
    print("=" * 60)

    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
