from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config import settings


class FsSandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class FsEntry:
    path: str
    type: str  # "file" | "dir"


def _safe_join(rel_path: str) -> Path:
    rel = (rel_path or "").strip().lstrip("/\\")
    candidate = (settings.fs_root / rel).resolve()
    root = settings.fs_root
    try:
        candidate.relative_to(root)
    except Exception as e:
        raise FsSandboxError("Path escapes sandbox root") from e
    return candidate


def list_dir(rel_path: str = "") -> list[FsEntry]:
    p = _safe_join(rel_path)
    if not p.exists():
        raise FileNotFoundError(rel_path)
    if not p.is_dir():
        raise NotADirectoryError(rel_path)
    out: list[FsEntry] = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        out.append(FsEntry(path=str(child.relative_to(settings.fs_root)), type="dir" if child.is_dir() else "file"))
    return out


def read_text(rel_path: str, max_chars: int = 200_000) -> str:
    p = _safe_join(rel_path)
    if not p.exists():
        raise FileNotFoundError(rel_path)
    if not p.is_file():
        raise IsADirectoryError(rel_path)
    data = p.read_text(encoding="utf-8", errors="replace")
    return data[:max_chars]


def write_text(rel_path: str, content: str, create_parents: bool = True) -> None:
    p = _safe_join(rel_path)
    if create_parents:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or "", encoding="utf-8")


def make_dir(rel_path: str, parents: bool = True) -> str:
    p = _safe_join(rel_path)
    p.mkdir(parents=parents, exist_ok=True)
    return str(p.relative_to(settings.fs_root))


def delete_path(rel_path: str) -> None:
    p = _safe_join(rel_path)
    if not p.exists():
        return
    if p.is_dir():
        raise IsADirectoryError("Refusing to delete directories via API")
    p.unlink(missing_ok=True)

