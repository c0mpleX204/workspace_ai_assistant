from __future__ import annotations

import os
from typing import Dict, List, Tuple

from server.config.config import settings
from server.services.model_service import smart_model_dispatch


SUMMARY_TRIGGER_MESSAGES = int(os.getenv("CHAT_SUMMARY_TRIGGER_MESSAGES", "18"))
SUMMARY_KEEP_RECENT = int(os.getenv("CHAT_SUMMARY_KEEP_RECENT", "10"))
SUMMARY_MAX_CHARS = int(os.getenv("CHAT_SUMMARY_MAX_CHARS", "1200"))


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
    trigger = max(8, SUMMARY_TRIGGER_MESSAGES)
    keep_recent = max(4, SUMMARY_KEEP_RECENT)
    if len(dialog) <= trigger:
        return dialog, previous_summary, False

    old_part = dialog[:-keep_recent]
    recent_part = dialog[-keep_recent:]
    if not old_part:
        return dialog, previous_summary, False

    old_part = old_part[-18:]
    summary_system = (
        "You are a conversation memory compressor. Update the existing summary "
        "with stable user preferences, goals, project context, unresolved questions, "
        "and important decisions. Keep it concise. Output only the updated summary."
    )
    summary_user = (
        "Existing summary:\n"
        f"{previous_summary or 'None'}\n\n"
        "Older dialogue to merge:\n"
        f"{plain_dialog(old_part)}\n\n"
        "Return the updated summary."
    )

    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": summary_user},
                ],
                "model": settings.remote_fast_model,
                "generation": {
                    "max_tokens": 360,
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

    max_chars = max(300, SUMMARY_MAX_CHARS)
    return recent_part, new_summary[:max_chars], True
