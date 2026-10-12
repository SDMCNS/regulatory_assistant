from bs4 import BeautifulSoup

with open(
    "skybrary_edge_page.html",
    "r",
    encoding="utf-8",
) as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

for a in soup.find_all("a", href=True):

    text = " ".join(
        a.get_text(" ", strip=True).split()
    )

    href = a["href"]

    if (
        text
        and "bookshelf" in href.lower()
    ):
        print(text)
        print(href)
        print("-" * 80)