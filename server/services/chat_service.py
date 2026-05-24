import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from server.config.config import settings
from server.memory.conversation_store import (
    DEFAULT_HISTORY_MAX as CHAT_HISTORY_MAX,
    infer_scope,
    load_conversation,
    merge_dialog,
    save_conversation,
)
from server.memory.conversation_summary import compact_dialog
from server.infra.repo import (
    get_document_detail,
    list_learning_progress,
    list_user_preferences,
    list_user_reminders,
)
from server.services.model_service import remote_stream_events, smart_model_dispatch
from server.services.web_search_service import web_search
from server.services.chat.compose import build_final_messages
from server.services.chat.errors import append_error_row
from server.services.chat.memory import (
    build_memory_text,
    extract_memory_signals,
    get_short_term_memory,
    persist_memory_signals,
)
from server.services.chat.references import (
    build_inline_context_reference_items,
    build_reference_items,
    build_retrieval_context,
    build_web_context,
    build_web_reference_items,
)
from server.services.chat.retrieval import (
    get_latest_user_query,
    retrieve_chunks_for_chat,
    retrieve_chunks_multi,
    rewrite_retrieval_query,
    should_auto_web_search,
)


def _payload_messages(payload: Any) -> List[Dict[str, str]]:
    return [
        m.model_dump()
        for m in payload.messages
        if str(getattr(m, "content", "") or "").strip()
    ]



def _prepare_conversation(
    *,
    user_id: str,
    session_id: str,
    raw_messages: List[Dict[str, str]],
    scope: str,
    log_label: str,
) -> tuple[List[Dict[str, str]], str]:
    merged_messages = merge_dialog(
        user_id,
        session_id,
        raw_messages,
        scope=scope,
        limit=CHAT_HISTORY_MAX,
    )
    previous_summary = ""
    try:
        previous_summary = load_conversation(
            user_id,
            session_id,
            scope=scope,
            limit=2,
        ).get("compressed_summary", "")
        merged_messages, conversation_summary, did_summarize = compact_dialog(
            merged_messages,
            str(previous_summary or ""),
        )
        if not did_summarize and not conversation_summary:
            conversation_summary = str(previous_summary or "")
    except Exception as exc:
        logging.warning("%s summary compact failed session=%s err=%s", log_label, session_id, exc)
        conversation_summary = str(previous_summary or "")
    return merged_messages, conversation_summary





def _build_input_data(payload: Any, final_messages: List[Dict[str, str]]) -> Dict[str, Any]:
    input_data: Dict[str, Any] = {"messages": final_messages}
    if payload.image_url:
        input_data["image_url"] = payload.image_url
    if payload.audio_url:
        input_data["audio_url"] = payload.audio_url
    if payload.files:
        input_data["files"] = payload.files
    return input_data


def _user_error_msg(msg: str) -> tuple[str, str]:
    if "http 429" in msg or "rate-limited" in msg:
        return "当前请求较多，我这边有点忙，稍后再试一下。", "RATE_LIMIT"
    if "timeout" in msg.lower() or "timed out" in msg:
        return "这次请求超时了，请简化问题后再试。", "TIMEOUT"
    if "WinError 10054" in msg or "Remote end closed connection" in msg:
        return "网络连接不太稳定，请稍后重试。", "CONNECTION_ERROR"
    return "服务暂时不可用，请稍后再试。", "UNKNOWN"


