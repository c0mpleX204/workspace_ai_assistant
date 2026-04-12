import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from config.config import settings
from dialogue.personas import PERSONAS
from infra.repo import get_user_preference_by_key, upsert_user_preference
from api.routers.schemas import (
    CompanionActRequest,
    CompanionActResponse,
    CompanionActionIntent,
    CompanionChatRequest,
    CompanionChatResponse,
    CompanionTaskPollRequest,
    CompanionTaskPollResponse,
)
from memory.companion_memory import (
    build_companion_memory_context,
    extract_companion_memory_signals,
    format_companion_long_term_memory,
    persist_companion_memory_signals,
    search_companion_long_term_memory,
)
from memory.companion_session_store import (
    DEFAULT_COMPANION_HISTORY_MAX_MESSAGES,
    load_companion_compressed_summary,
    merge_companion_dialog_history,
    save_companion_compressed_summary,
    save_companion_session_history,
)
from services.game_control_service import execute_game_control
from services.model_service import smart_model_dispatch

router = APIRouter(tags=["companion"])

ALLOWED_ACTION_TYPES = {
    "live2d_expression",
    "live2d_motion",
    "live2d_look_at",
    "game_control",
}
ALLOWED_EXPRESSIONS = {"neutral", "smile", "sad", "angry", "surprised"}
ALLOWED_MOTION_GROUPS = {"idle", "tap_body", "wave", "greet"}
ALLOWED_GAME_COMMANDS = {"jump", "attack", "move_left", "move_right", "interact"}

COMPANION_LIGHTWEIGHT_ENABLED = os.getenv("COMPANION_LIGHTWEIGHT_ENABLED", "true").lower() == "true"
COMPANION_LIGHTWEIGHT_MAX_MESSAGES = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_MESSAGES", "8"))
COMPANION_LIGHTWEIGHT_MAX_CHARS = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_CHARS", "360"))
COMPANION_LIGHTWEIGHT_MAX_TOKENS = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_TOKENS", "180"))
COMPANION_SYSTEM_KEEP = int(os.getenv("COMPANION_SYSTEM_KEEP", "4"))
COMPANION_HISTORY_MAX_MESSAGES = int(
    os.getenv("COMPANION_HISTORY_MAX_MESSAGES", str(DEFAULT_COMPANION_HISTORY_MAX_MESSAGES))
)
COMPANION_SUMMARY_TRIGGER_MESSAGES = int(
    os.getenv("COMPANION_SUMMARY_TRIGGER_MESSAGES", "14")
)
COMPANION_SUMMARY_KEEP_RECENT = int(
    os.getenv("COMPANION_SUMMARY_KEEP_RECENT", "8")
)
COMPANION_SUMMARY_MAX_CHARS = int(
    os.getenv("COMPANION_SUMMARY_MAX_CHARS", "800")
)
COMPANION_FAST_MODEL = os.getenv("COMPANION_FAST_MODEL", "Pro/Qwen/Qwen2.5-7B-Instruct").strip()
COMPANION_HEAVY_MODEL = os.getenv(
    "COMPANION_HEAVY_MODEL",
    settings.remote_primary_model,
).strip()
COMPANION_HEAVY_MAX_TOKENS = int(os.getenv("COMPANION_HEAVY_MAX_TOKENS", "900"))
COMPANION_HEAVY_ASYNC_ENABLED = os.getenv("COMPANION_HEAVY_ASYNC_ENABLED", "true").strip().lower() == "true"
COMPANION_DELEGATED_TASK_TTL_SECONDS = int(os.getenv("COMPANION_DELEGATED_TASK_TTL_SECONDS", "1800"))
COMPANION_ROUTE_CLASSIFIER_ENABLED = (
    os.getenv("COMPANION_ROUTE_CLASSIFIER_ENABLED", "true").strip().lower() == "true"
)
COMPANION_PERSONA_LOCK_ENABLED = (
    os.getenv("COMPANION_PERSONA_LOCK_ENABLED", "true").strip().lower() == "true"
)
COMPANION_PERSONA_LOCK_PREFIX = "companion_persona_lock:"
COMPANION_PERSONA_LOCK_SOURCE = "companion_persona_lock"

SESSION_PERSONA_LOCK: Dict[str, str] = {}

_DELEGATED_TASKS_LOCK = threading.Lock()
_DELEGATED_TASKS: Dict[str, Dict[str, Any]] = {}
_DELEGATED_TASKS_BY_SESSION: Dict[str, List[str]] = {}

ROUTE_MODE_AUTO = "auto"
ROUTE_MODE_CHAT_ONLY = "chat_only"
ROUTE_MODE_TASK_AUTO = "task_auto"
ROUTE_MODE_TASK_FORCE_HARD = "task_force_hard"


class CompanionIntentType(str, Enum):
    SMALL_TALK = "small_talk"
    COMPANION_ACTION = "companion_action"
    KNOWLEDGE_QUERY = "knowledge_query"
    HEAVY_TASK = "heavy_task"


class CompanionRoute(str, Enum):
    COMPANION = "companion"
    HANDOFF = "handoff"


@dataclass(slots=True)
class CompanionIntentDecision:
    intent: CompanionIntentType
    route: CompanionRoute
    confidence: float
    reason: str
    matched_rule: str = ""


