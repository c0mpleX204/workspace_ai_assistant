import logging
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

from server.config.config import settings
from server.orchestration.companion_routing import FAST_MODEL
from server.services.model_service import smart_model_dispatch


HEAVY_MODEL = os.getenv("COMPANION_HEAVY_MODEL", settings.remote_primary_model).strip()
HEAVY_TOKEN_MAX = int(os.getenv("COMPANION_HEAVY_MAX_TOKENS", "900"))
HEAVY_ASYNC = os.getenv("COMPANION_HEAVY_ASYNC_ENABLED", "true").strip().lower() == "true"
WORKER_MAX = max(1, int(os.getenv("COMPANION_HEAVY_MAX_WORKERS", "2")))
QUEUE_MAX = max(
    WORKER_MAX,
    int(os.getenv("COMPANION_DELEGATED_QUEUE_MAX", "6")),
)
SESSION_ACTIVE_MAX = max(
    1,
    int(os.getenv("COMPANION_DELEGATED_SESSION_MAX_ACTIVE", "1")),
)
TASK_TTL_SEC = int(os.getenv("COMPANION_DELEGATED_TASK_TTL_SECONDS", "1800"))

_TASK_LOCK = threading.Lock()
_TASKS: Dict[str, Dict[str, Any]] = {}
_TASKS_BY_SESSION: Dict[str, list[str]] = {}
_TASK_POOL = ThreadPoolExecutor(
    max_workers=WORKER_MAX,
    thread_name_prefix="companion-heavy",
)
_FUTURES: Dict[str, Future] = {}


def run_heavy_task(task_input: str) -> Tuple[bool, str]:
    task_text = str(task_input or "").strip()
    if not task_text:
        return False, "任务输入为空，无法执行。"

    try:
        result = smart_model_dispatch(
            {
                "messages": [{"role": "user", "content": task_text}],
                "model": HEAVY_MODEL,
                "generation": {
                    "max_tokens": max(128, HEAVY_TOKEN_MAX),
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


def task_result_prompt(
    task_input: str,
    *,
    ok: bool,
    result_text: str,
) -> str:
    status_line = "执行状态：成功" if ok else "执行状态：失败"
    return (
        "你现在负责把主任务模型的执行结果，用当前人设口吻转述给用户。\n"
        "回复要求：\n"
        "1. 第一短句先说“稍等，我先处理一下这个任务”。\n"
        "2. 第二部分给出处理结果；若失败，简明说明失败原因和下一步建议。\n"
        "3. 保持角色语气，禁止编造未执行的动作。\n\n"
        f"用户原任务：\n{str(task_input or '').strip()}\n\n"
        f"{status_line}\n"
        f"主任务模型输出：\n{str(result_text or '').strip()[:2400]}"
    )


def task_session_key(user_id: str, session_id: str) -> str:
    return f"{(user_id or 'user1').strip()}::{(session_id or 'default').strip() or 'default'}"


def summarize_task(task_input: str, ok: bool, result_text: str) -> str:
    text = str(result_text or "").strip()
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
                            "最多3条要点，并包含下一步建议。只输出摘要正文。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"用户任务：{str(task_input or '').strip()}\n\n"
                            f"主任务结果：\n{text[:2600]}"
                        ),
                    },
                ],
                "model": FAST_MODEL,
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


