import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

from server.api.schemas import CompanionActionIntent, CompanionChatRequest, CompanionChatResponse
from server.config.config import settings
from server.dialogue.companion_persona import (
    build_style_anchor,
    latest_user_text,
    resolve_persona_id,
    resolve_persona_prompt,
)
from server.memory.companion_memory import (
    build_memory_ctx,
    extract_mem_signals,
    format_recall,
    save_mem_signals,
    search_recall,
)
from server.memory.companion_session_store import (
    DEFAULT_HISTORY_MAX,
    load_summary,
    merge_dialog,
    save_summary,
    save_session,
)
from server.memory.companion_summary import compact_dialog, compact_msgs
from server.orchestration.companion_routing import (
    FAST_MODEL,
    CompanionIntentType,
    CompanionRoute,
    analyze_intent,
    classify_task,
    default_task_profile,
    intent_instruction,
    normalize_route_mode,
    MODE_CHAT,
    MODE_TASK,
    MODE_FORCE_TASK,
)
from server.services.companion_action_service import EXPRESSIONS, validate_intent
from server.services.companion_task_service import (
    HEAVY_ASYNC,
    HEAVY_MODEL,
    task_result_prompt,
    create_task,
    run_heavy_task,
    start_task,
)
from server.services.model_service import smart_model_dispatch


LIGHT_MODE = os.getenv("COMPANION_LIGHTWEIGHT_ENABLED", "true").lower() == "true"
LIGHT_TOKEN_MAX = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_TOKENS", "180"))
HISTORY_MAX = int(
    os.getenv("COMPANION_HISTORY_MAX_MESSAGES", str(DEFAULT_HISTORY_MAX))
)