ACTION_PATTERNS = (
    r"笑一笑|笑一下|微笑|生气|难过|惊讶|挥手|点头|眨眼|看向|看左边|看右边|看我|look at|wave|smile",
    r"跳一下|攻击|左移|右移|互动|做个动作|表情|动作|motion|expression|jump|attack",
)

HEAVY_PATTERNS = (
    r"改代码|写脚本|修bug|重构|跑测试|部署|重启服务|查日志|读取文件|检索仓库|执行命令",
    r"open file|read file|edit|refactor|debug|run command|terminal|workspace|repository|deploy",
)

KNOWLEDGE_PATTERNS = (
    r"什么是|为什么|原理|解释一下|区别|怎么理解|总结一下",
    r"what is|why|explain|difference|principle|summarize",
)


def _compact_messages(messages: List[Dict[str, object]]) -> List[Dict[str, object]]:
    max_count = max(2, COMPANION_LIGHTWEIGHT_MAX_MESSAGES)
    max_chars = max(80, COMPANION_LIGHTWEIGHT_MAX_CHARS)
    max_system = max(1, COMPANION_SYSTEM_KEEP)
    system_msgs = [m for m in messages if str(m.get("role", "")).strip() == "system"]
    dialog_msgs = [m for m in messages if str(m.get("role", "")).strip() != "system"]
    kept = dialog_msgs[-max_count:]
    compacted: List[Dict[str, object]] = []
    compacted.extend(system_msgs[:max_system])
    for msg in kept:
        content = str(msg.get("content", "")).strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        compacted.append({"role": msg.get("role", "user"), "content": content})
    return compacted


def _build_persona_lock_key(session_id: str) -> str:
    sid = (session_id or "default").strip() or "default"
    # Keep pref_key short and deterministic to avoid column-length surprises.
    return f"{COMPANION_PERSONA_LOCK_PREFIX}{sid[:96]}"


def _load_persona_lock_from_storage(user_id: str, session_id: str) -> str:
    lock_key = _build_persona_lock_key(session_id)
    try:
        item = get_user_preference_by_key(user_id=user_id, key=lock_key)
        if item is None:
            return ""
        value = str(item.get("value", "")).strip()
        if value:
            return value
    except Exception as exc:
        logging.warning("load companion persona lock failed user=%s session=%s err=%s", user_id, session_id, exc)
    return ""


def _save_persona_lock_to_storage(user_id: str, session_id: str, persona_id: str) -> None:
    if not persona_id.strip():
        return
    lock_key = _build_persona_lock_key(session_id)
    try:
        upsert_user_preference(
            user_id=user_id,
            key=lock_key,
            value=persona_id,
            source=COMPANION_PERSONA_LOCK_SOURCE,
            confidence=1.0,
        )
    except Exception as exc:
        logging.warning("save companion persona lock failed user=%s session=%s err=%s", user_id, session_id, exc)


def _resolve_companion_persona_id(user_id: str, session_id: str, requested_persona_id: str) -> str:
    cleaned = (requested_persona_id or "").strip()
    if not COMPANION_PERSONA_LOCK_ENABLED:
        return cleaned if cleaned not in {"", "default_companion"} else "student_friend"

    locked = SESSION_PERSONA_LOCK.get(session_id)
    if not locked:
        locked = _load_persona_lock_from_storage(user_id, session_id)
        if locked:
            SESSION_PERSONA_LOCK[session_id] = locked

    # Treat default_companion as "not explicitly chosen" and keep previous persona.
    if cleaned in {"", "default_companion"} and locked:
        return locked

    resolved = cleaned if cleaned not in {"", "default_companion"} else (locked or "student_friend")
    SESSION_PERSONA_LOCK[session_id] = resolved
    if resolved != locked:
        _save_persona_lock_to_storage(user_id, session_id, resolved)
    return resolved


def _resolve_persona_prompt(persona_id: str) -> str:
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


def _build_style_anchor(messages: List[object], *, keep_n: int = 2) -> str:
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


def _latest_user_text(messages: List[object]) -> str:
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


def _analyze_companion_intent(user_text: str, has_media: bool) -> CompanionIntentDecision:
    text = (user_text or "").strip().lower()
    if not text:
        return CompanionIntentDecision(
            intent=CompanionIntentType.SMALL_TALK,
            route=CompanionRoute.COMPANION,
            confidence=0.99,
            reason="empty_input",
        )

    for pattern in HEAVY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return CompanionIntentDecision(
                intent=CompanionIntentType.HEAVY_TASK,
                route=CompanionRoute.HANDOFF,
                confidence=0.9,
                reason="matched_heavy_rule",
                matched_rule=pattern,
            )

    for pattern in ACTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return CompanionIntentDecision(
                intent=CompanionIntentType.COMPANION_ACTION,
                route=CompanionRoute.COMPANION,
                confidence=0.9,
                reason="matched_action_rule",
                matched_rule=pattern,
            )

    for pattern in KNOWLEDGE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return CompanionIntentDecision(
                intent=CompanionIntentType.KNOWLEDGE_QUERY,
                route=CompanionRoute.COMPANION,
                confidence=0.82,
                reason="matched_knowledge_rule",
                matched_rule=pattern,
            )

    if has_media:
        return CompanionIntentDecision(
            intent=CompanionIntentType.KNOWLEDGE_QUERY,
            route=CompanionRoute.COMPANION,
            confidence=0.76,
            reason="media_context",
            matched_rule="has_media",
        )

    return CompanionIntentDecision(
        intent=CompanionIntentType.SMALL_TALK,
        route=CompanionRoute.COMPANION,
        confidence=0.72,
        reason="default_small_talk",
    )


