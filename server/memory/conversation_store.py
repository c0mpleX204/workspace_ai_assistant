from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_HISTORY_MAX = int(os.getenv("CHAT_HISTORY_MAX_MESSAGES", "24"))
CONVERSATION_DIR = Path(
    os.getenv("CONVERSATION_SESSION_DIR", "data/conversations")
)

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_id(value: object, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw)
    return cleaned[:120] or fallback


def infer_scope(session_id: str) -> str:
    sid = str(session_id or "").strip()
    if sid.startswith("course_") or sid.startswith("project_"):
        return "projects"
    return "ordinary"


def _session_path(user_id: str, session_id: str, scope: str | None = None) -> Path:
    uid = _clean_id(user_id, "default_user")
    sid = _clean_id(session_id, "default")
    scp = _clean_id(scope or infer_scope(sid), "ordinary")
    path = CONVERSATION_DIR / uid / scp
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{sid}.json"


def normalize_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    role = str(message.get("role") or "").strip().lower()
    if role not in {"user", "assistant", "system"}:
        return None
    content = str(message.get("content") or "").strip()
    if not content:
        return None

    normalized: Dict[str, Any] = {
        "role": role,
        "content": content,
    }
    created_at = str(message.get("created_at") or "").strip()
    normalized["created_at"] = created_at or _now_iso()

    metadata = message.get("metadata")
    if isinstance(metadata, dict) and metadata:
        normalized["metadata"] = metadata
    refs = message.get("refs") or message.get("reference")
    if isinstance(refs, list) and refs:
        normalized["refs"] = refs
    images = message.get("images")
    if isinstance(images, list) and images:
        normalized["images"] = images[:4]
    return normalized


def normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        msg = normalize_message(item)
        if msg is None:
            continue
        normalized.append(msg)
    return normalized


def model_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []
    for item in normalize_messages(messages):
        result.append({
            "role": str(item.get("role", "")),
            "content": str(item.get("content", "")),
        })
    return result


def _dedup_adjacent(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for msg in messages:
        if (
            result
            and result[-1].get("role") == msg.get("role")
            and result[-1].get("content") == msg.get("content")
        ):
            continue
        result.append(msg)
    return result


def _build_title(messages: List[Dict[str, Any]]) -> str:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content") or "").strip().replace("\n", " ")
        if content:
            return content[:40]
    return "New chat"


def load_conversation(
    user_id: str,
    session_id: str,
    *,
    scope: str | None = None,
    limit: int = DEFAULT_HISTORY_MAX,
) -> Dict[str, Any]:
    path = _session_path(user_id, session_id, scope)
    if not path.exists():
        return {
            "user_id": _clean_id(user_id, "default_user"),
            "session_id": _clean_id(session_id, "default"),
            "scope": _clean_id(scope or infer_scope(session_id), "ordinary"),
            "title": "New chat",
            "messages": [],
            "compressed_summary": "",
        }

    with _LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    if not isinstance(payload, dict):
        payload = {}

    messages = normalize_messages(payload.get("messages", []))
    max_messages = max(2, int(limit))
    messages = _dedup_adjacent(messages)[-max_messages:]
    return {
        "user_id": str(payload.get("user_id") or _clean_id(user_id, "default_user")),
        "session_id": str(payload.get("session_id") or _clean_id(session_id, "default")),
        "scope": str(payload.get("scope") or _clean_id(scope or infer_scope(session_id), "ordinary")),
        "title": str(payload.get("title") or _build_title(messages)),
        "messages": messages,
        "compressed_summary": str(payload.get("compressed_summary") or "").strip(),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def load_messages(
    user_id: str,
    session_id: str,
    *,
    scope: str | None = None,
    limit: int = DEFAULT_HISTORY_MAX,
) -> List[Dict[str, str]]:
    payload = load_conversation(user_id, session_id, scope=scope, limit=limit)
    return model_messages(payload.get("messages", []))


def load_summary(user_id: str, session_id: str, *, scope: str | None = None) -> str:
    payload = load_conversation(user_id, session_id, scope=scope, limit=2)
    return str(payload.get("compressed_summary") or "").strip()


def save_summary(
    user_id: str,
    session_id: str,
    summary: str,
    *,
    scope: str | None = None,
) -> None:
    existing = load_conversation(user_id, session_id, scope=scope, limit=DEFAULT_HISTORY_MAX)
    existing["compressed_summary"] = str(summary or "").strip()
    save_conversation(
        user_id,
        session_id,
        existing.get("messages", []),
        scope=scope,
        compressed_summary=existing["compressed_summary"],
    )


def merge_dialog(
    user_id: str,
    session_id: str,
    incoming_messages: List[Dict[str, Any]],
    *,
    scope: str | None = None,
    limit: int = DEFAULT_HISTORY_MAX,
) -> List[Dict[str, str]]:
    max_messages = max(2, int(limit))
    incoming = normalize_messages(incoming_messages)
    stored = load_conversation(user_id, session_id, scope=scope, limit=max_messages).get("messages", [])

    if len(incoming) >= 2:
        merged = incoming
    elif incoming:
        merged = list(stored) + incoming
    else:
        merged = list(stored)

    return model_messages(_dedup_adjacent(merged)[-max_messages:])


def save_conversation(
    user_id: str,
    session_id: str,
    messages: List[Dict[str, Any]],
    *,
    scope: str | None = None,
    limit: int = DEFAULT_HISTORY_MAX,
    compressed_summary: str | None = None,
) -> List[Dict[str, Any]]:
    path = _session_path(user_id, session_id, scope)
    now = _now_iso()
    current: Dict[str, Any] = {}
    if path.exists():
        with _LOCK:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    current = raw
            except Exception:
                current = {}

    max_messages = max(2, int(limit))
    normalized = _dedup_adjacent(normalize_messages(messages))[-max_messages:]
    summary = (
        str(compressed_summary).strip()
        if compressed_summary is not None
        else str(current.get("compressed_summary") or "").strip()
    )

    payload = {
        "user_id": _clean_id(user_id, "default_user"),
        "session_id": _clean_id(session_id, "default"),
        "scope": _clean_id(scope or infer_scope(session_id), "ordinary"),
        "title": str(current.get("title") or _build_title(normalized)),
        "messages": normalized,
        "compressed_summary": summary,
        "created_at": current.get("created_at") or now,
        "updated_at": now,
    }

    with _LOCK:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return normalized
