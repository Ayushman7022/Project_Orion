from typing import List

from ddgs import DDGS
from langchain.tools import tool


def _format_results(results: List[dict]) -> str:
    lines: List[str] = []
    for i, r in enumerate(results, start=1):
        title = r.get("title") or ""
        href = r.get("href") or ""
        body = r.get("body") or ""
        lines.append(f"{i}. {title}\n{href}\n{body}\n")
    return "\n".join(lines) if lines else "No results found."


@tool("web_search")
def web_search_tool(query: str) -> str:
    """
    Search the web using DuckDuckGo.
    Use when you need fresh internet information.
    """
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    return _format_results(results)