def _normalize_route_mode(route_mode: str) -> str:
    value = str(route_mode or "").strip().lower()
    if value in {ROUTE_MODE_CHAT_ONLY, "chat", "chat_only"}:
        return ROUTE_MODE_CHAT_ONLY
    if value in {ROUTE_MODE_TASK_FORCE_HARD, "task_force", "hard", "force_hard"}:
        return ROUTE_MODE_TASK_FORCE_HARD
    if value in {ROUTE_MODE_TASK_AUTO, "task", "task_auto"}:
        return ROUTE_MODE_TASK_AUTO
    return ROUTE_MODE_AUTO


def _classify_task_profile_with_fast_model(user_text: str) -> Dict[str, Any]:
    text = str(user_text or "").strip()
    if not text:
        return {
            "intent": "chat",
            "difficulty": 1,
            "task_kind": "chat",
            "need_ide": False,
            "confidence": 0.5,
            "source": "empty",
        }

    default_profile = {
        "intent": "task" if any(re.search(p, text, flags=re.IGNORECASE) for p in HEAVY_PATTERNS) else "chat",
        "difficulty": 3 if any(re.search(p, text, flags=re.IGNORECASE) for p in HEAVY_PATTERNS) else 1,
        "task_kind": "code" if re.search(r"代码|bug|脚本|重构|测试|deploy|debug|refactor", text, flags=re.IGNORECASE) else "non_code",
        "need_ide": bool(re.search(r"代码|文件|仓库|terminal|命令|run|debug|测试", text, flags=re.IGNORECASE)),
        "confidence": 0.58,
        "source": "heuristic",
    }

    if not COMPANION_ROUTE_CLASSIFIER_ENABLED:
        return default_profile

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是任务路由分类器。请只输出JSON，字段为："
                            "intent(chat|task),difficulty(1-5),task_kind(chat|non_code|code),need_ide(true|false),confidence(0-1)。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "model": COMPANION_FAST_MODEL,
                "generation": {
                    "max_tokens": 120,
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
            }
        )
        raw = str(result.get("reply", "")).strip()
        parsed: Dict[str, Any] = {}
        candidates = [raw]
        if "```" in raw:
            candidates.append(re.sub(r"```[a-zA-Z]*", "", raw).replace("```", "").strip())
        left, right = raw.find("{"), raw.rfind("}")
        if left != -1 and right > left:
            candidates.append(raw[left : right + 1])
        for cand in candidates:
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict):
                    parsed = obj
                    break
            except Exception:
                continue

        intent = str(parsed.get("intent", default_profile["intent"])).strip().lower()
        if intent not in {"chat", "task"}:
            intent = default_profile["intent"]
        difficulty = int(parsed.get("difficulty", default_profile["difficulty"]))
        difficulty = max(1, min(5, difficulty))
        task_kind = str(parsed.get("task_kind", default_profile["task_kind"])).strip().lower()
        if task_kind not in {"chat", "non_code", "code"}:
            task_kind = default_profile["task_kind"]
        need_ide = bool(parsed.get("need_ide", default_profile["need_ide"]))
        confidence = float(parsed.get("confidence", default_profile["confidence"]))
        confidence = max(0.0, min(1.0, confidence))
        return {
            "intent": intent,
            "difficulty": difficulty,
            "task_kind": task_kind,
            "need_ide": need_ide,
            "confidence": confidence,
            "source": "model",
        }
    except Exception:
        return default_profile


def _intent_instruction(decision: CompanionIntentDecision) -> str:
    if decision.intent == CompanionIntentType.COMPANION_ACTION:
        return (
            "当前意图=companion_action。优先生成可执行的 action_intents；"
            "若用户要求动作/表情，尽量返回至少一个合法动作。"
        )
    if decision.intent == CompanionIntentType.KNOWLEDGE_QUERY:
        return (
            "当前意图=knowledge_query。请简明解释，避免编造；"
            "若信息不确定，用温和语气说明不确定性。"
        )
    return "当前意图=small_talk。保持陪伴感与简洁回复。"


