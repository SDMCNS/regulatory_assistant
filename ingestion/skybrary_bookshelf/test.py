import requests

url = "https://skybrary.aero/bookshelf-items?page=0"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://skybrary.aero/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

r = requests.get(
    url,
    headers=headers,
    timeout=30,
)

print("Status:", r.status_code)
print("URL:", r.url)
print("Server:", r.headers.get("Server"))
print("Content-Type:", r.headers.get("Content-Type"))
print()
print(r.text[:2000])