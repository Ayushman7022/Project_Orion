from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config import settings


@dataclass(frozen=True)
class ShellResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str


_FORBIDDEN_TOKENS = [
    "rm ",
    " rm",
    "del ",
    " del",
    "rmdir",
    "mkfs",
    "format ",
    " shutdown",
    "reboot",
    ":(){:|:&};:",  # fork bomb
]


def _is_dangerous(cmd: str) -> bool:
    lower = cmd.lower()
    return any(tok in lower for tok in _FORBIDDEN_TOKENS)


def run_shell(command: str, cwd: str | None = None, timeout_s: float = 15.0) -> ShellResult:
    """
    Run a read-only shell command with basic guardrails.
    Intended for diagnostics: dir/ls, git status, pip list, etc.
    """
    cmd = (command or "").strip()
    if not cmd:
        raise ValueError("Empty command")
    if _is_dangerous(cmd):
        raise ValueError("Command rejected by safety filter")

    if cwd:
        base = Path(cwd)
    else:
        base = settings.fs_root
    base = base.resolve()

    try:
        base.relative_to(settings.fs_root)
    except Exception:
        # Force cwd inside sandbox
        base = settings.fs_root

    # On Windows, use shell=True so builtins like dir work.
    completed = subprocess.run(
        cmd,
        shell=True,
        cwd=str(base),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
    )

    return ShellResult(
        command=cmd,
        cwd=str(base),
        exit_code=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )

