from __future__ import annotations

import os
from typing import Dict, List, Tuple

from server.config.config import settings
from server.memory.summary_utils import compact_dialog_with_model


SUMMARY_TRIGGER_MESSAGES = int(os.getenv("CHAT_SUMMARY_TRIGGER_MESSAGES", "18"))
SUMMARY_KEEP_RECENT = int(os.getenv("CHAT_SUMMARY_KEEP_RECENT", "10"))
SUMMARY_MAX_CHARS = int(os.getenv("CHAT_SUMMARY_MAX_CHARS", "1200"))


def compact_dialog(
    dialog: List[Dict[str, str]],
    previous_summary: str,
) -> Tuple[List[Dict[str, str]], str, bool]:
    trigger = max(8, SUMMARY_TRIGGER_MESSAGES)
    keep_recent = max(4, SUMMARY_KEEP_RECENT)
    summary_system = (
        "You are a conversation memory compressor. Update the existing summary "
        "with stable user preferences, goals, project context, unresolved questions, "
        "and important decisions. Keep it concise. Output only the updated summary."
    )
    return compact_dialog_with_model(
        dialog,
        previous_summary,
        trigger=trigger,
        keep_recent=keep_recent,
        old_limit=18,
        summary_system=summary_system,
        build_summary_user=lambda prev, old_dialog: (
            "Existing summary:\n"
            f"{prev or 'None'}\n\n"
            "Older dialogue to merge:\n"
            f"{old_dialog}\n\n"
            "Return the updated summary."
        ),
        model=settings.remote_fast_model,
        generation={
            "max_tokens": 360,
            "temperature": 0.2,
            "top_p": 0.9,
        },
        max_chars=max(300, SUMMARY_MAX_CHARS),
    )
