from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, List
from uuid import uuid4

from fastapi.responses import StreamingResponse

from server.config.config import settings
from server.memory.conversation_store import (
    DEFAULT_HISTORY_MAX as CHAT_HISTORY_MAX,
    infer_scope,
    load_conversation,
    save_conversation,
)
from server.services.agent.command import (
    build_command_context,
    resolve_command_cwd,
    run_agent_command,
)
from server.services.agent.operations import _extract_code_operations
from server.services.agent.payload import _payload_to_messages
from server.services.agent.plan import (
    _initial_plan,
    _plan_from_planner,
    _planner_context,
    _set_plan_status,
    _update_plan_step,
)
from server.services.agent.reshape import _normalize_planner, reshape_agent_request
from server.services.agent.state import _now_iso, _save_run, load_agent_run
from server.services.chat.flow import (
    _prepare_conversation,
    build_final_messages,
    build_inline_context_reference_items,
    build_reference_items,
    build_retrieval_context,
    build_web_context,
    build_web_reference_items,
    get_latest_user_query,
    retrieve_chunks_for_chat,
    retrieve_chunks_multi,
    rewrite_retrieval_query,
)
from server.services.ai.model import remote_stream_events, smart_model_dispatch
from server.services.project.memory import load_project_memory, schedule_project_memory_update
from server.services.search.web import web_search


