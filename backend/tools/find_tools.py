from __future__ import annotations

import json

from langchain.tools import tool

from find_service import find_apps, find_files


@tool("system_find")
def system_find_tool(name: str, max_hits: int = 25) -> str:
    """
    Find files across the whole Windows PC by filename pattern (not content).
    Examples:
    - name="resume.pdf"
    - name="*.docx"
    - name="project_report"
    """
    hits = find_files(name=name, max_hits=max_hits)
    return json.dumps({"name": name, "hits": [h.__dict__ for h in hits]}, ensure_ascii=False)


@tool("system_find_app")
def system_find_app_tool(name: str, max_hits: int = 25) -> str:
    """
    Find an installed app on Windows (Start Menu shortcuts / common exe paths).
    Better than system_find for queries like "Telegram app" or "Microsoft Word".
    """
    hits = find_apps(name=name, max_hits=max_hits)
    return json.dumps({"name": name, "hits": [h.__dict__ for h in hits]}, ensure_ascii=False)

