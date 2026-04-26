import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from server.services.model_service import smart_model_dispatch


FAST_MODEL = os.getenv("COMPANION_FAST_MODEL", "Pro/Qwen/Qwen2.5-7B-Instruct").strip()
CLASSIFIER_ON = (
    os.getenv("COMPANION_ROUTE_CLASSIFIER_ENABLED", "true").strip().lower() == "true"
)

MODE_AUTO = "auto"
MODE_CHAT = "chat_only"
MODE_TASK = "task_auto"
MODE_FORCE_TASK = "task_force_hard"

ACTION_PATTERNS = (
    r"笑一笑|微笑|生气|难过|惊讶|挥手|点头|看向|look at|wave|smile",
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


class CompanionIntentType(str, Enum):
    SMALL_TALK = "small_talk"
    COMPANION_ACTION = "companion_action"
    KNOWLEDGE_QUERY = "knowledge_query"
    HEAVY_TASK = "heavy_task"


class CompanionRoute(str, Enum):
    COMPANION = "companion"
    HANDOFF = "handoff"


@dataclass(slots=True)
class IntentDecision:
    intent: CompanionIntentType
    route: CompanionRoute
    confidence: float
    reason: str
    matched_rule: str = ""


def analyze_intent(user_text: str, has_media: bool) -> IntentDecision:
    text = (user_text or "").strip().lower()
    if not text:
        return IntentDecision(
            intent=CompanionIntentType.SMALL_TALK,
            route=CompanionRoute.COMPANION,
            confidence=0.99,
            reason="empty_input",
        )

    for pattern in HEAVY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return IntentDecision(
                intent=CompanionIntentType.HEAVY_TASK,
                route=CompanionRoute.HANDOFF,
                confidence=0.9,
                reason="matched_heavy_rule",
                matched_rule=pattern,
            )

    for pattern in ACTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return IntentDecision(
                intent=CompanionIntentType.COMPANION_ACTION,
                route=CompanionRoute.COMPANION,
                confidence=0.9,
                reason="matched_action_rule",
                matched_rule=pattern,
            )

    for pattern in KNOWLEDGE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return IntentDecision(
                intent=CompanionIntentType.KNOWLEDGE_QUERY,
                route=CompanionRoute.COMPANION,
                confidence=0.82,
                reason="matched_knowledge_rule",
                matched_rule=pattern,
            )

    if has_media:
        return IntentDecision(
            intent=CompanionIntentType.KNOWLEDGE_QUERY,
            route=CompanionRoute.COMPANION,
            confidence=0.76,
            reason="media_context",
            matched_rule="has_media",
        )

    return IntentDecision(
        intent=CompanionIntentType.SMALL_TALK,
        route=CompanionRoute.COMPANION,
        confidence=0.72,
        reason="default_small_talk",
    )


def normalize_route_mode(route_mode: str) -> str:
    value = str(route_mode or "").strip().lower()
    if value in {MODE_CHAT, "chat", "chat_only"}:
        return MODE_CHAT
    if value in {MODE_FORCE_TASK, "task_force", "hard", "force_hard"}:
        return MODE_FORCE_TASK
    if value in {MODE_TASK, "task", "task_auto"}:
        return MODE_TASK
    return MODE_AUTO


def default_task_profile(user_text: str) -> Dict[str, Any]:
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

    heavy = any(re.search(p, text, flags=re.IGNORECASE) for p in HEAVY_PATTERNS)
    return {
        "intent": "task" if heavy else "chat",
        "difficulty": 3 if heavy else 1,
        "task_kind": "code"
        if re.search(r"代码|bug|脚本|重构|测试|deploy|debug|refactor", text, flags=re.IGNORECASE)
        else "non_code",
        "need_ide": bool(
            re.search(r"代码|文件|仓库|terminal|命令|run|debug|测试", text, flags=re.IGNORECASE)
        ),
        "confidence": 0.58,
        "source": "heuristic",
    }


def classify_task(user_text: str) -> Dict[str, Any]:
    text = str(user_text or "").strip()
    fallback = default_task_profile(text)
    if not text or not CLASSIFIER_ON:
        return fallback

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是任务路由分类器。请只输出JSON，字段为："
                            "intent(chat|task),difficulty(1-5),task_kind(chat|non_code|code),"
                            "need_ide(true|false),confidence(0-1)。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "model": FAST_MODEL,
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

        intent = str(parsed.get("intent", fallback["intent"])).strip().lower()
        if intent not in {"chat", "task"}:
            intent = fallback["intent"]
        difficulty = int(parsed.get("difficulty", fallback["difficulty"]))
        difficulty = max(1, min(5, difficulty))
        task_kind = str(parsed.get("task_kind", fallback["task_kind"])).strip().lower()
        if task_kind not in {"chat", "non_code", "code"}:
            task_kind = fallback["task_kind"]
        need_ide = bool(parsed.get("need_ide", fallback["need_ide"]))
        confidence = float(parsed.get("confidence", fallback["confidence"]))
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
        return fallback


def intent_instruction(decision: IntentDecision) -> str:
    if decision.intent == CompanionIntentType.COMPANION_ACTION:
        return (
            "当前意图=companion_action。优先生成可执行的action_intents；"
            "若用户要求动作/表情，尽量返回至少一个合法动作。"
        )
    if decision.intent == CompanionIntentType.KNOWLEDGE_QUERY:
        return (
            "当前意图=knowledge_query。请简明解释，避免编造；"
            "若信息不确定，用温和语气说明不确定性。"
        )
    return "当前意图=small_talk。保持陪伴感与简洁回复。"