def _messages_to_plain_text(messages: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip().replace("\n", " ")
        if not role or not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _compact_dialog_with_summary(
    dialog_messages: List[Dict[str, str]],
    previous_summary: str,
) -> Tuple[List[Dict[str, str]], str, bool]:
    trigger = max(6, COMPANION_SUMMARY_TRIGGER_MESSAGES)
    keep_recent = max(4, COMPANION_SUMMARY_KEEP_RECENT)

    if len(dialog_messages) <= trigger:
        return dialog_messages, previous_summary, False

    old_part = dialog_messages[:-keep_recent]
    recent_part = dialog_messages[-keep_recent:]
    if not old_part:
        return dialog_messages, previous_summary, False

    # Keep summarization input bounded to avoid latency spikes.
    old_part = old_part[-12:]

    summary_system = (
        "你是对话记忆压缩器。请把旧对话压缩成结构化摘要，"
        "包含：用户偏好、稳定事实、当前目标、情绪风格、未决问题。"
        "只输出摘要正文，不要输出解释。"
    )
    summary_user = (
        "已有摘要：\n"
        f"{previous_summary or '无'}\n\n"
        "新增旧对话：\n"
        f"{_messages_to_plain_text(old_part)}\n\n"
        "请输出更新后的摘要。"
    )

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": summary_user},
                ],
                "model": COMPANION_FAST_MODEL,
                "generation": {
                    "max_tokens": 260,
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
            }
        )
        new_summary = str(result.get("reply", "")).strip()
    except Exception:
        new_summary = previous_summary

    if not new_summary:
        return dialog_messages, previous_summary, False

    max_chars = max(200, COMPANION_SUMMARY_MAX_CHARS)
    return recent_part, new_summary[:max_chars], True


def _run_heavy_task_with_main_model(user_task_input: str) -> Tuple[bool, str]:
    task_text = str(user_task_input or "").strip()
    if not task_text:
        return False, "任务输入为空，无法执行。"

    try:
        result = smart_model_dispatch(
            {
                "messages": [{"role": "user", "content": task_text}],
                "model": COMPANION_HEAVY_MODEL,
                "generation": {
                    "max_tokens": max(128, COMPANION_HEAVY_MAX_TOKENS),
                    "temperature": 0.25,
                    "top_p": 0.9,
                },
            }
        )
        reply = str(result.get("reply", "")).strip()
        if not reply:
            return False, "主任务模型没有返回可用内容。"
        return True, reply
    except Exception as exc:
        return False, str(exc)


def _build_delegated_result_prompt(
    user_task_input: str,
    *,
    ok: bool,
    heavy_result_text: str,
) -> str:
    status_line = "执行状态：成功" if ok else "执行状态：失败"
    return (
        "你现在负责把主任务模型的执行结果，用当前人设口吻转述给用户。\n"
        "回复要求：\n"
        "1) 第一短句先说“稍等，我先处理一下这个任务”。\n"
        "2) 第二部分给出处理结果；若失败，简明说明失败原因和下一步建议。\n"
        "3) 保持角色语气，禁止编造未执行的动作。\n\n"
        f"用户原任务：\n{str(user_task_input or '').strip()}\n\n"
        f"{status_line}\n"
        f"主任务模型输出：\n{str(heavy_result_text or '').strip()[:2400]}"
    )


def _delegated_session_key(user_id: str, session_id: str) -> str:
    return f"{(user_id or 'user1').strip()}::{(session_id or 'default').strip() or 'default'}"


def _summarize_heavy_result(user_task_input: str, ok: bool, heavy_result_text: str) -> str:
    text = str(heavy_result_text or "").strip()
    if not text:
        return "后台任务未返回有效内容。"

    if not ok:
        short = text[:240]
        return f"后台任务失败：{short}"

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是结果摘要器。请把主任务执行结果压缩成简短中文总结，"
                            "最多3条要点，并包含下一步建议。"
                            "只输出摘要正文。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"用户任务：{str(user_task_input or '').strip()}\n\n"
                            f"主任务结果：\n{text[:2600]}"
                        ),
                    },
                ],
                "model": COMPANION_FAST_MODEL,
                "generation": {
                    "max_tokens": 220,
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
            }
        )
        summary = str(result.get("reply", "")).strip()
        if summary:
            return summary[:900]
    except Exception as exc:
        logging.warning("delegated summary failed err=%s", exc)

    return text[:900]


