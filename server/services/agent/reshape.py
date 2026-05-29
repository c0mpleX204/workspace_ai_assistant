from __future__ import annotations

import json
from typing import Any, Dict, List

from server.config.config import settings
from server.services.ai.model import smart_model_dispatch

PLAN_TASKS_TOOL = {
    "type": "function",
    "function": {
        "name": "plan_tasks",
        "description": "分析用户请求并生成任务计划。当用户要求执行操作、检索资料或需要联网时调用。如果用户只是闲聊或简单概念问题，也可以直接回答而不调用此函数。",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "一句话概括用户的真实目标和意图",
                },
                "needs_retrieval": {
                    "type": "boolean",
                    "description": "是否需要检索本地项目资料或课程资料来回答用户问题",
                },
                "needs_web": {
                    "type": "boolean",
                    "description": "是否需要联网搜索来获取最新信息（如价格、新闻、版本、天气等）",
                },
                "tasks": {
                    "type": "array",
                    "description": "任务拆解步骤列表，用中文描述",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "一个小而可执行的步骤，用中文",
                            },
                        },
                        "required": ["title"],
                    },
                },
                "actions": {
                    "type": "array",
                    "description": "需要执行的终端命令列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "const": "terminal",
                            },
                            "command": {
                                "type": "string",
                                "description": "要在 PowerShell 项目根目录执行的命令",
                            },
                            "interactive": {
                                "type": "boolean",
                                "description": "命令是否需要用户持续交互（如 REPL、TUI、长期运行的服务）",
                            },
                            "reason": {
                                "type": "string",
                                "description": "为什么需要这个命令",
                            },
                        },
                        "required": ["type", "command"],
                    },
                },
            },
            "required": ["summary", "needs_retrieval", "needs_web", "tasks"],
        },
    },
}


def _extract_tool_args(result: dict) -> Dict[str, Any]:
    """Extract function arguments from a model response that may contain tool_calls."""
    tool_calls = result.get("tool_calls") or []
    if tool_calls:
        tc = tool_calls[0]
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            args_str = str(fn.get("arguments") or "{}")
            try:
                return json.loads(args_str)
            except Exception:
                pass

    reply = str(result.get("reply") or "").strip()
    if reply:
        import re
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", reply, flags=re.IGNORECASE)
        if fenced:
            reply = fenced.group(1).strip()
        if not reply.startswith("{"):
            start = reply.find("{")
            end = reply.rfind("}")
            if start >= 0 and end > start:
                reply = reply[start:end + 1]
        try:
            data = json.loads(reply)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {}


def _normalize_planner(planner: Dict[str, Any], *, forced_retrieval: bool) -> Dict[str, Any]:
    summary = str(planner.get("summary") or "").strip()
    tasks_raw = planner.get("tasks") if isinstance(planner.get("tasks"), list) else []
    tasks: List[Dict[str, str]] = []
    for item in tasks_raw[:12]:
        title = ""
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("task") or "").strip()
        else:
            title = str(item or "").strip()
        if title:
            tasks.append({"title": title})
    if not tasks:
        tasks = [{"title": "理解用户请求并生成回答"}]

    actions_raw = planner.get("actions") if isinstance(planner.get("actions"), list) else []
    actions: List[Dict[str, Any]] = []
    for item in actions_raw[:8]:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type") or "").strip().lower()
        if action_type != "terminal":
            continue
        command = str(item.get("command") or "").strip()
        if not command:
            continue
        actions.append(
            {
                "type": "terminal",
                "command": command,
                "interactive": bool(item.get("interactive")),
                "reason": str(item.get("reason") or "").strip(),
            }
        )

    return {
        "summary": summary,
        "needs_retrieval": bool(planner.get("needs_retrieval") or forced_retrieval),
        "needs_web": bool(planner.get("needs_web")),
        "tasks": tasks,
        "actions": actions,
    }


def reshape_agent_request(
    *,
    query: str,
    merged_messages: List[Dict[str, str]],
    workspace_path: str,
    forced_retrieval: bool,
    project_memory_text: str = "",
    function_calling_enabled: bool | None = None,
) -> Dict[str, Any]:
    recent = [
        {"role": str(m.get("role", "")), "content": str(m.get("content", ""))[:1200]}
        for m in merged_messages[-8:]
        if str(m.get("role", "")) in {"user", "assistant"} and str(m.get("content", "")).strip()
    ]

    user_content = json.dumps(
        {
            "workspace_path": workspace_path,
            "forced_retrieval": forced_retrieval,
            "latest_user_input": query,
            "recent_dialogue": recent,
            "project_memory": str(project_memory_text or "")[:2500],
        },
        ensure_ascii=False,
    )

    use_function_calling = (
        function_calling_enabled
        if function_calling_enabled is not None
        else getattr(settings, "function_calling_enabled", False)
    )

    if use_function_calling:
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "user", "content": user_content},
                ],
                "model": settings.remote_fast_model,
                "generation": {
                    "max_tokens": 900,
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
                "tools": [PLAN_TASKS_TOOL],
            }
        )
        parsed = _extract_tool_args(result)
    else:
        AGENT_RESHAPE_SYSTEM_PROMPT = (
            "你是一个本地 IDE agent 的任务拆解器。你的任务不是回答用户，而是把用户输入 reshape 成 runtime 可执行的 JSON。\n\n"
            "只输出 JSON，不要输出 Markdown，不要解释。\n\n"
            'JSON schema: {"summary": "一句话概括用户真实目标", "needs_retrieval": true/false, "needs_web": true/false, '
            '"tasks": [{"title": "一个小而可执行的步骤"}], '
            '"actions": [{"type": "terminal", "command": "命令", "interactive": true/false, "reason": "为什么需要这个命令"}]}\n\n'
            "规则: 如果用户要求启动、打开、运行、测试、构建、安装等，生成 terminal action。"
            "如果命令会进入 REPL/TUI/长期运行服务，interactive=true。"
            "如果用户只是问概念问题，不要生成 terminal action。"
            "如果需最新信息/价格/版本/新闻，needs_web=true。"
            "如果用户选中了项目资料或请求基于本地资料分析，needs_retrieval=true。"
        )
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "system", "content": AGENT_RESHAPE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "model": settings.remote_fast_model,
                "generation": {
                    "max_tokens": 900,
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
            }
        )
        parsed = _extract_tool_args(result)

    return _normalize_planner(parsed, forced_retrieval=forced_retrieval)