async def handle_chat(payload: Any) -> Dict[str, Any]:
    start = time.time()
    session_id = payload.session_id.strip() if payload.session_id else "default"
    retrieved_chunks: List[Dict[str, object]] = []
    recall_ctx = ""
    try:
        if not session_id:
            session_id = "default"
        user_id = payload.user_id.strip() if payload.user_id else "default_user"
        if not user_id:
            user_id = "default_user"
        conversation_scope = infer_scope(session_id)
        raw_messages = _payload_messages(payload)
        merged_messages, conversation_summary = await run_in_threadpool(
            _prepare_conversation,
            user_id=user_id,
            session_id=session_id,
            raw_messages=raw_messages,
            scope=conversation_scope,
            log_label="chat",
        )

        short_mem = get_short_term_memory(
            session_id=session_id,
            merged_messages=merged_messages,
            rounds=settings.short_memory_rounds,
        )

        try:
            pref_items, progress_items = await asyncio.gather(
                run_in_threadpool(
                    list_user_preferences,
                    user_id=user_id,
                    limit=settings.long_memory_top_k,
                ),
                run_in_threadpool(
                    list_learning_progress,
                    user_id=user_id,
                    course_id=payload.document_id,
                    limit=settings.progress_top_k,
                ),
            )
        except Exception as exc:
            logging.warning(f"获取用户偏好失败: {exc}")
            pref_items = []
            progress_items = []

        try:
            reminders = await run_in_threadpool(
                list_user_reminders,
                user_id=user_id,
                lookahead_hours=48,
            )
            if reminders:
                progress_items = (progress_items or []) + reminders
        except Exception as exc:
            logging.warning(f"获取用户提醒失败: {exc}")

        memory_text = build_memory_text(
            short_mem=short_mem,
            pref_items=pref_items,
            progress_items=progress_items,
            pref_top_k=settings.long_memory_top_k,
            progress_top_k=settings.progress_top_k,
        )
        query = get_latest_user_query(merged_messages)
        retrieval_query = query
        effective_use_retrieval = bool(payload.use_retrieval or payload.document_ids or payload.document_id)
        effective_use_web_search = bool(payload.use_web_search or should_auto_web_search(query))
        web_results: List[Dict[str, object]] = []
        command_context = ""

        if effective_use_retrieval or effective_use_web_search:
            retrieval_query = await run_in_threadpool(
                rewrite_retrieval_query,
                query,
                merged_messages,
            )
        resolved_coursed_id: Optional[int] = None
        if payload.document_id:
            try:
                doc_detail = await run_in_threadpool(get_document_detail, payload.document_id)
                if doc_detail:
                    resolved_coursed_id = int(doc_detail.get("course_id") or 0)
            except Exception as exc:
                logging.warning(f"获取文档{payload.document_id}详情失败: {exc}")
        pref_signals, progress_signals = extract_memory_signals(
            user_text=query,
            document_id=resolved_coursed_id,
        )
        await run_in_threadpool(
            persist_memory_signals,
            user_id=user_id,
            pref_signals=pref_signals,
            progress_signals=progress_signals,
        )

        if effective_use_retrieval:
            eff_doc_ids = (
                list(payload.document_ids)
                if payload.document_ids
                else ([payload.document_id] if payload.document_id else [])
            )
            if eff_doc_ids:
                retrieved_chunks = await run_in_threadpool(
                    retrieve_chunks_multi,
                    query=retrieval_query,
                    document_ids=eff_doc_ids,
                    top_k=20,
                    candidate_limit=2000,
                )
            else:
                retrieved_chunks = await run_in_threadpool(
                    retrieve_chunks_for_chat,
                    query=retrieval_query,
                    document_id=payload.document_id,
                    top_k=20,
                    candidate_limit=2000,
                )
            recall_ctx = build_retrieval_context(retrieved_chunks)

        web_context = ""
        if effective_use_web_search:
            try:
                web_results = web_search(retrieval_query, top_k=5)
                web_context = build_web_context(web_results)
            except Exception as web_exc:
                logging.warning(f"web search failed: {web_exc}")

        final_messages = build_final_messages(
            merged_messages,
            conversation_summary=conversation_summary,
            memory_text=memory_text,
            query=query,
            recall_ctx=recall_ctx,
            web_context=web_context,
            command_context=command_context,
        )

        input_data = _build_input_data(payload, final_messages)
        result = await run_in_threadpool(smart_model_dispatch, input_data)

        latency_ms = int((time.time() - start) * 1000)
        logging.info(
            f"chat of session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms"
        )
        references = build_reference_items(retrieved_chunks) if effective_use_retrieval else []
        references.extend(
            build_web_reference_items(
                web_results,
                start_index=len(references) + 1,
                max_items=max(0, 8 - len(references)),
            )
        )
        references.extend(
            build_inline_context_reference_items(
                query,
                start_index=len(references) + 1,
                max_items=max(0, 8 - len(references)),
            )
        )
        merged_messages.append({
            "role": "assistant",
            "content": result["reply"],
            "refs": references,
            "metadata": {
                "usage": result.get("usage") or {},
                "model": result.get("model") or settings.remote_primary_model,
            },
        })
        await run_in_threadpool(
            save_conversation,
            user_id,
            session_id,
            merged_messages,
            scope=conversation_scope,
            limit=CHAT_HISTORY_MAX,
            compressed_summary=conversation_summary,
        )
        return {
            "reply": str(result.get("reply", "")),
            "latency_ms": int(result.get("latency_ms", 0)),
            "reference": references,
            "usage": result.get("usage") or {},
            "model": result.get("model") or settings.remote_primary_model,
        }
    except Exception as exc:
        msg = str(exc)
        latency_ms = int((time.time() - start) * 1000)
        logging.error(
            f"chat fail session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms err={msg}"
        )
        user_msg, error_type = _user_error_msg(msg)
        try:
            append_error_row(session_id, latency_ms, error_type, msg)
        except Exception as log_exc:
            logging.error(f"append_error_row failed: {log_exc}")
        raise HTTPException(status_code=500, detail=user_msg)


