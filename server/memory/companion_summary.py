import os
from typing import Dict, List, Tuple

from server.orchestration.companion_routing import FAST_MODEL
from server.services.model_service import smart_model_dispatch


LIGHT_MSG_MAX = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_MESSAGES", "8"))
LIGHT_CHAR_MAX = int(os.getenv("COMPANION_LIGHTWEIGHT_MAX_CHARS", "360"))
SYS_KEEP = int(os.getenv("COMPANION_SYSTEM_KEEP", "4"))
SUM_TRIGGER = int(os.getenv("COMPANION_SUMMARY_TRIGGER_MESSAGES", "14"))
SUM_KEEP = int(os.getenv("COMPANION_SUMMARY_KEEP_RECENT", "8"))
SUM_CHAR_MAX = int(os.getenv("COMPANION_SUMMARY_MAX_CHARS", "800"))


def compact_msgs(messages: List[Dict[str, object]]) -> List[Dict[str, object]]:
    max_count = max(2, LIGHT_MSG_MAX)
    max_chars = max(80, LIGHT_CHAR_MAX)
    max_system = max(1, SYS_KEEP)
    system_msgs = [m for m in messages if str(m.get("role", "")).strip() == "system"]
    dialog_msgs = [m for m in messages if str(m.get("role", "")).strip() != "system"]
    kept = dialog_msgs[-max_count:]
    compacted: List[Dict[str, object]] = []
    compacted.extend(system_msgs[:max_system])
    for msg in kept:
        content = str(msg.get("content", "")).strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        compacted.append({"role": msg.get("role", "user"), "content": content})
    return compacted


def plain_dialog(messages: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip().replace("\n", " ")
        if not role or not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def compact_dialog(
    dialog: List[Dict[str, str]],
    previous_summary: str,
) -> Tuple[List[Dict[str, str]], str, bool]:
    trigger = max(6, SUM_TRIGGER)
    keep_recent = max(4, SUM_KEEP)

    if len(dialog) <= trigger:
        return dialog, previous_summary, False

    old_part = dialog[:-keep_recent]
    recent_part = dialog[-keep_recent:]
    if not old_part:
        return dialog, previous_summary, False

    old_part = old_part[-12:]

    summary_system = (
        "你是对话记忆压缩器。请把旧对话压缩成结构化摘要，"
        "包含：用户偏好、稳定事实、当前目标、情绪风格、未解决问题。"
        "只输出摘要正文，不要输出解释。"
    )
    summary_user = (
        "已有摘要：\n"
        f"{previous_summary or '无'}\n\n"
        "新增旧对话：\n"
        f"{plain_dialog(old_part)}\n\n"
        "请输出更新后的摘要。"
    )

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": summary_user},
                ],
                "model": FAST_MODEL,
                "generation": {
                    "max_tokens": 260,
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
            }
        )
        new_summary = str(result.get("reply", "")).strip()
    except Exception:
        new_summary = previous_summary

    if not new_summary:
        return dialog, previous_summary, False

    max_chars = max(200, SUM_CHAR_MAX)
    return recent_part, new_summary[:max_chars], True
