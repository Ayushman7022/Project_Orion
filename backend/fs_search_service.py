from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config import settings
from fs_service import FsSandboxError


@dataclass(frozen=True)
class FsSearchHit:
    path: str
    kind: str  # "name" | "content"
    preview: str | None = None


def _iter_files(root: Path) -> Iterable[Path]:
    # Avoid extremely large directories by skipping common heavy folders.
    skip = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".idea"}
    for p in root.rglob("*"):
        try:
            if any(part in skip for part in p.parts):
                continue
            if p.is_file():
                yield p
        except Exception:
            continue


def search_fs(
    *,
    name_pattern: str | None = None,
    content_query: str | None = None,
    max_hits: int = 50,
    max_preview_chars: int = 180,
) -> list[FsSearchHit]:
    """
    Search within sandbox root by filename pattern and/or content substring.
    - name_pattern supports glob-like matching (e.g. "*.py", "config.*", "*main*")
    - content_query is a case-insensitive substring match on text files.
    """
    root = settings.fs_root
    if not root.exists():
        raise FsSandboxError("Sandbox root does not exist")

    pat = (name_pattern or "").strip()
    q = (content_query or "").strip()
    if not pat and not q:
        return []

    q_lower = q.lower()
    hits: list[FsSearchHit] = []

    for file_path in _iter_files(root):
        rel = str(file_path.relative_to(root))

        if pat and fnmatch.fnmatch(file_path.name, pat):
            hits.append(FsSearchHit(path=rel, kind="name"))
            if len(hits) >= max_hits:
                break

        if q:
            # best-effort: read as text
            try:
                data = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            idx = data.lower().find(q_lower)
            if idx >= 0:
                start = max(0, idx - max_preview_chars // 2)
                end = min(len(data), idx + max_preview_chars // 2)
                preview = data[start:end].replace("\n", " ").replace("\r", " ").strip()
                hits.append(FsSearchHit(path=rel, kind="content", preview=preview))
                if len(hits) >= max_hits:
                    break

    return hits