def create_chat_stream(payload: Any) -> StreamingResponse:
    start = time.time()
    session_id = payload.session_id.strip() if payload.session_id else "default"
    if not session_id:
        session_id = "default"
    user_id = payload.user_id.strip() if payload.user_id else "default_user"
    if not user_id:
        user_id = "default_user"
    conversation_scope = infer_scope(session_id)

    raw_messages = _payload_messages(payload)
    merged_messages, conversation_summary = _prepare_conversation(
        user_id=user_id,
        session_id=session_id,
        raw_messages=raw_messages,
        scope=conversation_scope,
        log_label="chat stream",
    )
    memory_text = ""
    query = get_latest_user_query(merged_messages)
    try:
        short_mem = get_short_term_memory(
            session_id=session_id,
            merged_messages=merged_messages,
            rounds=settings.short_memory_rounds,
        )
        memory_text = build_memory_text(
            short_mem=short_mem,
            pref_items=[],
            progress_items=[],
            pref_top_k=0,
            progress_top_k=0,
        )
    except Exception as exc:
        logging.warning(f"chat_stream memory inject failed: {exc}")

    def status_event(label: str, detail: str = "", kind: str = "activity") -> str:
        return f"data: {json.dumps({'status': {'label': label, 'detail': detail, 'kind': kind}}, ensure_ascii=False)}\n\n"

    def event_gen():
        try:
            yield status_event("正在判断是否需要检索或联网", kind="plan")
            recall_ctx = ""
            web_context = ""
            command_context = ""
            retrieved_chunks: List[Dict[str, object]] = []
            web_results: List[Dict[str, object]] = []
            retrieval_query = query
            effective_use_retrieval = bool(payload.use_retrieval or payload.document_ids or payload.document_id)
            effective_use_web_search = bool(payload.use_web_search or should_auto_web_search(query))

            if effective_use_retrieval or effective_use_web_search:
                try:
                    yield status_event("正在改写检索查询", kind="search")
                    retrieval_query = rewrite_retrieval_query(query, merged_messages)
                except Exception as exc:
                    logging.warning(f"chat_stream query rewrite failed: {exc}")

            if effective_use_retrieval:
                try:
                    yield status_event("正在查找本地资料", retrieval_query, kind="retrieval")
                    eff_doc_ids = (
                        list(payload.document_ids)
                        if payload.document_ids
                        else ([payload.document_id] if payload.document_id else [])
                    )
                    if eff_doc_ids:
                        retrieved_chunks = retrieve_chunks_multi(
                            query=retrieval_query,
                            document_ids=eff_doc_ids,
                            top_k=20,
                            candidate_limit=2000,
                        )
                    else:
                        retrieved_chunks = retrieve_chunks_for_chat(
                            query=retrieval_query,
                            document_id=payload.document_id,
                            top_k=20,
                            candidate_limit=2000,
                        )
                    recall_ctx = build_retrieval_context(retrieved_chunks)
                    yield status_event(f"找到 {len(retrieved_chunks)} 条本地资料片段", kind="retrieval")
                except Exception as exc:
                    logging.warning(f"chat_stream retrieval failed: {exc}")
                    retrieved_chunks = []
                    recall_ctx = ""

            if effective_use_web_search:
                try:
                    yield status_event("正在查找网上资料", retrieval_query, kind="web")
                    web_results = web_search(retrieval_query, top_k=5)
                    web_context = build_web_context(web_results)
                    yield status_event(f"找到 {len(web_results)} 条网页结果", kind="web")
                except Exception as exc:
                    logging.warning(f"chat_stream web search failed: {exc}")
                    web_context = ""
                    web_results = []

            references = build_reference_items(retrieved_chunks) if effective_use_retrieval else []
            references.extend(
                build_web_reference_items(
                    web_results,
                    start_index=len(references) + 1,
                    max_items=max(0, 8 - len(references)),
                )
            )
            references.extend(
                build_inline_context_reference_items(
                    query,
                    start_index=len(references) + 1,
                    max_items=max(0, 8 - len(references)),
                )
            )
            final_messages = build_final_messages(
                merged_messages,
                conversation_summary=conversation_summary,
                memory_text=memory_text,
                query=query,
                recall_ctx=recall_ctx,
                web_context=web_context,
                command_context=command_context,
            )
            yield status_event("正在生成回答", kind="model")

            if payload.image_url or payload.audio_url or payload.files:
                input_data = _build_input_data(payload, final_messages)
                result = smart_model_dispatch(input_data)
                reply = str(result.get("reply", "")).strip()
                usage = dict(result.get("usage") or {})
                model = str(result.get("model") or settings.remote_primary_model)
                if reply:
                    yield f"data: {json.dumps({'delta': reply}, ensure_ascii=False)}\n\n"
                latency_ms = int((time.time() - start) * 1000)
                yield f"data: {json.dumps({'done': True, 'reply': reply, 'latency_ms': latency_ms, 'reference': references, 'usage': usage, 'model': model}, ensure_ascii=False)}\n\n"
                merged_messages.append({
                    "role": "assistant",
                    "content": reply,
                    "refs": references,
                    "metadata": {"usage": usage, "model": model},
                })
                save_conversation(
                    user_id,
                    session_id,
                    merged_messages,
                    scope=conversation_scope,
                    limit=CHAT_HISTORY_MAX,
                    compressed_summary=conversation_summary,
                )
                return

            stream_generation = {
                "max_tokens": max(settings.max_new_tokens, 1600),
                "temperature": settings.temperature,
                "top_p": settings.top_p,
            }
            reply_chunks: List[str] = []
            usage: Dict[str, object] = {}
            try:
                for event in remote_stream_events(final_messages, generation=stream_generation):
                    if event.get("type") == "usage":
                        usage = dict(event.get("usage") or {})
                        yield f"data: {json.dumps({'usage': usage}, ensure_ascii=False)}\n\n"
                        continue
                    raw_delta = event.get("delta", "")
                    if raw_delta is None:
                        continue
                    delta = str(raw_delta)
                    if delta:
                        reply_chunks.append(delta)
                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            except Exception as stream_exc:
                logging.warning(f"chat stream upstream failed, fallback to non-stream: {stream_exc}")
                fallback_result = smart_model_dispatch({"messages": final_messages, "generation": stream_generation})
                fallback_reply = str(fallback_result.get("reply", "")).strip()
                if not fallback_reply:
                    raise stream_exc
                reply_chunks = [fallback_reply]
                usage = dict(fallback_result.get("usage") or {})
                yield f"data: {json.dumps({'delta': fallback_reply}, ensure_ascii=False)}\n\n"

            reply = "".join(reply_chunks).strip()
            latency_ms = int((time.time() - start) * 1000)
            model = settings.remote_primary_model
            merged_messages.append({
                "role": "assistant",
                "content": reply,
                "refs": references,
                "metadata": {"usage": usage, "model": model},
            })
            save_conversation(
                user_id,
                session_id,
                merged_messages,
                scope=conversation_scope,
                limit=CHAT_HISTORY_MAX,
                compressed_summary=conversation_summary,
            )
            yield f"data: {json.dumps({'done': True, 'reply': reply, 'latency_ms': latency_ms, 'usage': usage, 'reference': references, 'model': model}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            msg = str(exc)
            latency_ms = int((time.time() - start) * 1000)
            logging.error(
                f"chat stream fail session={session_id} model={settings.remote_primary_model} latency={latency_ms}ms err={msg}"
            )
            yield f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
