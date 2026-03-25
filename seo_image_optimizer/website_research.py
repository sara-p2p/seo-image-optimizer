from __future__ import annotations

from collections import deque
from html import unescape
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def fetch_site_summary(start_url: str, max_pages: int = 5) -> str:
    visited: set[str] = set()
    queue: deque[str] = deque([start_url])
    parsed_start = urlparse(start_url)
    allowed_host = parsed_start.netloc
    collected: list[str] = []

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, headers=HEADERS, timeout=12)
            response.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        body_text = " ".join(soup.stripped_strings)
        if body_text:
            collected.append(f"URL: {url}\nTITLE: {title}\nTEXT: {unescape(body_text[:5000])}")

        for anchor in soup.find_all("a", href=True):
            href = urljoin(url, anchor["href"])
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            if parsed.netloc != allowed_host:
                continue
            path = parsed.path.lower()
            if any(key in path for key in ("about", "service", "portfolio", "experience", "contact", "pricing")):
                if href not in visited:
                    queue.append(href)

    return "\n\n".join(collected)
