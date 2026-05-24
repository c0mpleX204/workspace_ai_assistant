from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from server.config.config import settings
from server.services.ai.model import smart_model_dispatch

AGENT_RESHAPE_SYSTEM_PROMPT = """
你是一个本地 IDE agent 的任务拆解器。你的任务不是回答用户，而是把用户输入 reshape 成 runtime 可执行的 JSON。

只输出 JSON，不要输出 Markdown，不要解释。

JSON schema:
{
  "summary": "一句话概括用户真实目标",
  "needs_retrieval": true/false,
  "needs_web": true/false,
  "tasks": [
    {"title": "一个小而可执行的步骤"}
  ],
  "actions": [
    {
      "type": "terminal",
      "command": "要在 PowerShell 项目根目录执行或启动的原始命令",
      "interactive": true/false,
      "reason": "为什么需要这个命令"
    }
  ]
}

规则:
- 如果用户要求启动、打开、运行、测试、构建、安装、查看版本、检查环境、调用 CLI 等，生成 terminal action。
- 如果命令会进入 REPL/TUI/需要用户继续输入/长期运行服务，interactive=true；如果是一次性命令，interactive=false。
- 如果用户只是问概念问题，不要生成 terminal action。
- 如果需要最新信息、网上资料、价格、版本、新闻、文档或外部来源，needs_web=true。
- 如果用户选择了项目资料/课程资料，或请求基于本地项目/资料分析，needs_retrieval=true。
- 大任务必须拆成多个小步骤，步骤用用户能看懂的中文。
- 不要臆造用户没有要求的危险命令。
""".strip()


def _json_from_model(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
) -> Dict[str, Any]:
    recent = [
        {"role": str(m.get("role", "")), "content": str(m.get("content", ""))[:1200]}
        for m in merged_messages[-8:]
        if str(m.get("role", "")) in {"user", "assistant"} and str(m.get("content", "")).strip()
    ]
    result = smart_model_dispatch(
        {
            "messages": [
                {"role": "system", "content": AGENT_RESHAPE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "workspace_path": workspace_path,
                            "forced_retrieval": forced_retrieval,
                            "latest_user_input": query,
                            "recent_dialogue": recent,
                            "project_memory": str(project_memory_text or "")[:2500],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "model": settings.remote_fast_model,
            "generation": {
                "max_tokens": 900,
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }
    )
    parsed = _json_from_model(str(result.get("reply") or ""))
    return _normalize_planner(parsed, forced_retrieval=forced_retrieval)
