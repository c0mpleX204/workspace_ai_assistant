import logging
import os
from typing import List

from server.dialogue.personas import PERSONAS
from server.infra.repo import get_user_pref, upsert_user_preference


LOCK_ON = (
    os.getenv("COMPANION_PERSONA_LOCK_ENABLED", "true").strip().lower() == "true"
)
LOCK_PREFIX = "companion_persona_lock:"
LOCK_SOURCE = "companion_persona_lock"

SESSION_LOCKS: dict[str, str] = {}


def persona_lock_key(session_id: str) -> str:
    sid = (session_id or "default").strip() or "default"
    return f"{LOCK_PREFIX}{sid[:96]}"


def load_persona_lock(user_id: str, session_id: str) -> str:
    lock_key = persona_lock_key(session_id)
    try:
        item = get_user_pref(user_id=user_id, key=lock_key)
        if item is None:
            return ""
        value = str(item.get("value", "")).strip()
        if value:
            return value
    except Exception as exc:
        logging.warning("load companion persona lock failed user=%s session=%s err=%s", user_id, session_id, exc)
    return ""


def save_persona_lock(user_id: str, session_id: str, persona_id: str) -> None:
    if not persona_id.strip():
        return
    lock_key = persona_lock_key(session_id)
    try:
        upsert_user_preference(
            user_id=user_id,
            key=lock_key,
            value=persona_id,
            source=LOCK_SOURCE,
            confidence=1.0,
        )
    except Exception as exc:
        logging.warning("save companion persona lock failed user=%s session=%s err=%s", user_id, session_id, exc)


def resolve_persona_id(user_id: str, session_id: str, requested_persona_id: str) -> str:
    cleaned = (requested_persona_id or "").strip()
    if not LOCK_ON:
        return cleaned if cleaned not in {"", "default_companion"} else "student_friend"

    locked = SESSION_LOCKS.get(session_id)
    if not locked:
        locked = load_persona_lock(user_id, session_id)
        if locked:
            SESSION_LOCKS[session_id] = locked

    if cleaned in {"", "default_companion"} and locked:
        return locked

    resolved = cleaned if cleaned not in {"", "default_companion"} else (locked or "student_friend")
    SESSION_LOCKS[session_id] = resolved
    if resolved != locked:
        save_persona_lock(user_id, session_id, resolved)
    return resolved


def resolve_persona_prompt(persona_id: str) -> str:
    card = PERSONAS.get(persona_id) if isinstance(PERSONAS, dict) else None
    if card and isinstance(card, dict):
        prompt = str(card.get("system_prompt", "")).strip()
        if prompt:
            return prompt
    return (
        "你是实时桌面陪伴助手。语气温和、简洁、稳定。"
        "先回应用户情绪，再给简短建议。"
        "不编造事实，不突然切换人格。"
    )


def build_style_anchor(messages: List[object], *, keep_n: int = 2) -> str:
    samples: List[str] = []
    for msg in reversed(messages or []):
        if isinstance(msg, dict):
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip().replace("\n", " ")
        else:
            role = str(getattr(msg, "role", "")).strip().lower()
            content = str(getattr(msg, "content", "")).strip().replace("\n", " ")
        if role != "assistant" or not content:
            continue
        samples.append(content[:100])
        if len(samples) >= keep_n:
            break

    if not samples:
        return ""
    samples.reverse()
    joined = "\n".join(f"- {item}" for item in samples)
    return (
        "多轮一致性约束：保持与最近回复一致的语气、称呼和情绪强度。"
        "参考最近回复风格：\n"
        f"{joined}"
    )


def latest_user_text(messages: List[object]) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, dict):
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "")).strip()
        else:
            role = str(getattr(msg, "role", "")).strip().lower()
            content = str(getattr(msg, "content", "")).strip()
        if role == "user" and content:
            return content
    return ""
