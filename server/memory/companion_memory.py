# companion_memory.py
from __future__ import annotations

import re
from typing import Any, Dict, List

from server.infra.repo import (
    list_user_prefs,
    list_learning_progress,
    list_user_reminders,
    upsert_user_preference,
)

COMPANION_PREF_PREFIX = "companion_pref:"
COMPANION_FACT_PREFIX = "companion_fact:"
COMPANION_LOCK_PREFIX = "companion_persona_lock:"
MAX_PREF_CONTEXT = 8
MAX_FACT_CONTEXT = 6


def _clean(text: str) -> str:
    return (text or "").strip()


def _pref_key(name: str) -> str:
    return f"{COMPANION_PREF_PREFIX}{name.strip()}"


def _fact_key(session_id: str, name: str) -> str:
    sid = (session_id or "default").strip() or "default"
    return f"{COMPANION_FACT_PREFIX}{sid}:{name.strip()}"


def extract_mem_signals(user_text: str, session_id: str) -> List[Dict[str, Any]]:
    text = _clean(user_text)
    if not text:
        return []

    signals: List[Dict[str, Any]] = []

    # 鍋忓ソ锛氱О鍛?
    m = re.search(r"鍙垜\s*([^\s锛屻€傦紒锛?!?]{1,20})", text, flags=re.IGNORECASE)
    if m:
        signals.append(
            {
                "key": _pref_key("nickname"),
                "value": m.group(1).strip(),
                "source": "companion_rule:nickname",
                "confidence": 0.95,
            }
        )

    # 鍋忓ソ锛氳姘?
    m = re.search(r"(鐢▅淇濇寔)\s*([^\s锛屻€傦紒锛?!?]{1,20})\s*(璇皵|椋庢牸)", text, flags=re.IGNORECASE)
    if m:
        signals.append(
            {
                "key": _pref_key("tone"),
                "value": m.group(2).strip(),
                "source": "companion_rule:tone",
                "confidence": 0.9,
            }
        )

    # 鍋忓ソ锛氬枩娆?/ 涓嶅枩娆?
    m = re.search(r"鎴戝枩娆?.{1,40})", text, flags=re.IGNORECASE)
    if m:
        signals.append(
            {
                "key": _pref_key("likes"),
                "value": m.group(1).strip(" 锛屻€??锛侊紵"),
                "source": "companion_rule:likes",
                "confidence": 0.82,
            }
        )

    m = re.search(r"鎴戜笉鍠滄(.{1,40})", text, flags=re.IGNORECASE)
    if m:
        signals.append(
            {
                "key": _pref_key("dislikes"),
                "value": m.group(1).strip(" 锛屻€??锛侊紵"),
                "source": "companion_rule:dislikes",
                "confidence": 0.88,
            }
        )

    # 浼氳瘽浜嬪疄锛氭渶杩戝湪鍋氫粈涔?
    m = re.search(r"(鎴戞渶杩戝湪|鎴戠幇鍦ㄥ湪)(.{1,60})", text, flags=re.IGNORECASE)
    if m:
        signals.append(
            {
                "key": _fact_key(session_id, "recent_focus"),
                "value": m.group(2).strip(" 锛屻€??锛侊紵"),
                "source": "companion_rule:recent_focus",
                "confidence": 0.78,
            }
        )

    return signals


def save_mem_signals(user_id: str, signals: List[Dict[str, Any]]) -> None:
    uid = _clean(user_id) or "user1"
    if not signals:
        return

    for s in signals:
        key = _clean(str(s.get("key", "")))
        value = _clean(str(s.get("value", "")))
        source = _clean(str(s.get("source", "companion_rule")))
        confidence = float(s.get("confidence", 0.7))
        if not key or not value:
            continue
        upsert_user_preference(
            user_id=uid,
            key=key,
            value=value,
            source=source,
            confidence=confidence,
        )


