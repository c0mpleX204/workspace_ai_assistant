from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
from typing import Dict, List

DEFAULT_HISTORY_MAX = int(
    os.getenv("COMPANION_HISTORY_MAX_MESSAGES", "24")
)
SESSION_DIR = Path(
    os.getenv("COMPANION_SESSION_DIR", "data/companion_sessions")
)

_LOCK = threading.RLock()


def _normalize_role(value: object) -> str:
    role = str(value or "").strip().lower()
    if role in {"user", "assistant"}:
        return role
    return ""


def _normalize_content(value: object) -> str:
    return str(value or "").strip()


def _sanitize_session_id(session_id: str) -> str:
    raw = str(session_id or "").strip()
    if not raw:
        return "default"
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw)
    return cleaned[:120] or "default"


def _session_file_path(session_id: str) -> Path:
    session_dir = SESSION_DIR
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / f"{_sanitize_session_id(session_id)}.json"


def normalize_msgs(messages: List[Dict[str, object]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in messages or []:
        role = _normalize_role(item.get("role"))
        content = _normalize_content(item.get("content"))
        if not role or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _dedup_adjacent(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for msg in messages:
        if result and result[-1]["role"] == msg["role"] and result[-1]["content"] == msg["content"]:
            continue
        result.append(msg)
    return result


def load_session(
    session_id: str,
    *,
    limit: int = DEFAULT_HISTORY_MAX,
) -> List[Dict[str, str]]:
    path = _session_file_path(session_id)
    if not path.exists():
        return []

    with _LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    if not isinstance(payload, dict):
        return []

    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return []

    normalized = normalize_msgs(messages)
    max_messages = max(2, int(limit))
    return _dedup_adjacent(normalized)[-max_messages:]


def save_session(
    session_id: str,
    messages: List[Dict[str, object]],
    *,
    limit: int = DEFAULT_HISTORY_MAX,
) -> List[Dict[str, str]]:
    max_messages = max(2, int(limit))
    normalized = normalize_msgs(messages)
    normalized = _dedup_adjacent(normalized)[-max_messages:]

    path = _session_file_path(session_id)
    existing_summary = ""
    if path.exists():
        with _LOCK:
            try:
                old_payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(old_payload, dict):
                    existing_summary = str(old_payload.get("compressed_summary", "")).strip()
            except Exception:
                existing_summary = ""
    payload = {
        "session_id": _sanitize_session_id(session_id),
        "messages": normalized,
        "compressed_summary": existing_summary,
    }

    with _LOCK:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return normalized


def load_summary(session_id: str) -> str:
    path = _session_file_path(session_id)
    if not path.exists():
        return ""

    with _LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ""

    if not isinstance(payload, dict):
        return ""
    return str(payload.get("compressed_summary", "")).strip()


def save_summary(session_id: str, summary: str) -> None:
    path = _session_file_path(session_id)
    normalized_summary = str(summary or "").strip()

    with _LOCK:
        payload: Dict[str, object] = {}
        if path.exists():
            try:
                old_payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(old_payload, dict):
                    payload = old_payload
            except Exception:
                payload = {}

        payload["session_id"] = _sanitize_session_id(session_id)
        raw_messages = payload.get("messages", [])
        messages = raw_messages if isinstance(raw_messages, list) else []
        payload["messages"] = normalize_msgs(messages)
        payload["compressed_summary"] = normalized_summary
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def merge_dialog(
    session_id: str,
    incoming_messages: List[Dict[str, object]],
    *,
    limit: int = DEFAULT_HISTORY_MAX,
) -> List[Dict[str, str]]:
    max_messages = max(2, int(limit))
    incoming = normalize_msgs(incoming_messages)
    stored = load_session(session_id, limit=max_messages)

    # If frontend already sends multi-turn history, treat it as authoritative.
    if len(incoming) >= 2:
        merged = incoming
    elif incoming:
        merged = stored + incoming
    else:
        merged = stored

    return _dedup_adjacent(merged)[-max_messages:]
