from __future__ import annotations

import json
from typing import Optional

from langchain.tools import tool

from shell_service import run_shell


@tool("shell_run")
def shell_run_tool(command: str, cwd: Optional[str] = None) -> str:
    """
    Run a safe shell command inside the sandbox root.
    Only for read-only diagnostics (e.g. 'dir', 'git status', 'pip list').
    Dangerous commands (delete/format/shutdown) are rejected.
    """
    result = run_shell(command, cwd=cwd or None)
    return json.dumps(
        {
            "command": result.command,
            "cwd": result.cwd,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        ensure_ascii=False,
    )