def build_chat_response(payload: CompanionChatRequest) -> CompanionChatResponse:
    start = time.time()
    user_id = (payload.user_id or "user1").strip() or "user1"
    persona_id = resolve_persona_id(
        user_id,
        payload.session_id,
        payload.persona_id or "",
    )
    scene = payload.scene or "desktop"
    system_prompt = settings.build_companion_prompt(
        persona_id=persona_id,
        scene=scene,
    )

    memory_ctx = ""
    try:
        memory_ctx = build_memory_ctx(
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

    incoming_msgs: List[Dict[str, object]] = [
        {"role": m.role, "content": (m.content or "").strip()}
        for m in payload.messages
        if (m.content or "").strip() and m.role in {"user", "assistant"}
    ]
    dialog = merge_dialog(
        payload.session_id,
        incoming_msgs,
        limit=HISTORY_MAX,
    )

    summary = ""
    did_summarize = False
    try:
        previous_summary = load_summary(payload.session_id)
        dialog, summary, did_summarize = compact_dialog(
            dialog,
            previous_summary,
        )
        if did_summarize:
            save_summary(payload.session_id, summary)
        elif not summary:
            summary = previous_summary
    except Exception as exc:
        logging.warning("companion summary compact failed session=%s err=%s", payload.session_id, exc)

    persona_prompt = resolve_persona_prompt(persona_id)
    style_msgs: List[object] = [m for m in dialog]
    style_anchor = build_style_anchor(style_msgs)
    latest_text = latest_user_text(style_msgs)
    has_media = bool(payload.image_url or payload.audio_url)
    intent_decision = analyze_intent(latest_text, has_media=has_media)
    route_mode = normalize_route_mode(payload.route_mode or "auto")
    task_profile = default_task_profile(latest_text)
    if route_mode not in {MODE_CHAT, MODE_FORCE_TASK}:
        task_profile = classify_task(latest_text)
    else:
        task_profile["source"] = f"route_mode:{route_mode}"

    if route_mode == MODE_CHAT:
        delegated_heavy = False
    elif route_mode == MODE_FORCE_TASK:
        delegated_heavy = True
    elif route_mode == MODE_TASK:
        delegated_heavy = task_profile.get("intent") == "task" and int(task_profile.get("difficulty", 1)) >= 3
    else:
        delegated_heavy = (
            task_profile.get("intent") == "task" and int(task_profile.get("difficulty", 1)) >= 3
        ) or (intent_decision.route == CompanionRoute.HANDOFF)

    code_needs_ide = (
        delegated_heavy
        and str(task_profile.get("task_kind", "")).lower() == "code"
        and bool(task_profile.get("need_ide", False))
        and not bool(payload.capability_ide)
    )
    if code_needs_ide:
        delegated_heavy = False

    recall_ctx = ""
    recall_count = 0
    try:
        recall_items = search_recall(
            user_id=user_id,
            session_id=payload.session_id,
            query=latest_text,
            top_k=5,
        )
        recall_ctx = format_recall(recall_items)
        recall_count = len(recall_items)
    except Exception as exc:
        logging.warning(
            "companion long-term search failed user=%s session=%s err=%s",
            user_id,
            payload.session_id,
            exc,
        )

    heavy_ok = False
    heavy_result = ""
    task_info: Optional[Dict[str, object]] = None
    task_reject_reason = ""
    if delegated_heavy and HEAVY_ASYNC:
        try:
            delegated_task = create_task(user_id, payload.session_id, latest_text)
            start_task(str(delegated_task["task_id"]))
            task_info = {
                "task_id": delegated_task["task_id"],
                "status": "queued",
                "model": HEAVY_MODEL,
                "poll_url": "/companion/task/poll",
            }
            logging.info(
                "companion delegated heavy queued session=%s task_id=%s intent=%s model=%s",
                payload.session_id,
                delegated_task["task_id"],
                intent_decision.intent.value,
                HEAVY_MODEL,
            )
        except RuntimeError as exc:
            task_reject_reason = str(exc)
            logging.info("companion delegated heavy rejected session=%s reason=%s", payload.session_id, exc)
    elif delegated_heavy:
        heavy_ok, heavy_result = run_heavy_task(latest_text)
        logging.info(
            "companion delegated heavy session=%s ok=%s intent=%s model=%s",
            payload.session_id,
            heavy_ok,
            intent_decision.intent.value,
            HEAVY_MODEL,
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
        {"role": "system", "content": intent_instruction(intent_decision)},
    ]
    if summary:
        msgs.append(
            {
                "role": "system",
                "content": "历史压缩摘要（旧轮次背景，若与本轮冲突以本轮为准）：\n" + summary,
            }
        )
    if memory_ctx:
        msgs.append({"role": "system", "content": f"相关记忆：{memory_ctx}"})
    if recall_ctx:
        msgs.append({"role": "system", "content": recall_ctx})
    if style_anchor:
        msgs.append({"role": "system", "content": style_anchor})
    if code_needs_ide:
        msgs.append(
            {
                "role": "system",
                "content": (
                    "当前识别为需要IDE能力的代码任务，但当前能力=无IDE。"
                    "请不要假装已执行代码操作；改为给可执行的分析方案、排查步骤和验证清单。"
                ),
            }
        )
    for m in dialog:
        content = str(m.get("content", "")).strip()
        role = str(m.get("role", "")).strip().lower()
        if content and role in {"user", "assistant"}:
            msgs.append({"role": role, "content": content})

    if delegated_heavy and not HEAVY_ASYNC:
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
                "content": task_result_prompt(
                    latest_text,
                    ok=heavy_ok,
                    result_text=heavy_result,
                ),
            }
        )

    lightweight = LIGHT_MODE
    if lightweight:
        msgs = compact_msgs(msgs)

    input_data: Dict[str, object] = {"messages": msgs}
    if payload.image_url:
        input_data["image_url"] = payload.image_url
    if payload.audio_url:
        input_data["audio_url"] = payload.audio_url

    if lightweight:
        max_tokens = LIGHT_TOKEN_MAX
        temperature = 0.55
        if intent_decision.intent == CompanionIntentType.KNOWLEDGE_QUERY:
            max_tokens = max(max_tokens, 240)
            temperature = 0.45
        input_data["generation"] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
        }
        if FAST_MODEL and not payload.image_url:
            input_data["model"] = FAST_MODEL

    if payload.model:
        input_data["model"] = payload.model

    skip_model_dispatch = delegated_heavy and HEAVY_ASYNC
    if skip_model_dispatch:
        if task_info:
            raw_text = "收到，这个任务有点重，我先在后台处理。你可以继续和我聊天，处理完成后我会告诉你结果。"
        else:
            raw_text = (
                "现在后台任务队列有点忙，我先不再启动新的重任务。"
                "你可以等当前任务完成后再试，或者把问题拆小一点让我先直接回答。"
            )
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
        if emo in EXPRESSIONS:
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
        signals = extract_mem_signals(
            user_text=latest_text,
            session_id=payload.session_id,
        )
        save_mem_signals(user_id=user_id, signals=signals)
    except Exception as exc:
        logging.warning("companion memory persist failed user=%s session=%s err=%s", user_id, payload.session_id, exc)

    try:
        
        merged_for_save: List[Dict[str, object]] = list(dialog)
        merged_for_save.append({"role": "assistant", "content": reply})
        save_session(
            payload.session_id,
            merged_for_save,
            limit=HISTORY_MAX,
        )
    except Exception as exc:
        logging.warning("companion session save failed session=%s err=%s", payload.session_id, exc)

    logging.info(
        "companion_chat ok session=%s persona_id=%s intent=%s route=%s delegated_heavy=%s delegated_task_id=%s confidence=%.2f context_messages=%s did_summarize=%s recall_count=%s lightweight=%s latency=%sms",
        payload.session_id,
        persona_id,
        intent_decision.intent.value,
        intent_decision.route.value,
        delegated_heavy,
        (task_info or {}).get("task_id", ""),
        intent_decision.confidence,
        len(dialog),
        did_summarize,
        recall_count,
        lightweight,
        latency_ms,
    )
    return CompanionChatResponse(
        reply=reply,
        tts_text=tts_text,
        emotion=emotion,
        action_intents=action_intents,
        latency_ms=latency_ms,
        delegated_task=task_info,
        route_decision={
            "route_mode": route_mode,
            "delegated_heavy": delegated_heavy,
            "task_reject_reason": task_reject_reason,
            "task_profile": task_profile,
            "code_needs_ide": code_needs_ide,
            "intent_heuristic": intent_decision.intent.value,
        },
    )


