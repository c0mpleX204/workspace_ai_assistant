from __future__ import annotations

import logging
from pathlib import Path
import re
import subprocess
from typing import Dict, Optional


BLOCKED_COMMAND_RE = re.compile(
    r"(\brm\s+-rf\b|\bremove-item\b.*\b-recurse\b|\bgit\s+reset\s+--hard\b|\bformat\b|\bdel\s+/s\b)",
    re.IGNORECASE,
)


def resolve_command_cwd(workspace_path: Optional[str]) -> Optional[Path]:
    if not workspace_path:
        return None
    try:
        path = Path(str(workspace_path)).expanduser().resolve()
    except Exception:
        return None
    if not path.exists() or not path.is_dir():
        return None
    return path


def run_agent_command(command: str, cwd: Path, timeout_sec: int = 45) -> Dict[str, object]:
    cmd = str(command or "").strip()
    if not cmd:
        return {"ok": False, "error": "empty command"}
    if BLOCKED_COMMAND_RE.search(cmd):
        return {"ok": False, "error": "blocked potentially destructive command", "command": cmd}

    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, min(180, int(timeout_sec))),
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        return {
            "ok": completed.returncode == 0,
            "command": cmd,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout": stdout[-12000:],
            "stderr": stderr[-8000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "command": cmd,
            "cwd": str(cwd),
            "error": f"command timed out after {timeout_sec}s",
            "stdout": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        logging.warning("agent command failed: %s", exc)
        return {"ok": False, "command": cmd, "cwd": str(cwd), "error": str(exc)}


def build_command_context(result: Dict[str, object]) -> str:
    if not result:
        return ""
    lines = [
        "【命令行执行结果】",
        f"cwd: {result.get('cwd', '')}",
        f"command: {result.get('command', '')}",
        f"exit_code: {result.get('returncode', '')}",
    ]
    if result.get("error"):
        lines.append(f"error: {result.get('error')}")
    if result.get("stdout"):
        lines.extend(["", "stdout:", str(result.get("stdout", ""))])
    if result.get("stderr"):
        lines.extend(["", "stderr:", str(result.get("stderr", ""))])
    return "\n".join(lines).strip()
