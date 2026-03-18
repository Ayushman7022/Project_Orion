from __future__ import annotations

import re
from typing import Iterable, List

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from langchain.tools import tool


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _clean_text(s: str) -> str:
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def _extract_visible_text(html: str, *, max_chars: int) -> str:
    """
    Extract main-ish readable text from HTML.
    We try paragraphs first, then fall back to full page text.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    paragraphs: List[str] = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if t:
            paragraphs.append(t)

    text = "\n".join(paragraphs).strip()
    if len(text) < 400:
        text = soup.get_text("\n", strip=True)

    text = _clean_text(text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0].strip()
    return text


def _iter_ddg_results(query: str, *, max_links: int) -> Iterable[dict]:
    with DDGS() as ddgs:
        # ddgs.text returns dicts like: {title, href, body}
        yield from ddgs.text(query, max_results=max_links)


@tool("web_crawl")
def web_crawl_tool(query: str) -> str:
    """
    Search the web for fresh info, then download and extract top link text.
    Intended for "latest/current/trending/news" style questions that need content,
    not just search snippets.
    """
    max_links = 3
    max_chars_per_page = 6000

    results = list(_iter_ddg_results(query, max_links=max_links))
    if not results:
        return "No results found."

    out_parts: List[str] = []
    timeout = httpx.Timeout(connect=6.0, read=12.0, write=10.0, pool=10.0)
    headers = {"User-Agent": _UA}

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for i, r in enumerate(results, start=1):
            title = (r.get("title") or "").strip()
            url = (r.get("href") or "").strip()
            out_parts.append(f"RESULT {i}\nTITLE: {title}\nURL: {url}")

            if not url:
                out_parts.append("EXTRACTED_TEXT: (no url)")
                continue

            try:
                resp = client.get(url)
                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    out_parts.append(f"EXTRACTED_TEXT: (skipped non-html content: {content_type})")
                    continue

                extracted = _extract_visible_text(resp.text, max_chars=max_chars_per_page)
                out_parts.append(f"EXTRACTED_TEXT:\n{extracted}")
            except Exception as e:
                out_parts.append(f"EXTRACTED_TEXT: (fetch failed: {e})")

    return "\n\n".join(out_parts)