def build_memory_debug(payload: CompanionChatRequest) -> Dict[str, object]:
    user_id = (payload.user_id or "user1").strip() or "user1"
    session_id = payload.session_id or "default"

    incoming_msgs = [
        {"role": m.role, "content": (m.content or "").strip()}
        for m in payload.messages
        if (m.content or "").strip() and m.role in {"user", "assistant"}
    ]
    dialog = merge_dialog(
        session_id,
        incoming_msgs,
        limit=HISTORY_MAX,
    )

    previous_summary = load_summary(session_id)
    compacted_dialog, compacted_summary, did_summarize = compact_dialog(
        dialog,
        previous_summary,
    )

    latest_text = latest_user_text(compacted_dialog)
    recall_items = search_recall(
        user_id=user_id,
        session_id=session_id,
        query=latest_text,
        top_k=5,
    )
    recall_ctx = format_recall(recall_items)
    memory_ctx = build_memory_ctx(
        user_id=user_id,
        session_id=session_id,
        include_progress=True,
    )

    return {
        "session_id": session_id,
        "history_messages": len(dialog),
        "compacted_messages": len(compacted_dialog),
        "summary_updated_preview": bool(did_summarize),
        "previous_summary": previous_summary,
        "compacted_summary": compacted_summary,
        "latest_user_text": latest_text,
        "memory_ctx": memory_ctx,
        "recall_count": len(recall_items),
        "recall_items": recall_items,
        "recall_ctx": recall_ctx,
    }
