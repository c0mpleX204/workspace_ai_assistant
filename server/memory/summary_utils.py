from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from server.services.ai.model import smart_model_dispatch


def plain_dialog(messages: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip().replace("\n", " ")
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def compact_dialog_with_model(
    dialog: List[Dict[str, str]],
    previous_summary: str,
    *,
    trigger: int,
    keep_recent: int,
    old_limit: int,
    summary_system: str,
    build_summary_user: Callable[[str, str], str],
    model: str,
    generation: Dict[str, object],
    max_chars: int,
) -> Tuple[List[Dict[str, str]], str, bool]:
    if len(dialog) <= trigger:
        return dialog, previous_summary, False

    old_part = dialog[:-keep_recent]
    recent_part = dialog[-keep_recent:]
    if not old_part:
        return dialog, previous_summary, False

    old_dialog = plain_dialog(old_part[-old_limit:])
    try:
        result = smart_model_dispatch(
            {
                "messages": [
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": build_summary_user(previous_summary, old_dialog)},
                ],
                "model": model,
                "generation": generation,
            }
        )
        new_summary = str(result.get("reply", "")).strip()
    except Exception:
        new_summary = previous_summary

    if not new_summary:
        return dialog, previous_summary, False

    return recent_part, new_summary[:max_chars], True
