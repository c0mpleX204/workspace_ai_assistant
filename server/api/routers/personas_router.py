import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.api.schemas import (
    PersonaApplyRequest,
    PersonaItem,
    PersonaListResponse,
    PersonaSaveRequest,
)
from server.config.config import settings
from server.memory.conversation_store import load_conversation, save_conversation
from server.services.ai.model import remote_stream_events, smart_model_dispatch
from server.services.personas import list_personas, save_persona_markdown

router = APIRouter(tags=["personas"])


@router.get("/personas", response_model=PersonaListResponse)
def personas() -> PersonaListResponse:
    items = [PersonaItem(**item) for item in list_personas()]
    return PersonaListResponse(items=items, total=len(items))


@router.post("/personas", response_model=PersonaItem)
def create_persona(payload: PersonaSaveRequest) -> PersonaItem:
    return PersonaItem(**save_persona_markdown(payload.name, payload.content))


@router.post("/personas/apply/stream")
def apply_persona_stream(payload: PersonaApplyRequest):
    start = time.time()
    persona_prompt = str(payload.persona_prompt or "").strip()
    session_id = str(payload.session_id or "").strip()
    user_id = str(payload.user_id or "default_user").strip() or "default_user"
    clean_messages = [
        {"role": item.role, "content": str(item.content or "").strip()}
        for item in payload.messages
        if item.role in {"user", "assistant"} and str(item.content or "").strip()
    ][-24:]

    final_messages = [
        {"role": "system", "content": persona_prompt},
        {
            "role": "system",
            "content": (
                "你正在对一段已有聊天进行人格化重处理。"
                "输入只包含用户与 AI 的纯对话内容，不包含工具计划、终端操作、任务状态或 UI 日志。"
                "请以当前人设重新处理这段对话，优先回应最后一个用户需求。"
                "不要提到你在重写，不要声称执行工具，不要编造外部动作。"
            ),
        },
        *clean_messages,
        {
            "role": "user",
            "content": "请以当前人设重新处理上面的纯对话，只输出处理后的回复。",
        },
    ]

    def event_gen():
        full_text = ""
        usage = {}
        try:
            try:
                for event in remote_stream_events(final_messages):
                    if event.get("type") == "usage":
                        usage = dict(event.get("usage") or {})
                        yield f"data: {json.dumps({'usage': usage}, ensure_ascii=False)}\n\n"
                        continue
                    delta = str(event.get("delta") or "")
                    if delta:
                        full_text += delta
                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logging.warning("persona apply stream fallback: %s", exc)
                result = smart_model_dispatch({"messages": final_messages})
                full_text = str(result.get("reply") or "")
                usage = dict(result.get("usage") or {})
                if full_text:
                    yield f"data: {json.dumps({'delta': full_text}, ensure_ascii=False)}\n\n"
                if usage:
                    yield f"data: {json.dumps({'usage': usage}, ensure_ascii=False)}\n\n"

            if payload.persist_to_session and session_id and full_text.strip():
                try:
                    existing = load_conversation(user_id, session_id)
                    messages = list(existing.get("messages", []))
                    messages.append(
                        {
                            "role": "assistant",
                            "content": full_text.strip(),
                            "metadata": {"transient_persona_apply": True},
                        }
                    )
                    save_conversation(user_id, session_id, messages)
                except Exception as exc:
                    logging.warning("persist persona apply reply failed: %s", exc)

            yield f"data: {json.dumps({'done': True, 'reply': full_text, 'latency_ms': int((time.time() - start) * 1000), 'usage': usage, 'model': settings.remote_primary_model}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