def create_agent_run_stream(payload: Any) -> StreamingResponse:
    start = time.time()
    run_id = uuid4().hex
    session_id = str(getattr(payload, "session_id", "") or "default").strip() or "default"
    user_id = str(getattr(payload, "user_id", "") or "default_user").strip() or "default_user"
    conversation_scope = infer_scope(session_id)
    workspace_path = str(getattr(payload, "workspace_path", "") or "")
    raw_messages = _payload_to_messages(payload)
    try:
        stored_messages_before = load_conversation(
            user_id,
            session_id,
            scope=conversation_scope,
            limit=2,
        ).get("messages", [])
    except Exception:
        stored_messages_before = []
    is_new_project_dialog = bool(workspace_path.strip()) and not stored_messages_before
    project_memory_text = load_project_memory(workspace_path) if is_new_project_dialog else ""
    merged_messages, conversation_summary = _prepare_conversation(
        user_id=user_id,
        session_id=session_id,
        raw_messages=raw_messages,
        scope=conversation_scope,
        log_label="agent run",
    )
    query = get_latest_user_query(merged_messages)
    forced_retrieval = bool(getattr(payload, "use_retrieval", False) or getattr(payload, "document_ids", None) or getattr(payload, "document_id", None))
    command_cwd = resolve_command_cwd(workspace_path)

    run: Dict[str, Any] = {
        "run_id": run_id,
        "status": "planning",
        "mode": str(getattr(payload, "mode", "") or "plan_then_act"),
        "user_id": user_id,
        "session_id": session_id,
        "workspace_path": workspace_path,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "query": query,
        "plan": _initial_plan(),
        "operations": [],
        "events": [],
        "reply": "",
        "usage": {},
        "references": [],
        "planner": {},
        "project_memory_injected": bool(project_memory_text),
    }
    _save_run(run)

    def append_event(event_type: str, payload_data: Dict[str, Any]) -> str:
        event = {"type": event_type, "created_at": _now_iso(), **payload_data}
        if event_type == "delta":
            run["reply"] = str(run.get("reply", "")) + str(payload_data.get("delta", ""))
        else:
            run.setdefault("events", []).append(event)
        _save_run(run)
        return f"data: {json.dumps(payload_data, ensure_ascii=False)}\n\n"

    def emit_status(label: str, detail: str = "", kind: str = "activity") -> str:
        return append_event(
            "status",
            {"status": {"label": label, "detail": detail, "kind": kind, "created_at": _now_iso()}},
        )

    def emit_plan() -> str:
        return append_event("plan", {"plan": run["plan"]})

    def emit_operation(operation: Dict[str, Any]) -> str:
        operation = {"created_at": _now_iso(), **operation}
        run.setdefault("operations", []).append(operation)
        return append_event("operation", {"operation": operation})

    def event_gen() -> Iterator[str]:
        try:
            run["status"] = "running"
            _update_plan_step(run["plan"], "保存任务状态", "running")
            yield append_event("run", {"run": {k: run[k] for k in ("run_id", "status", "created_at", "updated_at")}})
            yield emit_plan()
            yield emit_status("已自动保存任务状态", run_id, "state")
            _update_plan_step(run["plan"], "保存任务状态", "done")
            yield emit_plan()

            _update_plan_step(run["plan"], "让模型拆解", "running")
            yield emit_plan()
            yield emit_status("正在让模型 reshape 输入并拆解任务", kind="planner")
            try:
                planner = reshape_agent_request(
                    query=query,
                    merged_messages=merged_messages,
                    workspace_path=workspace_path,
                    forced_retrieval=forced_retrieval,
                    project_memory_text=project_memory_text,
                )
            except Exception as exc:
                logging.warning("agent reshape failed: %s", exc)
                planner = _normalize_planner({}, forced_retrieval=forced_retrieval)
            run["planner"] = planner
            run["plan"] = _plan_from_planner(planner)
            if run["plan"]:
                run["plan"][0]["status"] = "running"
            yield emit_plan()
            if planner.get("summary"):
                yield emit_status("模型已完成任务拆解", str(planner.get("summary")), "planner")
            else:
                yield emit_status("模型已完成任务拆解", kind="planner")

            retrieved_chunks: List[Dict[str, object]] = []
            web_results: List[Dict[str, object]] = []
            recall_ctx = ""
            web_context = ""
            command_contexts: List[str] = []
            retrieval_query = query
            effective_use_retrieval = bool(planner.get("needs_retrieval"))
            effective_use_web = bool(planner.get("needs_web"))
            terminal_actions = [
                action for action in planner.get("actions", [])
                if isinstance(action, dict)
                and str(action.get("type") or "").lower() == "terminal"
                and str(action.get("command") or "").strip()
            ]

            if effective_use_retrieval or effective_use_web:
                yield emit_status("正在改写检索查询", kind="search")
                try:
                    retrieval_query = rewrite_retrieval_query(query, merged_messages)
                except Exception as exc:
                    logging.warning("agent query rewrite failed: %s", exc)

            if effective_use_retrieval:
                _update_plan_step(run["plan"], "检索项目资料", "running")
                yield emit_plan()
                yield emit_status("正在检索项目资料", retrieval_query, "retrieval")
                try:
                    eff_doc_ids = (
                        list(getattr(payload, "document_ids", None) or [])
                        or ([getattr(payload, "document_id", None)] if getattr(payload, "document_id", None) else [])
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
                            document_id=getattr(payload, "document_id", None),
                            top_k=20,
                            candidate_limit=2000,
                        )
                    recall_ctx = build_retrieval_context(retrieved_chunks)
                    yield emit_status(f"找到 {len(retrieved_chunks)} 条项目资料片段", kind="retrieval")
                    _update_plan_step(run["plan"], "检索项目资料", "done")
                    yield emit_plan()
                except Exception as exc:
                    _update_plan_step(run["plan"], "检索项目资料", "done")
                    yield emit_status("项目资料检索失败，继续回答", str(exc), "warning")

            if effective_use_web:
                _update_plan_step(run["plan"], "查找网上资料", "running")
                yield emit_plan()
                yield emit_status("正在查找网上资料", retrieval_query, "web")
                try:
                    web_results = web_search(retrieval_query, top_k=5)
                    web_context = build_web_context(web_results)
                    yield emit_status(f"找到 {len(web_results)} 条网页结果", kind="web")
                    _update_plan_step(run["plan"], "查找网上资料", "done")
                    yield emit_plan()
                except Exception as exc:
                    _update_plan_step(run["plan"], "查找网上资料", "done")
                    yield emit_status("网上资料查找失败，继续回答", str(exc), "warning")

            for action in terminal_actions:
                command_text = str(action.get("command") or "").strip()
                if not command_text:
                    continue
                if not command_cwd:
                    yield emit_operation(
                        {
                            "id": f"op-{len(run['operations']) + 1}",
                            "type": "terminal",
                            "title": command_text,
                            "command": command_text,
                            "cwd": workspace_path,
                            "status": "failed",
                            "stderr": "当前项目没有可用根目录，无法执行终端动作。",
                        }
                    )
                    continue
                if bool(action.get("interactive")):
                    yield emit_status("正在打开可见终端并输入模型规划的命令", command_text, "terminal")
                    command_contexts.append(
                        "【命令行执行结果】\n"
                        f"cwd: {command_cwd}\n"
                        f"command: {command_text}\n"
                        "status: interactive terminal requested\n"
                        "说明：这是交互式命令，已交给前端可见终端执行。"
                    )
                    yield emit_operation(
                        {
                            "id": f"op-{len(run['operations']) + 1}",
                            "type": "terminal_interactive",
                            "title": command_text,
                            "command": command_text,
                            "cwd": str(command_cwd),
                            "status": "requested",
                            "stdout": str(action.get("reason") or "已请求在可见 PowerShell 终端中启动该命令。"),
                            "stderr": "",
                        }
                    )
                else:
                    yield emit_status("正在执行模型规划的终端命令", command_text, "terminal")
                    result = run_agent_command(command_text, command_cwd)
                    command_contexts.append(build_command_context(result))
                    yield emit_operation(
                        {
                            "id": f"op-{len(run['operations']) + 1}",
                            "type": "terminal",
                            "title": command_text,
                            "command": command_text,
                            "cwd": str(command_cwd),
                            "status": "done" if result.get("ok") else "failed",
                            "exit_code": result.get("returncode"),
                            "stdout": result.get("stdout") or "",
                            "stderr": result.get("stderr") or result.get("error") or "",
                        }
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
            run["references"] = references
            command_context = "\n\n".join(x for x in command_contexts if x.strip())

            final_messages = build_final_messages(
                merged_messages,
                conversation_summary=conversation_summary,
                memory_text="",
                query=query,
                recall_ctx=recall_ctx,
                web_context=web_context,
                command_context=command_context,
                project_memory_text=project_memory_text,
            )
            final_messages.insert(1, {"role": "system", "content": _planner_context(planner)})
            _update_plan_step(run["plan"], "生成回答", "running")
            yield emit_plan()
            yield emit_status("正在生成回答", kind="model")

            final_generation = {
                "max_tokens": max(settings.max_new_tokens, 1600),
                "temperature": settings.temperature,
                "top_p": settings.top_p,
            }
            usage: Dict[str, Any] = {}
            reply_chunks: List[str] = []
            image_url = str(getattr(payload, "image_url", "") or "")
            audio_url = str(getattr(payload, "audio_url", "") or "")
            if image_url or audio_url:
                result = smart_model_dispatch({
                    "messages": final_messages,
                    "image_url": image_url,
                    "audio_url": audio_url,
                })
                reply_text = str(result.get("reply", "") or "")
                reply_chunks = [reply_text]
                usage = dict(result.get("usage") or {})
                run["reply"] = reply_text
                run["usage"] = usage
                if reply_text:
                    yield append_event("delta", {"delta": reply_text})
                if usage:
                    yield append_event("usage", {"usage": usage})
            else:
                try:
                    for event in remote_stream_events(final_messages, generation=final_generation):
                        if event.get("type") == "usage":
                            usage = dict(event.get("usage") or {})
                            run["usage"] = usage
                            yield append_event("usage", {"usage": usage})
                            continue
                        raw_delta = event.get("delta", "")
                        if raw_delta is None:
                            continue
                        delta = str(raw_delta)
                        if delta:
                            reply_chunks.append(delta)
                            yield append_event("delta", {"delta": delta})
                except Exception as exc:
                    logging.warning("agent run stream failed, fallback to non-stream: %s", exc)
                    fallback = smart_model_dispatch({"messages": final_messages, "generation": final_generation})
                    fallback_reply = str(fallback.get("reply", "") or "")
                    reply_chunks = [fallback_reply]
                    usage = dict(fallback.get("usage") or {})
                    run["reply"] = fallback_reply
                    run["usage"] = usage
                    if fallback_reply:
                        yield append_event("delta", {"delta": fallback_reply})

            reply = "".join(reply_chunks).strip()
            run["reply"] = reply
            code_operations = _extract_code_operations(reply, start_index=len(run["operations"]) + 1)
            for operation in code_operations:
                yield emit_operation(operation)

            _set_plan_status(run["plan"], "done")
            run["status"] = "done"
            latency_ms = int((time.time() - start) * 1000)
            assistant_message = {
                "role": "assistant",
                "content": reply,
                "refs": references,
                "metadata": {
                    "usage": usage,
                    "model": settings.remote_primary_model,
                    "agent_run_id": run_id,
                    "plan": run["plan"],
                    "operations": run["operations"],
                },
                "created_at": _now_iso(),
            }
            merged_messages.append(assistant_message)
            save_conversation(
                user_id,
                session_id,
                merged_messages,
                scope=conversation_scope,
                limit=CHAT_HISTORY_MAX,
                compressed_summary=conversation_summary,
            )
            schedule_project_memory_update(
                workspace_path,
                query=query,
                reply=reply,
                plan=run["plan"],
                operations=run["operations"],
            )
            _save_run(run)
            yield append_event(
                "done",
                {
                    "done": True,
                    "reply": reply,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "reference": references,
                    "model": settings.remote_primary_model,
                    "run": {k: run[k] for k in ("run_id", "status", "created_at", "updated_at")},
                    "plan": run["plan"],
                    "operations": run["operations"],
                },
            )
        except Exception as exc:
            run["status"] = "failed"
            _save_run(run)
            yield append_event("error", {"error": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