def build_memory_ctx(user_id: str, session_id: str, *, include_progress: bool = True) -> str:
    uid = _clean(user_id) or "user1"
    sid = _clean(session_id) or "default"

    companion_prefs = list_user_prefs(
        user_id=uid,
        key_prefix=COMPANION_PREF_PREFIX,
        limit=MAX_PREF_CONTEXT,
    )
    session_facts = list_user_prefs(
        user_id=uid,
        key_prefix=f"{COMPANION_FACT_PREFIX}{sid}:",
        limit=MAX_FACT_CONTEXT,
    )

    lines: List[str] = []

    if companion_prefs:
        lines.append("【用户长期偏好】")
        for p in companion_prefs[:MAX_PREF_CONTEXT]:
            key = str(p.get("key", "")).replace(COMPANION_PREF_PREFIX, "", 1)
            val = str(p.get("value", "")).strip()
            if val:
                lines.append(f"- {key}: {val}")

    if session_facts:
        lines.append("【会话近期事实】")
        for p in session_facts[:MAX_FACT_CONTEXT]:
            key = str(p.get("key", "")).split(":")[-1]
            val = str(p.get("value", "")).strip()
            if val:
                lines.append(f"- {key}: {val}")

    if include_progress:
        reminders = list_user_reminders(user_id=uid, lookahead_hours=48, limit=5)
        if reminders:
            lines.append("【近期学习提醒】")
            for r in reminders:
                topic = str(r.get("topic", "")).strip()
                nxt = str(r.get("next_review_at", "")).strip()
                if topic:
                    lines.append(f"- {topic}（{nxt or '近期'}）")

        progress = list_learning_progress(user_id=uid, course_id=None, limit=5)
        if progress:
            lines.append("【学习状态摘要】")
            for p in progress[:5]:
                topic = str(p.get("topic", "")).strip()
                status = str(p.get("status", "")).strip()
                mastery = p.get("mastery")
                if topic:
                    mastery_text = "" if mastery is None else f", mastery={mastery}"
                    lines.append(f"- {topic}: {status}{mastery_text}")

    if not lines:
        return ""

    return (
        "以下为长期记忆，请作为稳定偏好与背景，仅在相关时使用；若与用户本轮明确新指令冲突，以本轮为准。\n\n"
        + "\n".join(lines)
    )


def _tokenize(text: str) -> List[str]:
    t = _clean(text).lower()
    if not t:
        return []
    return [x for x in re.split(r"[\s,，。！？；：,.!?;:]+", t) if x]


def _overlap_score(query_text: str, item_text: str) -> float:
    tq = set(_tokenize(query_text))
    ti = set(_tokenize(item_text))
    if not tq or not ti:
        return 0.0
    return len(tq & ti) / max(1, len(tq))


def search_recall(
    user_id: str,
    session_id: str,
    query: str,
    *,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    uid = _clean(user_id) or "user1"
    sid = _clean(session_id) or "default"
    q = _clean(query)
    if not q:
        return []

    pref_items = list_user_prefs(
        user_id=uid,
        key_prefix=COMPANION_PREF_PREFIX,
        limit=40,
    )
    fact_items = list_user_prefs(
        user_id=uid,
        key_prefix=f"{COMPANION_FACT_PREFIX}{sid}:",
        limit=40,
    )
    reminders = list_user_reminders(user_id=uid, lookahead_hours=48, limit=10)
    progress = list_learning_progress(user_id=uid, course_id=None, limit=10)

    candidates: List[Dict[str, Any]] = []

    for p in pref_items:
        text = f"{p.get('key', '')} {p.get('value', '')}".strip()
        conf = float(p.get("confidence") or 0.6)
        score = 0.65 * _overlap_score(q, text) + 0.35 * conf
        candidates.append({"kind": "preference", "text": text, "score": score})

    for p in fact_items:
        text = f"{p.get('key', '')} {p.get('value', '')}".strip()
        conf = float(p.get("confidence") or 0.5)
        score = 0.7 * _overlap_score(q, text) + 0.3 * conf
        candidates.append({"kind": "fact", "text": text, "score": score})

    for r in reminders:
        text = f"{r.get('topic', '')} {r.get('status', '')} {r.get('evidence', '')}".strip()
        score = 0.8 * _overlap_score(q, text) + 0.2
        candidates.append({"kind": "reminder", "text": text, "score": score})

    for p in progress:
        text = f"{p.get('topic', '')} {p.get('status', '')} {p.get('evidence', '')}".strip()
        score = 0.8 * _overlap_score(q, text) + 0.2
        candidates.append({"kind": "progress", "text": text, "score": score})

    candidates.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    filtered = [item for item in candidates if float(item.get("score") or 0.0) > 0.12]
    return filtered[: max(1, int(top_k))]


def format_recall(items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""

    lines = ["【长期记忆检索命中】"]
    for idx, item in enumerate(items, 1):
        kind = str(item.get("kind", "memory")).strip() or "memory"
        text = str(item.get("text", "")).strip()[:120]
        if text:
            lines.append(f"- #{idx} ({kind}) {text}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)