def cleanup_expired_locked(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    expired_ids = [
        task_id
        for task_id, task in _TASKS.items()
        if float(task.get("expire_at", 0.0)) <= now
    ]
    if not expired_ids:
        return

    expired_set = set(expired_ids)
    for task_id in expired_ids:
        _TASKS.pop(task_id, None)
        future = _FUTURES.pop(task_id, None)
        if future is not None:
            future.cancel()

    for sess_key, task_ids in list(_TASKS_BY_SESSION.items()):
        kept = [tid for tid in task_ids if tid not in expired_set]
        if kept:
            _TASKS_BY_SESSION[sess_key] = kept
        else:
            _TASKS_BY_SESSION.pop(sess_key, None)


def run_delegated_task(task_id: str) -> None:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["updated_at"] = time.time()
        task_input = str(task.get("user_input", "")).strip()

    ok, raw_result = run_heavy_task(task_input)
    summary = summarize_task(task_input, ok, raw_result)
    now = time.time()

    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        if bool(task.get("cancel_requested", False)):
            task["status"] = "cancelled"
            task["ok"] = False
            task["result_raw"] = ""
            task["result_summary"] = "任务已取消。"
            task["completed_at"] = now
            task["updated_at"] = now
            return
        task["status"] = "completed" if ok else "failed"
        task["ok"] = bool(ok)
        task["result_raw"] = str(raw_result or "")
        task["result_summary"] = summary
        task["completed_at"] = now
        task["updated_at"] = now


def count_active_locked(sess_key: Optional[str] = None) -> int:
    active_statuses = {"queued", "running"}
    total = 0
    for task in _TASKS.values():
        if str(task.get("status", "")).lower() not in active_statuses:
            continue
        if sess_key and str(task.get("sess_key", "")) != sess_key:
            continue
        total += 1
    return total


def create_task(user_id: str, session_id: str, user_input: str) -> Dict[str, Any]:
    now = time.time()
    task_id = uuid.uuid4().hex
    sess_key = task_session_key(user_id, session_id)
    task: Dict[str, Any] = {
        "task_id": task_id,
        "user_id": user_id,
        "session_id": session_id,
        "sess_key": sess_key,
        "user_input": str(user_input or "").strip(),
        "status": "queued",
        "ok": None,
        "result_raw": "",
        "result_summary": "",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "delivered": False,
        "expire_at": now + max(120, TASK_TTL_SEC),
    }

    with _TASK_LOCK:
        cleanup_expired_locked(now)
        if count_active_locked() >= QUEUE_MAX:
            raise RuntimeError("delegated task queue is full")
        if count_active_locked(sess_key) >= SESSION_ACTIVE_MAX:
            raise RuntimeError("delegated task already running for this session")
        _TASKS[task_id] = task
        task_list = _TASKS_BY_SESSION.setdefault(sess_key, [])
        task_list.append(task_id)
        if len(task_list) > 20:
            _TASKS_BY_SESSION[sess_key] = task_list[-20:]
    return task


def fail_task(task_id: str, message: str) -> None:
    now = time.time()
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if not task:
            return
        if str(task.get("status", "")).lower() in {"completed", "failed", "cancelled"}:
            return
        task["status"] = "failed"
        task["ok"] = False
        task["result_raw"] = str(message or "")
        task["result_summary"] = str(message or "delegated task failed")
        task["completed_at"] = now
        task["updated_at"] = now


def on_task_done(task_id: str, future: Future) -> None:
    with _TASK_LOCK:
        _FUTURES.pop(task_id, None)

    if future.cancelled():
        fail_task(task_id, "delegated task was cancelled before it started")
        return

    try:
        exc = future.exception()
    except Exception as callback_exc:
        exc = callback_exc
    if exc is not None:
        fail_task(task_id, str(exc))


def start_task(task_id: str) -> None:
    try:
        future = _TASK_POOL.submit(run_delegated_task, task_id)
    except Exception as exc:
        fail_task(task_id, str(exc))
        raise RuntimeError(f"failed to start delegated task: {exc}") from exc

    with _TASK_LOCK:
        _FUTURES[task_id] = future
    future.add_done_callback(lambda done, tid=task_id: on_task_done(tid, done))


def shutdown_task_pool() -> None:
    with _TASK_LOCK:
        futures = list(_FUTURES.values())
        _FUTURES.clear()
    for future in futures:
        future.cancel()
    _TASK_POOL.shutdown(wait=False, cancel_futures=True)


def poll_task(user_id: str, session_id: str, task_id: str = "") -> Optional[Dict[str, Any]]:
    sess_key = task_session_key(user_id, session_id)
    now = time.time()
    wanted_id = str(task_id or "").strip()
    with _TASK_LOCK:
        cleanup_expired_locked(now)
        task_ids = list(_TASKS_BY_SESSION.get(sess_key, []))
        if not task_ids:
            return None

        if wanted_id:
            task = _TASKS.get(wanted_id)
            if not task or str(task.get("sess_key", "")) != sess_key:
                return None
            status = str(task.get("status", ""))
            return {
                "task_id": wanted_id,
                "status": status,
                "ok": task.get("ok"),
                "user_input": str(task.get("user_input", "")),
                "main_result": str(task.get("result_raw", "")),
                "summary": str(task.get("result_summary", "")),
                "completed_at": task.get("completed_at"),
            }

        for task_id in task_ids:
            task = _TASKS.get(task_id)
            if not task:
                continue
            status = str(task.get("status", ""))
            if status in {"completed", "failed", "cancelled"} and not bool(task.get("delivered", False)):
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

        for task_id in reversed(task_ids):
            task = _TASKS.get(task_id)
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


def cancel_task(user_id: str, session_id: str, task_id: str = "") -> Optional[Dict[str, Any]]:
    sess_key = task_session_key(user_id, session_id)
    wanted_id = str(task_id or "").strip()
    if not wanted_id:
        return None

    now = time.time()
    with _TASK_LOCK:
        cleanup_expired_locked(now)
        task = _TASKS.get(wanted_id)
        if not task or str(task.get("sess_key", "")) != sess_key:
            return None

        status = str(task.get("status", "")).lower()
        if status not in {"completed", "failed", "cancelled"}:
            task["cancel_requested"] = True
            future = _FUTURES.get(wanted_id)
            cancelled_before_start = bool(future.cancel()) if future is not None else False
            if status == "queued" or cancelled_before_start:
                task["status"] = "cancelled"
                task["ok"] = False
                task["result_raw"] = ""
                task["result_summary"] = "任务已取消。"
                task["completed_at"] = now
            task["updated_at"] = now

        return {
            "task_id": wanted_id,
            "status": str(task.get("status", "")),
            "ok": task.get("ok"),
            "user_input": str(task.get("user_input", "")),
            "main_result": str(task.get("result_raw", "")),
            "summary": str(task.get("result_summary", "")),
            "completed_at": task.get("completed_at"),
        }
