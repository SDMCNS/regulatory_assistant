from __future__ import annotations

import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


URL = "https://skybrary.aero/bookshelf-items?page=0"

# Keep the browser profile between runs.
PROFILE_DIR = Path("skybrary_browser_profile")


def main() -> None:
    print("=" * 70)
    print("SKYbrary Playwright test")
    print("=" * 70)
    print()

    with sync_playwright() as p:

        print("Launching Chromium...")

        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={
                "width": 1440,
                "height": 900,
            },
            locale="en-GB",
            timezone_id="Europe/London",
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        print()
        print("Opening:")
        print(URL)
        print()

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        print("Initial page loaded.")
        print("URL:", page.url)
        print("Title:", page.title())
        print()

        # Give Cloudflare/browser JS time to do whatever it needs.
        print("Waiting for the page/challenge to settle...")
        print()

        for i in range(12):

            time.sleep(5)

            print(
                f"  {((i + 1) * 5):2d}s  "
                f"URL={page.url}  "
                f"TITLE={page.title()!r}"
            )

            # Look for the actual bookshelf content.
            if "bookshelf-items" in page.url.lower():

                text = page.locator("body").inner_text(
                    timeout=5_000
                )

                if len(text) > 1000:
                    print()
                    print("Looks like the actual SKYbrary page has loaded.")
                    break

        print()
        print("-" * 70)
        print("PAGE INFORMATION")
        print("-" * 70)

        print("URL:", page.url)
        print("Title:", page.title())

        html = page.content()

        Path("skybrary_page0.html").write_text(
            html,
            encoding="utf-8",
        )

        print()
        print("Saved page HTML to:")
        print("  skybrary_page0.html")

        # Parse links.
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        links = []

        for a in soup.find_all("a", href=True):

            href = a["href"].strip()

            text = " ".join(
                a.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            if not text:
                continue

            if href.startswith("/"):
                href = "https://skybrary.aero" + href

            if href.startswith(
                "https://skybrary.aero/"
            ):
                links.append(
                    (
                        text,
                        href,
                    )
                )

        print()
        print(f"Found {len(links)} SKYbrary links.")

        print()
        print("-" * 70)
        print("FIRST 30 LINKS")
        print("-" * 70)

        for number, (text, href) in enumerate(
            links[:30],
            start=1,
        ):

            print()
            print(f"{number}. {text}")
            print(f"   {href}")

        print()
        print("-" * 70)
        print("BROWSER LEFT OPEN FOR 30 SECONDS")
        print("-" * 70)
        print()
        print("If the page looks correct, we're ready for the crawler.")

        time.sleep(30)

        browser.close()


if __name__ == "__main__":
    main()