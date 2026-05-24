from __future__ import annotations

import ctypes
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List

from server.config.config import settings
from server.services.ai.model import smart_model_dispatch


PROJECT_MEMORY_FILENAME = ".project-memory.md"
PROJECT_MEMORY_MAX_CHARS = int(os.getenv("PROJECT_MEMORY_MAX_CHARS", "5000"))
PROJECT_MEMORY_UPDATE_MAX_TOKENS = int(os.getenv("PROJECT_MEMORY_UPDATE_MAX_TOKENS", "900"))

_LOCK = threading.RLock()


PROJECT_MEMORY_TEMPLATE = """# Project Memory

<!-- Hidden file maintained by workspace_ai_assistant. -->

## Background
- None yet.

## Progress
- None yet.

## Important User Notes
- None yet.

## Open Questions
- None yet.
"""


def _workspace_root(workspace_path: str | os.PathLike[str] | None) -> Path | None:
    raw = str(workspace_path or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return None


def _set_hidden_on_windows(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return
        ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        logging.debug("failed to mark project memory hidden: %s", path, exc_info=True)


def project_memory_path(workspace_path: str | os.PathLike[str] | None) -> Path | None:
    root = _workspace_root(workspace_path)
    if root is None:
        return None
    return root / PROJECT_MEMORY_FILENAME


def ensure_project_memory_file(workspace_path: str | os.PathLike[str] | None) -> Path | None:
    path = project_memory_path(workspace_path)
    if path is None:
        return None
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(PROJECT_MEMORY_TEMPLATE, encoding="utf-8")
        _set_hidden_on_windows(path)
    return path


def _has_saved_content(text: str) -> bool:
    cleaned = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        if stripped in {"-->", "- None yet.", "None yet."}:
            continue
        cleaned.append(stripped)
    return bool(cleaned)


def load_project_memory(workspace_path: str | os.PathLike[str] | None) -> str:
    path = ensure_project_memory_file(workspace_path)
    if path is None or not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not _has_saved_content(text):
        return ""
    return text[:PROJECT_MEMORY_MAX_CHARS]


def _recent_exchange_text(
    *,
    query: str,
    reply: str,
    plan: List[Dict[str, Any]] | None = None,
    operations: List[Dict[str, Any]] | None = None,
) -> str:
    lines = [
        "User:",
        str(query or "").strip(),
        "",
        "Assistant:",
        str(reply or "").strip(),
    ]
    plan_items = [str(x.get("title") or "").strip() for x in (plan or []) if isinstance(x, dict)]
    if plan_items:
        lines.extend(["", "Plan:", *[f"- {x}" for x in plan_items if x]])
    op_lines: List[str] = []
    for op in operations or []:
        if not isinstance(op, dict):
            continue
        title = str(op.get("title") or op.get("command") or "").strip()
        status = str(op.get("status") or "").strip()
        if title:
            op_lines.append(f"- {title}{f' ({status})' if status else ''}")
    if op_lines:
        lines.extend(["", "Operations:", *op_lines[:8]])
    return "\n".join(lines).strip()


def update_project_memory(
    workspace_path: str | os.PathLike[str] | None,
    *,
    query: str,
    reply: str,
    plan: List[Dict[str, Any]] | None = None,
    operations: List[Dict[str, Any]] | None = None,
) -> None:
    if not str(query or "").strip() or not str(reply or "").strip():
        return
    path = ensure_project_memory_file(workspace_path)
    if path is None:
        return

    with _LOCK:
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = PROJECT_MEMORY_TEMPLATE

        exchange = _recent_exchange_text(query=query, reply=reply, plan=plan, operations=operations)
        try:
            result = smart_model_dispatch(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You update a hidden per-project memory file for an IDE assistant. "
                                "Keep only durable project background, current progress, user-emphasized constraints, "
                                "decisions, and open questions. Do not store generic chit-chat, timestamps, token stats, "
                                "or temporary status messages. Preserve useful existing information and merge the new "
                                "exchange. Output the full Markdown file using exactly these headings: "
                                "Project Memory, Background, Progress, Important User Notes, Open Questions."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Existing project memory file:\n"
                                f"{existing}\n\n"
                                "Latest exchange to consider:\n"
                                f"{exchange}\n\n"
                                "Return the updated Markdown file only."
                            ),
                        },
                    ],
                    "model": settings.remote_fast_model,
                    "generation": {
                        "max_tokens": max(300, PROJECT_MEMORY_UPDATE_MAX_TOKENS),
                        "temperature": 0.2,
                        "top_p": 0.9,
                    },
                }
            )
            updated = str(result.get("reply") or "").strip()
        except Exception as exc:
            logging.warning("project memory update failed path=%s err=%s", path, exc)
            return

        if not updated:
            return
        if "# Project Memory" not in updated:
            updated = PROJECT_MEMORY_TEMPLATE.rstrip() + "\n\n## Notes\n" + updated
        updated = updated[:PROJECT_MEMORY_MAX_CHARS].rstrip() + "\n"
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp_path.write_text(updated, encoding="utf-8")
            tmp_path.replace(path)
            _set_hidden_on_windows(path)
        except OSError as exc:
            logging.warning("project memory write failed path=%s err=%s", path, exc)


def schedule_project_memory_update(
    workspace_path: str | os.PathLike[str] | None,
    *,
    query: str,
    reply: str,
    plan: List[Dict[str, Any]] | None = None,
    operations: List[Dict[str, Any]] | None = None,
) -> None:
    if not workspace_path or not str(query or "").strip() or not str(reply or "").strip():
        return

    def worker() -> None:
        update_project_memory(
            workspace_path,
            query=query,
            reply=reply,
            plan=plan,
            operations=operations,
        )

    thread = threading.Thread(target=worker, name="project-memory-update", daemon=True)
    thread.start()
