from __future__ import annotations

import os
import re
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
import json

from config import settings
from fs_service import _safe_join


@dataclass(frozen=True)
class OpenResult:
    kind: str  # "url" | "path" | "app"
    target: str
    ok: bool
    detail: str = ""


_DANGEROUS_CHARS_RE = re.compile(r"[&|;><`]")


def _reject_if_unsafe(s: str) -> None:
    if _DANGEROUS_CHARS_RE.search(s or ""):
        raise ValueError("Target rejected by safety filter")


def _looks_like_url(s: str) -> bool:
    t = (s or "").strip().lower()
    return t.startswith("http://") or t.startswith("https://")


def _open_url(url: str) -> OpenResult:
    ok = webbrowser.open(url, new=2, autoraise=True)
    return OpenResult(kind="url", target=url, ok=bool(ok))


def _open_path(rel_or_abs: str) -> OpenResult:
    # Only allow opening inside sandbox root.
    p = _safe_join(rel_or_abs)
    if not p.exists():
        return OpenResult(kind="path", target=str(p.relative_to(settings.fs_root)), ok=False, detail="Not found")
    try:
        os.startfile(str(p))  # Windows only
    except Exception as e:
        return OpenResult(kind="path", target=str(p.relative_to(settings.fs_root)), ok=False, detail=str(e))
    return OpenResult(kind="path", target=str(p.relative_to(settings.fs_root)), ok=True)


def _open_app(name: str) -> OpenResult:
    """
    Open an app by name using PowerShell Start-Process.
    We also map common natural-language names to real executables so that
    "calculator" works reliably (calc.exe).
    """
    raw = (name or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Empty app name")

    key = raw.lower().strip()

    # Common aliases -> executable / URI
    aliases: dict[str, str] = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "command line": "cmd.exe",
        "terminal cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "settings": "ms-settings:",
        "word": "winword.exe",
        "microsoft word": "winword.exe",
        "excel": "excel.exe",
        "microsoft excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
        "microsoft powerpoint": "powerpnt.exe",
        "telegram": "telegram.exe",
        "telegram desktop": "telegram.exe",
    }
    target = aliases.get(key, raw)

    resolved = _resolve_app_target(target)
    if resolved:
        target = resolved

    # Start-Process returns non-zero on failure, so we can report ok accurately.
    try:
        # Quote target safely for PowerShell single-quoted string.
        ps_target = target.replace("'", "''")
        if target.lower().startswith("shell:appsfolder\\"):
            # Packaged/Store app launch
            ps_cmd = f"Start-Process -FilePath 'explorer.exe' -ArgumentList '{ps_target}'"
        else:
            ps_cmd = f"Start-Process -FilePath '{ps_target}'"

        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=8.0,
            shell=False,
        )
        if completed.returncode == 0:
            return OpenResult(kind="app", target=target, ok=True)
        err = (completed.stderr or completed.stdout or "").strip()
        return OpenResult(kind="app", target=target, ok=False, detail=err or "Start-Process failed")
    except Exception as e:
        return OpenResult(kind="app", target=target, ok=False, detail=str(e))


def _resolve_app_target(name_or_exe: str) -> str | None:
    """
    Try to resolve app names more intelligently:
    - if it's on PATH, return resolved name
    - check App Paths registry (winword.exe etc.)
    - search Start Menu shortcuts (.lnk) and return shortcut path
    """
    t = (name_or_exe or "").strip().strip('"').strip("'")
    if not t:
        return None

    # URI schemes like ms-settings:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:$", t):
        return t

    # If user gave "word", try "word.exe"
    candidates: list[str] = [t]
    if not t.lower().endswith(".exe") and " " not in t and ":" not in t and "\\" not in t and "/" not in t:
        candidates.append(t + ".exe")

    # PATH resolution (fast)
    for c in candidates:
        p = shutil.which(c)
        if p:
            return c  # Start-Process works fine with command name

    # App Paths registry lookup (fast, good for Office apps)
    reg_hit = _lookup_app_paths_registry(candidates)
    if reg_hit:
        return reg_hit

    # Start Menu shortcut lookup (covers apps like Telegram)
    shortcut = _find_start_menu_shortcut(candidates)
    if shortcut:
        return shortcut

    # Common install locations (covers Telegram installed under AppData\Local\Programs)
    exe_hit = _find_common_exe(candidates)
    if exe_hit:
        return exe_hit

    # Start Menu app registry (Store apps, packaged apps)
    app_link = _find_startapps_link(candidates)
    if app_link:
        return app_link

    return None


