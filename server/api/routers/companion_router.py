import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException

from server.api.schemas import (
    CompanionActRequest,
    CompanionActResponse,
    CompanionActionIntent,
    CompanionChatRequest,
    CompanionChatResponse,
    CompanionTaskPollRequest,
    TaskPollResponse,
)
from server.services.companion_action_service import dispatch_intent, validate_intent
from server.services.companion_chat_service import (
    build_chat_response,
    build_memory_debug,
)
from server.services.companion_task_service import cancel_task, poll_task


router = APIRouter(tags=["companion"])


@router.post("/companion/chat", response_model=CompanionChatResponse)
def api_companion_chat(payload: CompanionChatRequest) -> CompanionChatResponse:
    try:
        return build_chat_response(payload)
    except Exception as exc:
        logging.error("companion_chat failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"companion chat failed: {exc}")


@router.post("/companion/task/poll", response_model=TaskPollResponse)
def api_companion_task_poll(payload: CompanionTaskPollRequest) -> TaskPollResponse:
    try:
        user_id = (payload.user_id or "user1").strip() or "user1"
        session_id = (payload.session_id or "default").strip() or "default"
        task = poll_task(
            user_id=user_id,
            session_id=session_id,
            task_id=payload.task_id or "",
        )
        return TaskPollResponse(ok=True, task=task)
    except Exception as exc:
        logging.error("companion task poll failed: %s", exc)
        return TaskPollResponse(ok=False, task=None)


@router.post("/companion/task/cancel", response_model=TaskPollResponse)
def companion_task_cancel(payload: CompanionTaskPollRequest) -> TaskPollResponse:
    try:
        user_id = (payload.user_id or "user1").strip() or "user1"
        session_id = (payload.session_id or "default").strip() or "default"
        task = cancel_task(
            user_id=user_id,
            session_id=session_id,
            task_id=payload.task_id or "",
        )
        return TaskPollResponse(ok=task is not None, task=task)
    except Exception as exc:
        logging.error("companion task cancel failed: %s", exc)
        return TaskPollResponse(ok=False, task=None)


@router.post("/companion/memory/debug")
def companion_memory_debug(payload: CompanionChatRequest) -> Dict[str, object]:
    return build_memory_debug(payload)


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
