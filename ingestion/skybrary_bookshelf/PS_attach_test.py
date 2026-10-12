from __future__ import annotations

import json
import requests
import websocket


DEBUG_URL = "http://127.0.0.1:9222/json"


def get_skybrary_target():
    """Find the currently open SKYbrary page."""

    pages = requests.get(
        DEBUG_URL,
        timeout=10,
    ).json()

    for page in pages:
        if (
            page.get("type") == "page"
            and "skybrary.aero" in page.get("url", "")
        ):
            return page

    raise RuntimeError(
        "Could not find an open SKYbrary page in Edge."
    )


def cdp_command(ws, command_id, method, params=None):
    """Send a Chrome DevTools Protocol command."""

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


def main():

    target = get_skybrary_target()

    print("Found SKYbrary page:")
    print("  Title:", target["title"])
    print("  URL:", target["url"])
    print()

    ws_url = target["webSocketDebuggerUrl"]

    print("Connecting to:")
    print(" ", ws_url)
    print()

    ws = websocket.create_connection(
        ws_url,
        timeout=30,
    )

    # Get the complete DOM as HTML.
    response = cdp_command(
        ws,
        1,
        "Runtime.evaluate",
        {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True,
        },
    )

    html = (
        response
        .get("result", {})
        .get("result", {})
        .get("value", "")
    )

    print(
        f"Received {len(html):,} characters of HTML."
    )

    with open(
        "skybrary_edge_page.html",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(html)

    print()
    print("Saved:")
    print("  skybrary_edge_page.html")

    # Also retrieve visible text.
    response = cdp_command(
        ws,
        2,
        "Runtime.evaluate",
        {
            "expression": "document.body.innerText",
            "returnByValue": True,
        },
    )

    text = (
        response
        .get("result", {})
        .get("result", {})
        .get("value", "")
    )

    print()
    print("-" * 70)
    print("VISIBLE PAGE TEXT")
    print("-" * 70)
    print()
    print(text[:5000])

    ws.close()


if __name__ == "__main__":
    main()