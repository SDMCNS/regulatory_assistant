import sqlite3
import requests
import os
import re

# --- Configuration ---
DB_PATH = 'skybrary.db'
TABLE_NAME = 'publications'
BASE_DOWNLOAD_DIR = 'pdfs'
MAX_DOWNLOADS = 0  # Change to 0 to download everything
FORCE_REDOWNLOAD = False  # Set to True to re-download files even if marked 'complete' or on disk


def sanitize_name(name, default="Unknown"):
    if not name:
        return default
    clean = re.sub(r'[\\/*?:"<>|]', "", str(name))
    return clean.strip() or default


def download_pdfs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build the base query
    query = f'''
        SELECT id, title, category, pdf_url, download_attempts 
        FROM {TABLE_NAME} 
        WHERE pdf_url IS NOT NULL 
        AND pdf_url != '' 
    '''

    # Layer 1 Check: Unless forced, only fetch database rows that aren't marked complete
    if not FORCE_REDOWNLOAD:
        query += " AND (download_status != 'complete' OR download_status IS NULL) "

    # Apply the limit if one is set
    if MAX_DOWNLOADS > 0:
        query += f" LIMIT {MAX_DOWNLOADS}"

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"Found {len(rows)} PDFs to process (Limit: {MAX_DOWNLOADS}, Force Redownload: {FORCE_REDOWNLOAD}).")

    for row in rows:
        doc_id = row['id']
        title = row['title']
        category = row['category']
        pdf_url = row['pdf_url']
        attempts = row['download_attempts'] or 0
        attempts += 1

        safe_category = sanitize_name(category, default="Uncategorized")
        category_dir = os.path.join(BASE_DOWNLOAD_DIR, safe_category)
        os.makedirs(category_dir, exist_ok=True)

        safe_title = sanitize_name(title, default=f"document_{doc_id}")
        file_path = os.path.join(category_dir, f"{safe_title}.pdf")

        print(f"[{doc_id}] Downloading: {safe_title[:50]}... ", end="", flush=True)

        # Layer 2 Check: Verify the file doesn't already exist on disk
        if not FORCE_REDOWNLOAD and os.path.exists(file_path):
            print("Skipped (File already exists on disk).")

            # Update DB to ensure it knows the file is already here
            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET pdf_path = ?, download_status = 'complete', download_error = NULL
                WHERE id = ?
            ''', (file_path, doc_id))
            conn.commit()
            continue

        try:
            # We use a user-agent header because some servers block blank/default Python scrapers
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(pdf_url, stream=True, headers=headers, timeout=15)
            response.raise_for_status()

            with open(file_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET pdf_path = ?, 
                    download_status = 'complete', 
                    download_attempts = ?, 
                    download_error = NULL
                WHERE id = ?
            ''', (file_path, attempts, doc_id))

            print("Done.")

        except Exception as e:
            error_msg = str(e)[:200]
            print(f"Error: {error_msg}")

            cursor.execute(f'''
                UPDATE {TABLE_NAME}
                SET download_status = 'error', 
                    download_attempts = ?, 
                    download_error = ?
                WHERE id = ?
            ''', (attempts, error_msg, doc_id))

        conn.commit()

    conn.close()
    print("Finished processing.")


if __name__ == "__main__":
    download_pdfs()