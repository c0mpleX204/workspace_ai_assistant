from __future__ import annotations

from typing import Any, Dict, List


def _initial_plan() -> List[Dict[str, Any]]:
    return [
        {"id": "1", "title": "保存任务状态", "status": "pending"},
        {"id": "2", "title": "让模型拆解请求并生成可执行计划", "status": "pending"},
        {"id": "3", "title": "按计划执行并生成回答", "status": "pending"},
    ]


def _update_plan_step(plan: List[Dict[str, Any]], title_contains: str, status: str) -> None:
    needle = title_contains.strip()
    for item in plan:
        if needle in str(item.get("title", "")):
            item["status"] = status
            return


def _set_plan_status(plan: List[Dict[str, Any]], status: str) -> None:
    for item in plan:
        item["status"] = status


def _plan_from_planner(planner: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for item in planner.get("tasks", [])[:12]:
        title = str(item.get("title") if isinstance(item, dict) else item).strip()
        if title:
            plan.append({"id": str(len(plan) + 1), "title": title, "status": "pending"})
    if not plan:
        plan = [{"id": "1", "title": "生成回答", "status": "pending"}]
    return plan


def _planner_context(planner: Dict[str, Any]) -> str:
    lines = ["【Agent任务拆解】"]
    if planner.get("summary"):
        lines.append(f"目标：{planner['summary']}")
    if planner.get("tasks"):
        lines.append("步骤：")
        for idx, item in enumerate(planner.get("tasks", []), 1):
            lines.append(f"{idx}. {item.get('title')}")
    if planner.get("actions"):
        lines.append("动作：")
        for idx, item in enumerate(planner.get("actions", []), 1):
            lines.append(
                f"{idx}. terminal command={item.get('command')} interactive={bool(item.get('interactive'))} reason={item.get('reason', '')}"
            )
    return "\n".join(lines).strip()
