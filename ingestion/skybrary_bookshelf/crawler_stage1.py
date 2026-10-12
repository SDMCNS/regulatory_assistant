import json
import time
import urllib.request
import websocket


TARGET_URL = "https://skybrary.aero/bookshelf/guide-aircraft-ground-deicing"


def get_skybrary_target():
    with urllib.request.urlopen("http://127.0.0.1:9222/json") as response:
        targets = json.load(response)

    for target in targets:
        if (
            target.get("type") == "page"
            and "skybrary.aero" in target.get("url", "")
        ):
            return target

    raise RuntimeError("No SKYbrary browser tab found.")


def cdp_command(ws, command_id, method, params=None):
    message = {
        "id": command_id,
        "method": method,
    }

    if params:
        message["params"] = params

    ws.send(json.dumps(message))

    while True:
        response = json.loads(ws.recv())

        if response.get("id") == command_id:
            return response


target = get_skybrary_target()

print("Connecting to:")
print(target["url"])
print()

ws = websocket.create_connection(
    target["webSocketDebuggerUrl"],
    origin="http://127.0.0.1:9222",
)

command_id = 1

# Navigate the existing Edge tab.
result = cdp_command(
    ws,
    command_id,
    "Page.navigate",
    {"url": TARGET_URL},
)

print("Navigation requested.")
print("Waiting for page...")

time.sleep(5)

# Get rendered HTML from the real browser.
command_id += 1

result = cdp_command(
    ws,
    command_id,
    "Runtime.evaluate",
    {
        "expression": "document.documentElement.outerHTML",
        "returnByValue": True,
    },
)

html = result["result"]["result"]["value"]

print(f"Received {len(html):,} characters of HTML.")

with open("summary.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Saved: summary.html")

# Now inspect every link containing something interesting.
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "html.parser")

print()
print("=" * 100)
print("POTENTIAL DOCUMENT LINKS")
print("=" * 100)

found = 0

for a in soup.find_all("a", href=True):
    href = a["href"]
    text = " ".join(a.get_text(" ", strip=True).split())

    href_lower = href.lower()
    text_lower = text.lower()

    if (
        ".pdf" in href_lower
        or "/sites/default/files/" in href_lower
        or "download" in text_lower
        or "document" in text_lower
        or "publication" in text_lower
    ):
        print()
        print("TEXT :", text)
        print("HREF :", href)
        found += 1

print()
print(f"Found {found} potential document links.")

ws.close()