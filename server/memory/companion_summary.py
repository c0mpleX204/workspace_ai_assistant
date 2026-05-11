import os
from typing import Dict, List, Tuple

from server.memory.summary_utils import compact_dialog_with_model
from server.orchestration.companion_routing import FAST_MODEL


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


def compact_dialog(
    dialog: List[Dict[str, str]],
    previous_summary: str,
) -> Tuple[List[Dict[str, str]], str, bool]:
    trigger = max(6, SUM_TRIGGER)
    keep_recent = max(4, SUM_KEEP)
    summary_system = (
        "你是对话记忆压缩器。请把旧对话压缩成结构化摘要，"
        "包含：用户偏好、稳定事实、当前目标、情绪风格、未解决问题。"
        "只输出摘要正文，不要输出解释。"
    )
    return compact_dialog_with_model(
        dialog,
        previous_summary,
        trigger=trigger,
        keep_recent=keep_recent,
        old_limit=12,
        summary_system=summary_system,
        build_summary_user=lambda prev, old_dialog: (
            "已有摘要：\n"
            f"{prev or '无'}\n\n"
            "新增旧对话：\n"
            f"{old_dialog}\n\n"
            "请输出更新后的摘要。"
        ),
        model=FAST_MODEL,
        generation={
            "max_tokens": 260,
            "temperature": 0.2,
            "top_p": 0.9,
        },
        max_chars=max(200, SUM_CHAR_MAX),
    )
