from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from server.config.config import settings


@dataclass
class SubAgentTask:
    """A self-contained unit of work that a sub-agent can process independently."""

    id: str
    title: str
    prompt: str
    system_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def run_subagents_parallel(
    tasks: List[SubAgentTask],
    executor_fn: Callable[[SubAgentTask], Dict[str, Any]],
    max_workers: int | None = None,
    timeout_sec: float = 60.0,
) -> List[Dict[str, Any]]:
    """Execute multiple sub-agent tasks in parallel using a thread pool.

    Each task is dispatched to ``executor_fn(task)`` which should return a
    result dict with at least a ``"reply"`` key.  Results are collected in the
    order they complete and returned as a list.

    If a sub-agent fails, its error is logged and a fallback result is
    inserted so the orchestrator can continue.
    """
    if not tasks:
        return []

    workers = max_workers if max_workers is not None else getattr(settings, "subagent_max_workers", 4)
    workers = max(1, min(workers, len(tasks)))

    results: List[Dict[str, Any]] = []
    task_map: Dict[concurrent.futures.Future, int] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for idx, task in enumerate(tasks):
            future = executor.submit(executor_fn, task)
            task_map[future] = idx

        for future in concurrent.futures.as_completed(task_map, timeout=timeout_sec):
            idx = task_map[future]
            try:
                result = future.result()
                results.append({"index": idx, "task_id": tasks[idx].id, "ok": True, **result})
            except Exception as exc:
                logging.warning("sub-agent task %s (%s) failed: %s", tasks[idx].id, tasks[idx].title, exc)
                results.append({
                    "index": idx,
                    "task_id": tasks[idx].id,
                    "ok": False,
                    "error": str(exc),
                    "reply": "",
                })

    results.sort(key=lambda r: r["index"])
    return results


def build_subagent_context(
    query: str,
    persona_prompt: str = "",
    memory_text: str = "",
    max_chars: int = 3000,
) -> str:
    """Build a compact context block for a sub-agent prompt."""
    parts: List[str] = []
    if memory_text:
        parts.append(f"【记忆上下文】\n{str(memory_text)[:max_chars]}")
    parts.append(f"【用户问题】\n{str(query)[:max_chars]}")
    return "\n\n".join(parts)