def _lookup_app_paths_registry(candidates: list[str]) -> str | None:
    try:
        import winreg  # type: ignore
    except Exception:
        return None

    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for c in candidates:
        exe = c if c.lower().endswith(".exe") else c + ".exe"
        for hive, base in roots:
            try:
                with winreg.OpenKey(hive, base + "\\" + exe) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and isinstance(val, str) and Path(val).exists():
                        return val
            except Exception:
                continue
    return None


def _find_start_menu_shortcut(candidates: list[str]) -> str | None:
    start_dirs = []
    try:
        appdata = Path(os.environ.get("APPDATA", ""))
        programdata = Path(os.environ.get("PROGRAMDATA", ""))
        if appdata:
            start_dirs.append(appdata / r"Microsoft\Windows\Start Menu\Programs")
        if programdata:
            start_dirs.append(programdata / r"Microsoft\Windows\Start Menu\Programs")
    except Exception:
        return None

    want = set()
    for c in candidates:
        base = Path(c).stem.lower()
        want.add(base)

    for root in start_dirs:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*.lnk"):
                stem = p.stem.lower()
                if stem in want or any(w in stem for w in want):
                    return str(p)
        except Exception:
            continue

    return None


def _find_common_exe(candidates: list[str]) -> str | None:
    exe_names: list[str] = []
    for c in candidates:
        stem = Path(c).stem
        exe = stem if stem.lower().endswith(".exe") else stem + ".exe"
        exe_names.append(exe)

    roots: list[Path] = []
    localapp = Path(os.environ.get("LOCALAPPDATA", "") or "")
    if localapp:
        roots.append(localapp / "Programs")
        roots.append(localapp)
    roots.append(Path(r"C:\Program Files"))
    roots.append(Path(r"C:\Program Files (x86)"))

    for root in roots:
        if not root.exists():
            continue
        for exe in exe_names:
            try:
                for p in root.rglob(exe):
                    if p.exists():
                        return str(p)
            except Exception:
                continue
    return None


def _find_startapps_link(candidates: list[str]) -> str | None:
    """
    Uses PowerShell Get-StartApps to find Start Menu entries (including Store apps).
    Returns an AppsFolder link that can be opened via explorer:
      shell:AppsFolder\\<AppID>
    """
    tokens: list[str] = []
    for c in candidates:
        stem = Path(c).stem.lower().strip()
        if stem:
            tokens.append(stem)
    tokens = list(dict.fromkeys(tokens))  # dedupe preserving order
    if not tokens:
        return None

    # Prefer the first token for matching.
    t = tokens[0]
    # Escape for a single-quoted PowerShell string.
    ps_pat = ("*" + t + "*").replace("'", "''")

    ps = (
        "Get-StartApps | "
        f"Where-Object {{ $_.Name -like '{ps_pat}' }} | "
        "Select-Object -First 5 Name, AppID | "
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
    except Exception:
        return None

    if completed.returncode != 0:
        return None
    out = (completed.stdout or "").strip()
    if not out:
        return None

    try:
        data = json.loads(out)
    except Exception:
        return None

    # ConvertTo-Json returns either object or list.
    items = data if isinstance(data, list) else [data]
    for it in items:
        appid = (it or {}).get("AppID")
        if appid and isinstance(appid, str):
            return r"shell:AppsFolder\\" + appid
    return None


def open_target(target: str) -> OpenResult:
    """
    Open a URL, a sandboxed file/folder, or a Windows app by name.
    Guardrails:
    - rejects common shell metacharacters
    - file/folder opens are sandboxed to JARVIS_FS_ROOT
    """
    t = (target or "").strip()
    if not t:
        raise ValueError("Empty target")

    _reject_if_unsafe(t)

    # URL
    if _looks_like_url(t):
        return _open_url(t)

    # If it looks like a path (contains slashes or a dot-extension), treat as sandbox path.
    looks_like_path = ("/" in t) or ("\\" in t) or bool(re.search(r"\.[a-z0-9]{1,5}$", t.lower()))
    if looks_like_path:
        return _open_path(t)

    # Otherwise treat as app name.
    return _open_app(t)