def _cleanup_expired_delegated_tasks_locked(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    expired_ids = [
        task_id
        for task_id, task in _DELEGATED_TASKS.items()
        if float(task.get("expire_at", 0.0)) <= now
    ]
    if not expired_ids:
        return

    expired_set = set(expired_ids)
    for task_id in expired_ids:
        _DELEGATED_TASKS.pop(task_id, None)

    for session_key, task_ids in list(_DELEGATED_TASKS_BY_SESSION.items()):
        kept = [tid for tid in task_ids if tid not in expired_set]
        if kept:
            _DELEGATED_TASKS_BY_SESSION[session_key] = kept
        else:
            _DELEGATED_TASKS_BY_SESSION.pop(session_key, None)


def _run_delegated_task(task_id: str) -> None:
    with _DELEGATED_TASKS_LOCK:
        task = _DELEGATED_TASKS.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["updated_at"] = time.time()
        task_input = str(task.get("user_input", "")).strip()

    ok, raw_result = _run_heavy_task_with_main_model(task_input)
    summary = _summarize_heavy_result(task_input, ok, raw_result)
    now = time.time()

    with _DELEGATED_TASKS_LOCK:
        task = _DELEGATED_TASKS.get(task_id)
        if not task:
            return
        task["status"] = "completed" if ok else "failed"
        task["ok"] = bool(ok)
        task["result_raw"] = str(raw_result or "")
        task["result_summary"] = summary
        task["completed_at"] = now
        task["updated_at"] = now


def _create_delegated_task(user_id: str, session_id: str, user_input: str) -> Dict[str, Any]:
    now = time.time()
    task_id = uuid.uuid4().hex
    session_key = _delegated_session_key(user_id, session_id)
    task: Dict[str, Any] = {
        "task_id": task_id,
        "user_id": user_id,
        "session_id": session_id,
        "session_key": session_key,
        "user_input": str(user_input or "").strip(),
        "status": "queued",
        "ok": None,
        "result_raw": "",
        "result_summary": "",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "delivered": False,
        "expire_at": now + max(120, COMPANION_DELEGATED_TASK_TTL_SECONDS),
    }

    with _DELEGATED_TASKS_LOCK:
        _cleanup_expired_delegated_tasks_locked(now)
        _DELEGATED_TASKS[task_id] = task
        task_list = _DELEGATED_TASKS_BY_SESSION.setdefault(session_key, [])
        task_list.append(task_id)
        if len(task_list) > 20:
            _DELEGATED_TASKS_BY_SESSION[session_key] = task_list[-20:]
    return task


def _start_delegated_task(task_id: str) -> None:
    worker = threading.Thread(target=_run_delegated_task, args=(task_id,), daemon=True)
    worker.start()


def _poll_delegated_task(user_id: str, session_id: str, task_id: str = "") -> Optional[Dict[str, Any]]:
    session_key = _delegated_session_key(user_id, session_id)
    now = time.time()
    wanted_task_id = str(task_id or "").strip()
    with _DELEGATED_TASKS_LOCK:
        _cleanup_expired_delegated_tasks_locked(now)
        task_ids = list(_DELEGATED_TASKS_BY_SESSION.get(session_key, []))
        if not task_ids:
            return None

        if wanted_task_id:
            task = _DELEGATED_TASKS.get(wanted_task_id)
            if not task or str(task.get("session_key", "")) != session_key:
                return None
            status = str(task.get("status", ""))
            return {
                "task_id": wanted_task_id,
                "status": status,
                "ok": task.get("ok"),
                "user_input": str(task.get("user_input", "")),
                "main_result": str(task.get("result_raw", "")),
                "summary": str(task.get("result_summary", "")),
                "completed_at": task.get("completed_at"),
            }

        # Prefer returning the oldest finished-but-undelivered task.
        for task_id in task_ids:
            task = _DELEGATED_TASKS.get(task_id)
            if not task:
                continue
            status = str(task.get("status", ""))
            if status in {"completed", "failed"} and not bool(task.get("delivered", False)):
                task["delivered"] = True
                task["updated_at"] = now
                return {
                    "task_id": task_id,
                    "status": status,
                    "ok": bool(task.get("ok", False)),
                    "user_input": str(task.get("user_input", "")),
                    "main_result": str(task.get("result_raw", "")),
                    "summary": str(task.get("result_summary", "")),
                    "completed_at": task.get("completed_at"),
                }

        # If none completed, expose latest active task so frontend can keep waiting state.
        for task_id in reversed(task_ids):
            task = _DELEGATED_TASKS.get(task_id)
            if not task:
                continue
            status = str(task.get("status", ""))
            if status in {"queued", "running"}:
                return {
                    "task_id": task_id,
                    "status": status,
                    "ok": None,
                    "user_input": str(task.get("user_input", "")),
                    "main_result": "",
                    "summary": "",
                    "completed_at": None,
                }
    return None


def validate_expression(payload: Dict[str, object]) -> Tuple[bool, str]:
    name = payload.get("name")
    weight = payload.get("weight", 1.0)
    if name not in ALLOWED_EXPRESSIONS:
        return False, "invalid expression weight"
    if not isinstance(weight, (int, float)) or not (0.0 <= weight <= 1.0):
        return False, "invalid expression weight"
    return True, ""


def validate_motion(payload: Dict[str, object]) -> Tuple[bool, str]:
    group = payload.get("group")
    priority = payload.get("priority", 2)
    if group not in ALLOWED_MOTION_GROUPS:
        return False, "invalid motion group"
    if not isinstance(priority, int) or not (1 <= priority <= 3):
        return False, "invalid motion priory"
    return True, ""


def validate_look_at(payload: Dict[str, object]) -> Tuple[bool, str]:
    x = payload.get("x")
    y = payload.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False, "invalid look_at args"
    if not (-1.0 <= float(x) <= 1.0) or not (-1.0 <= float(y) <= 1.0):
        return False, "look_at out of range"
    return True, ""


def validate_game_control(payload: Dict[str, object]) -> Tuple[bool, str]:
    cmd = payload.get("command")
    duration = payload.get("duration_ms", 120)
    if cmd not in ALLOWED_GAME_COMMANDS:
        return False, "invalid game command"
    if not isinstance(duration, int) or not (100 <= duration <= 3000):
        return False, "invalid game duration"
    return True, ""


def validate_intent(intent: CompanionActionIntent) -> Tuple[bool, str]:
    if intent.type not in ALLOWED_ACTION_TYPES:
        return False, f"unsupported type:{intent.type}"
    if intent.type == "live2d_expression":
        return validate_expression(intent.payload)
    if intent.type == "live2d_motion":
        return validate_motion(intent.payload)
    if intent.type == "live2d_look_at":
        return validate_look_at(intent.payload)
    if intent.type == "game_control":
        return validate_game_control(intent.payload)
    return False, "unknown type"


def dispatch_intent(intent: CompanionActionIntent) -> Tuple[bool, str]:
    t = intent.type
    if t == "live2d_expression":
        return True, "ok"
    if t == "live2d_motion":
        return True, "ok"
    if t == "live2d_look_at":
        return True, "ok"
    if t == "game_control":
        result = execute_game_control(intent.payload)
        return bool(result.ok), str(result.reason or "")
    return False, "unsupported_dispatch_type"


@router.post("/companion/chat", response_model=CompanionChatResponse)
def api_companion_chat(payload: CompanionChatRequest) -> CompanionChatResponse:
    start = time.time()
    try:
        user_id = (payload.user_id or "user1").strip() or "user1"
        persona_id = _resolve_companion_persona_id(
            user_id,
            payload.session_id,
            payload.persona_id or "",
        )
        scene = payload.scene or "desktop"
        system_prompt = settings.build_companion_system_prompt(
            persona_id=persona_id,
            scene=scene,
        )
        memory_context = ""
        try:
            memory_context = build_companion_memory_context(
                user_id=user_id,
                session_id=payload.session_id,
                include_progress=True,
            )
        except Exception as exc:
            logging.warning(
                "companion memory load failed user=%s session=%s err=%s",
                user_id,
                payload.session_id,
                exc,
            )
        incoming_dialog_messages = [
            {"role": m.role, "content": (m.content or "").strip()}
            for m in payload.messages
            if (m.content or "").strip() and m.role in {"user", "assistant"}
        ]
        dialog_messages = merge_companion_dialog_history(
            payload.session_id,
            incoming_dialog_messages,
            limit=COMPANION_HISTORY_MAX_MESSAGES,
        )

        compressed_summary = ""
        summary_updated = False
        try:
            previous_summary = load_companion_compressed_summary(payload.session_id)
            dialog_messages, compressed_summary, summary_updated = _compact_dialog_with_summary(
                dialog_messages,
                previous_summary,
            )
            if summary_updated:
                save_companion_compressed_summary(payload.session_id, compressed_summary)
            elif not compressed_summary:
                compressed_summary = previous_summary
        except Exception as exc:
            logging.warning(
                "companion summary compact failed session=%s err=%s",
                payload.session_id,
                exc,
            )

        persona_prompt = _resolve_persona_prompt(persona_id)
        style_anchor = _build_style_anchor(dialog_messages)

        latest_user_text = _latest_user_text(dialog_messages)
        has_media = bool(payload.image_url or payload.audio_url)
        intent_decision = _analyze_companion_intent(latest_user_text, has_media=has_media)
        route_mode = _normalize_route_mode(payload.route_mode or "auto")
        task_profile = _classify_task_profile_with_fast_model(latest_user_text)

        if route_mode == ROUTE_MODE_CHAT_ONLY:
            delegated_heavy = False
        elif route_mode == ROUTE_MODE_TASK_FORCE_HARD:
            delegated_heavy = True
        elif route_mode == ROUTE_MODE_TASK_AUTO:
            delegated_heavy = task_profile.get("intent") == "task" and int(task_profile.get("difficulty", 1)) >= 3
        else:
            # auto: use model difficulty first, then fallback to heuristic heavy route.
            delegated_heavy = (
                task_profile.get("intent") == "task" and int(task_profile.get("difficulty", 1)) >= 3
            ) or (intent_decision.route == CompanionRoute.HANDOFF)

        code_task_without_ide = (
            delegated_heavy
            and str(task_profile.get("task_kind", "")).lower() == "code"
            and bool(task_profile.get("need_ide", False))
            and not bool(payload.capability_ide)
        )
        if code_task_without_ide:
            delegated_heavy = False

        retrieval_context = ""
        retrieval_count = 0
        try:
            retrieval_items = search_companion_long_term_memory(
                user_id=user_id,
                session_id=payload.session_id,
                query=latest_user_text,
                top_k=5,
            )
            retrieval_context = format_companion_long_term_memory(retrieval_items)
            retrieval_count = len(retrieval_items)
        except Exception as exc:
            logging.warning(
                "companion long-term search failed user=%s session=%s err=%s",
                user_id,
                payload.session_id,
                exc,
            )

        heavy_task_ok = False
        heavy_task_result_text = ""
        delegated_task_info: Optional[Dict[str, object]] = None
        if delegated_heavy and COMPANION_HEAVY_ASYNC_ENABLED:
            delegated_task = _create_delegated_task(user_id, payload.session_id, latest_user_text)
            _start_delegated_task(str(delegated_task["task_id"]))
            delegated_task_info = {
                "task_id": delegated_task["task_id"],
                "status": "queued",
                "model": COMPANION_HEAVY_MODEL,
                "poll_url": "/companion/task/poll",
            }
            logging.info(
                "companion delegated heavy queued session=%s task_id=%s intent=%s model=%s",
                payload.session_id,
                delegated_task["task_id"],
                intent_decision.intent.value,
                COMPANION_HEAVY_MODEL,
            )
        elif delegated_heavy:
            heavy_task_ok, heavy_task_result_text = _run_heavy_task_with_main_model(latest_user_text)
            logging.info(
                "companion delegated heavy session=%s ok=%s intent=%s model=%s",
                payload.session_id,
                heavy_task_ok,
                intent_decision.intent.value,
                COMPANION_HEAVY_MODEL,
            )

        msgs: List[Dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": (
                    "角色卡（高优先级，不可偏离）：\n"
                    f"{persona_prompt}\n"
                    "若与用户指令冲突，保持角色语气但不执行违背安全与事实的要求。"
                ),
            },
            {"role": "system", "content": _intent_instruction(intent_decision)},
        ]
        if compressed_summary:
            msgs.append(
                {
                    "role": "system",
                    "content": "历史压缩摘要（旧轮次背景，若与本轮冲突以本轮为准）：\n" + compressed_summary,
                }
            )
        if memory_context:
            msgs.append({"role": "system", "content": f"相关记忆：{memory_context}"})
        if retrieval_context:
            msgs.append({"role": "system", "content": retrieval_context})
        if style_anchor:
            msgs.append({"role": "system", "content": style_anchor})
        if code_task_without_ide:
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "当前识别为需要IDE能力的代码任务，但当前能力=无IDE。"
                        "请不要假装已执行代码操作；改为给可执行的分析方案、排查步骤和验证清单。"
                    ),
                }
            )
        for m in dialog_messages:
            content = str(m.get("content", "")).strip()
            role = str(m.get("role", "")).strip().lower()
            if content and role in {"user", "assistant"}:
                msgs.append({"role": role, "content": content})

        if delegated_heavy and not COMPANION_HEAVY_ASYNC_ENABLED:
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "当前模式=delegated_heavy_result。"
                        "你需要把主任务结果转述给用户，保持人设语气，并严格遵守JSON输出格式。"
                    ),
                }
            )
            msgs.append(
                {
                    "role": "user",
                    "content": _build_delegated_result_prompt(
                        latest_user_text,
                        ok=heavy_task_ok,
                        heavy_result_text=heavy_task_result_text,
                    ),
                }
            )

        lightweight = COMPANION_LIGHTWEIGHT_ENABLED
        if lightweight:
            msgs = _compact_messages(msgs)

        input_data: Dict[str, object] = {"messages": msgs}
        if payload.image_url:
            input_data["image_url"] = payload.image_url
        if payload.audio_url:
            input_data["audio_url"] = payload.audio_url

        if lightweight:
            max_tokens = COMPANION_LIGHTWEIGHT_MAX_TOKENS
            temperature = 0.55
            if intent_decision.intent == CompanionIntentType.KNOWLEDGE_QUERY:
                max_tokens = max(max_tokens, 240)
                temperature = 0.45
            input_data["generation"] = {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 0.9,
            }
            # For multimodal requests, keep model unset here so smart_model_dispatch
            # can pick remote_vision_model instead of forcing a text-only model.
            if COMPANION_FAST_MODEL and not payload.image_url:
                input_data["model"] = COMPANION_FAST_MODEL

        if payload.model:
            input_data["model"] = payload.model

        skip_model_dispatch = delegated_heavy and COMPANION_HEAVY_ASYNC_ENABLED
        raw_text = ""
        if skip_model_dispatch:
            raw_text = "收到，这个任务有点重，我先在后台处理。你可以继续和我聊天，处理完成后我会告诉你结果。"
        else:
            result = smart_model_dispatch(input_data)
            raw_text = str(result.get("reply", "")).strip()

        reply = raw_text
        tts_text = raw_text
        emotion = "neutral"
        action_intents: List[CompanionActionIntent] = []

        parsed: Dict[str, object] = {}
        if raw_text and not skip_model_dispatch:
            json_candidates: List[str] = [raw_text]
            if "```" in raw_text:
                cleaned = re.sub(r"```[a-zA-Z]*", "", raw_text).replace("```", "").strip()
                json_candidates.append(cleaned)
            left = raw_text.find("{")
            right = raw_text.rfind("}")
            if left != -1 and right != -1 and right > left:
                json_candidates.append(raw_text[left : right + 1])

            for cand in json_candidates:
                try:
                    obj = json.loads(cand)
                    if isinstance(obj, dict):
                        parsed = obj
                        break
                except Exception:
                    continue

        if parsed:
            reply = str(parsed.get("reply", raw_text)).strip() or raw_text
            tts_text = str(parsed.get("tts_text", reply)).strip() or reply
            emo = str(parsed.get("emotion", "neutral")).strip().lower()
            if emo in ALLOWED_EXPRESSIONS:
                emotion = emo

            raw_intents = parsed.get("action_intents", [])
            if isinstance(raw_intents, list):
                for item in raw_intents:
                    if not isinstance(item, dict):
                        continue
                    intent_type = str(item.get("type", "")).strip()
                    payload_obj = item.get("payload", {})
                    if not intent_type or not isinstance(payload_obj, dict):
                        continue
                    try:
                        intent = CompanionActionIntent(type=intent_type, payload=payload_obj)
                        ok, _ = validate_intent(intent)
                        if ok:
                            action_intents.append(intent)
                    except Exception:
                        continue

        max_chars = int(getattr(settings, "companion_tts_max_chars", 120))
        if max_chars > 0 and len(tts_text) > max_chars:
            tts_text = tts_text[:max_chars]

        if not reply:
            reply = "我在，继续和我说说。"
        if not tts_text:
            tts_text = reply

        latency_ms = int((time.time() - start) * 1000)
        try:
            signals = extract_companion_memory_signals(
                user_text=latest_user_text,
                session_id=payload.session_id,
            )
            persist_companion_memory_signals(user_id=user_id, signals=signals)
        except Exception as exc:
            logging.warning(
                "companion memory persist failed user=%s session=%s err=%s",
                user_id,
                payload.session_id,
                exc,
            )
        try:
            merged_for_save: List[Dict[str, object]] = list(dialog_messages)
            merged_for_save.append({"role": "assistant", "content": reply})
            save_companion_session_history(
                payload.session_id,
                merged_for_save,
                limit=COMPANION_HISTORY_MAX_MESSAGES,
            )
        except Exception as exc:
            logging.warning(
                "companion session save failed session=%s err=%s",
                payload.session_id,
                exc,
            )
        logging.info(
            "companion_chat ok session=%s persona_id=%s intent=%s route=%s delegated_heavy=%s delegated_task_id=%s confidence=%.2f context_messages=%s summary_updated=%s retrieval_count=%s lightweight=%s latency=%sms",
            payload.session_id,
            persona_id,
            intent_decision.intent.value,
            intent_decision.route.value,
            delegated_heavy,
            (delegated_task_info or {}).get("task_id", ""),
            intent_decision.confidence,
            len(dialog_messages),
            summary_updated,
            retrieval_count,
            lightweight,
            latency_ms,
        )
        return CompanionChatResponse(
            reply=reply,
            tts_text=tts_text,
            emotion=emotion,
            action_intents=action_intents,
            latency_ms=latency_ms,
            delegated_task=delegated_task_info,
            route_decision={
                "route_mode": route_mode,
                "delegated_heavy": delegated_heavy,
                "task_profile": task_profile,
                "code_task_without_ide": code_task_without_ide,
                "intent_heuristic": intent_decision.intent.value,
            },
        )
        
        
    except Exception as exc:
        logging.error(f"companion_chat failed: {exc}")
        raise HTTPException(status_code=500, detail=f"companion chat failed: {exc}")


