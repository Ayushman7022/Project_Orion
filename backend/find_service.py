from __future__ import annotations

import re
import string
import subprocess
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class FindHit:
    path: str


_BAD_CHARS_RE = re.compile(r"[&|;><`]")


def _safe_pattern(pat: str) -> str:
    p = (pat or "").strip().strip('"').strip("'")
    if not p:
        raise ValueError("Empty filename pattern")
    if _BAD_CHARS_RE.search(p):
        raise ValueError("Pattern rejected by safety filter")
    # Strip common filler words so "telegram app" still matches Telegram.exe / Telegram.lnk
    p = re.sub(r"(?i)\b(app|application|desktop app|software|program)\b", "", p).strip()
    # If user provides a bare name without wildcard/extension, try to make it useful.
    if "*" not in p and "?" not in p and "." not in p:
        p = f"*{p}*"
    return p


def _available_roots() -> list[str]:
    # Prefer searching common user folders first (much faster than scanning C:\).
    roots: list[str] = []
    home = Path.home()
    for p in [
        home,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "OneDrive",
        home / "OneDrive" / "Desktop",
        home / "OneDrive" / "Documents",
        home / "OneDrive" / "Downloads",
    ]:
        try:
            if p.exists():
                roots.append(str(p))
        except Exception:
            pass

    for d in string.ascii_uppercase:
        drive = Path(f"{d}:\\")
        if drive.exists():
            # Avoid duplicates (e.g. home is on C:\)
            dp = str(drive)
            if dp not in roots:
                roots.append(dp)
    return roots


def _run_where(root: str, pattern: str, timeout_s: float) -> list[str]:
    # where.exe supports wildcards; /r <root> <pattern>
    completed = subprocess.run(
        ["where", "/r", root, pattern],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
        shell=False,
    )
    # where returns exit code 1 if not found; treat that as empty.
    if completed.returncode not in (0, 1):
        raise RuntimeError((completed.stderr or "").strip() or f"where.exe failed ({completed.returncode})")
    lines = [ln.strip() for ln in (completed.stdout or "").splitlines() if ln.strip()]
    return lines


def find_files(
    *,
    name: str,
    max_hits: int = 25,
    timeout_s_per_root: float = 10.0,
    roots: list[str] | None = None,
) -> list[FindHit]:
    """
    Find files across available Windows drives using where.exe.
    This is read-only and only searches by filename pattern (not content).
    """
    pattern = _safe_pattern(name)
    search_roots = roots or _available_roots()
    hits: list[FindHit] = []

    for root in search_roots:
        if len(hits) >= max_hits:
            break
        # User folders can still be large; give them a bit more time than whole-drive roots.
        per_root_timeout = timeout_s_per_root
        if re.match(r"^[A-Z]:\\\\$", root, flags=re.IGNORECASE):
            per_root_timeout = min(timeout_s_per_root, 6.0)
        else:
            per_root_timeout = max(timeout_s_per_root, 12.0)
        try:
            paths = _run_where(root, pattern, timeout_s=per_root_timeout)
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

        for p in paths:
            hits.append(FindHit(path=p))
            if len(hits) >= max_hits:
                break

    return hits


def find_apps(
    *,
    name: str,
    max_hits: int = 25,
) -> list[FindHit]:
    """
    Find installed apps more precisely than find_files():
    - Start Menu shortcuts (*.lnk)
    - Common install dirs for executables (*.exe)
    This avoids returning irrelevant source files like "telegram.py".
    """
    q = (name or "").strip().strip('"').strip("'")
    if not q:
        raise ValueError("Empty app name")
    if _BAD_CHARS_RE.search(q):
        raise ValueError("Name rejected by safety filter")

    # Normalize: remove "app/application" etc.
    q = re.sub(r"(?i)\b(app|application|desktop app|software|program)\b", "", q).strip()
    if not q:
        raise ValueError("Empty app name")

    token = q.lower().strip()
    hits: list[FindHit] = []

    def add(p: str) -> None:
        nonlocal hits
        if p and all(h.path.lower() != p.lower() for h in hits):
            hits.append(FindHit(path=p))

    # 1) Start Menu shortcuts
    start_dirs: list[Path] = []
    appdata = Path(os.environ.get("APPDATA", "") or "")
    programdata = Path(os.environ.get("PROGRAMDATA", "") or "")
    if appdata:
        start_dirs.append(appdata / r"Microsoft\Windows\Start Menu\Programs")
    if programdata:
        start_dirs.append(programdata / r"Microsoft\Windows\Start Menu\Programs")

    for root in start_dirs:
        if len(hits) >= max_hits:
            break
        if not root.exists():
            continue
        try:
            for p in root.rglob("*.lnk"):
                if token in p.stem.lower():
                    add(str(p))
                    if len(hits) >= max_hits:
                        break
        except Exception:
            continue

    # 1b) Start Menu app registry (Store/packaged apps)
    ps_pat = ("*" + token + "*").replace("'", "''")
    ps = (
        "Get-StartApps | "
        f"Where-Object {{ $_.Name -like '{ps_pat}' }} | "
        "Select-Object -First 15 Name, AppID | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=6.0,
            shell=False,
        )
        if completed.returncode == 0:
            out = (completed.stdout or "").strip()
            if out:
                data = json.loads(out)
                items = data if isinstance(data, list) else [data]
                for it in items:
                    appid = (it or {}).get("AppID")
                    name2 = (it or {}).get("Name") or ""
                    if appid and isinstance(appid, str):
                        add(f"shell:AppsFolder\\{appid}  ({name2})")
                        if len(hits) >= max_hits:
                            break
    except Exception:
        pass

    # 2) Common executable locations (use where.exe with timeouts; much faster than rglob)
    exe_name = token if token.endswith(".exe") else token + ".exe"
    common_roots: list[str] = []
    localapp = Path(os.environ.get("LOCALAPPDATA", "") or "")
    if localapp:
        p = localapp / "Programs"
        if p.exists():
            common_roots.append(str(p))
    # Whole Program Files trees can be huge; rely on where.exe with short timeouts.
    for p in [Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")]:
        if p.exists():
            common_roots.append(str(p))

    for root in common_roots:
        if len(hits) >= max_hits:
            break
        # Longer for LocalAppData, shorter for Program Files.
        timeout = 8.0 if "AppData" in root else 4.0
        try:
            paths = _run_where(root, exe_name, timeout_s=timeout)
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue
        for p in paths:
            add(p)
            if len(hits) >= max_hits:
                break

    return hits

