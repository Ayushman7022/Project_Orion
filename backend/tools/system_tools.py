from __future__ import annotations

import json

from langchain.tools import tool

from system_service import open_target


@tool("system_open")
def system_open_tool(target: str) -> str:
    """
    Open a URL, a sandboxed file/folder, or a Windows app by name.
    Example inputs:
    - https://example.com
    - Documents/notes.txt
    - calculator
    """
    res = open_target(target)
    return json.dumps(
        {"ok": res.ok, "kind": res.kind, "target": res.target, "detail": res.detail},
        ensure_ascii=False,
    )

