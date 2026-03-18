from __future__ import annotations

import json
from typing import Optional

from langchain.tools import tool

from fs_service import delete_path, list_dir, make_dir, read_text, write_text
from fs_search_service import search_fs


@tool("fs_list")
def fs_list_tool(path: str = "") -> str:
    """List directory entries under the sandbox root."""
    entries = list_dir(path)
    payload = {"path": path, "entries": [e.__dict__ for e in entries]}
    return json.dumps(payload, ensure_ascii=False)


@tool("fs_read")
def fs_read_tool(path: str, max_chars: int = 200_000) -> str:
    """Read a UTF-8 text file under the sandbox root."""
    content = read_text(path, max_chars=max_chars)
    payload = {"path": path, "content": content}
    return json.dumps(payload, ensure_ascii=False)


@tool("fs_write")
def fs_write_tool(path: str, content: str) -> str:
    """Write a UTF-8 text file under the sandbox root."""
    write_text(path, content)
    return json.dumps({"ok": True, "path": path}, ensure_ascii=False)


@tool("fs_delete")
def fs_delete_tool(path: str) -> str:
    """Delete a file (not directory) under the sandbox root."""
    delete_path(path)
    return json.dumps({"ok": True, "path": path}, ensure_ascii=False)


@tool("fs_search")
def fs_search_tool(name: str = "", q: str = "", max_hits: int = 50) -> str:
    """
    Search within sandbox root by filename pattern and/or content substring.
    Parameters:
    - name: filename glob, e.g. "*.py" or "*config*"
    - q: text to search inside files (substring, case-insensitive)
    """
    hits = search_fs(name_pattern=name or None, content_query=q or None, max_hits=max_hits)
    return json.dumps({"name": name, "q": q, "hits": [h.__dict__ for h in hits]}, ensure_ascii=False)


@tool("fs_mkdir")
def fs_mkdir_tool(path: str) -> str:
    """Create a directory under the sandbox root."""
    created = make_dir(path, parents=True)
    return json.dumps({"ok": True, "path": created}, ensure_ascii=False)