@router.post("/companion/task/poll", response_model=CompanionTaskPollResponse)
def api_companion_task_poll(payload: CompanionTaskPollRequest) -> CompanionTaskPollResponse:
    try:
        user_id = (payload.user_id or "user1").strip() or "user1"
        session_id = (payload.session_id or "default").strip() or "default"
        task = _poll_delegated_task(
            user_id=user_id,
            session_id=session_id,
            task_id=payload.task_id or "",
        )
        return CompanionTaskPollResponse(ok=True, task=task)
    except Exception as exc:
        logging.error("companion task poll failed: %s", exc)
        return CompanionTaskPollResponse(ok=False, task=None)
 

@router.post("/companion/memory/debug")
def api_companion_memory_debug(payload: CompanionChatRequest) -> Dict[str, object]:
    user_id = (payload.user_id or "user1").strip() or "user1"
    session_id = payload.session_id or "default"

    incoming_dialog_messages = [
        {"role": m.role, "content": (m.content or "").strip()}
        for m in payload.messages
        if (m.content or "").strip() and m.role in {"user", "assistant"}
    ]
    dialog_messages = merge_companion_dialog_history(
        session_id,
        incoming_dialog_messages,
        limit=COMPANION_HISTORY_MAX_MESSAGES,
    )

    previous_summary = load_companion_compressed_summary(session_id)
    compacted_dialog, compacted_summary, summary_updated = _compact_dialog_with_summary(
        dialog_messages,
        previous_summary,
    )

    latest_user_text = _latest_user_text(compacted_dialog)
    retrieval_items = search_companion_long_term_memory(
        user_id=user_id,
        session_id=session_id,
        query=latest_user_text,
        top_k=5,
    )
    retrieval_context = format_companion_long_term_memory(retrieval_items)
    memory_context = build_companion_memory_context(
        user_id=user_id,
        session_id=session_id,
        include_progress=True,
    )

    return {
        "session_id": session_id,
        "history_messages": len(dialog_messages),
        "compacted_messages": len(compacted_dialog),
        "summary_updated_preview": bool(summary_updated),
        "previous_summary": previous_summary,
        "compacted_summary": compacted_summary,
        "latest_user_text": latest_user_text,
        "memory_context": memory_context,
        "retrieval_count": len(retrieval_items),
        "retrieval_items": retrieval_items,
        "retrieval_context": retrieval_context,
    }



@router.post("/companion/act", response_model=CompanionActResponse)
def api_companion_act(payload: CompanionActRequest) -> CompanionActResponse:
    applied: List[CompanionActionIntent] = []
    rejected: List[str] = []
    for i, intent in enumerate(payload.action_intents):
        ok, reason = validate_intent(intent)
        if not ok:
            rejected.append(f"#{i} {reason}")
            continue

        try:
            done, dispatch_reason = dispatch_intent(intent)
            if done:
                applied.append(intent)
            else:
                rejected.append(f"#{i} dispatch failed:{dispatch_reason or 'unknown'}")
        except Exception as exc:
            rejected.append(f"#{i} dispatch exception:{exc}")

    logging.info(
        "companion_act done total=%s applied=%s rejected=%s",
        len(payload.action_intents),
        len(applied),
        len(rejected),
    )
    return CompanionActResponse(
        ok=len(rejected) == 0,
        applied=applied,
        rejected=rejected,
    )
