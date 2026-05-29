from __future__ import annotations

from typing import Dict, List

from server.config.config import settings

def _insert_system_after_primary(
    messages: List[Dict[str, str]],
    system_msg: Dict[str, str],
    *,
    marker: str | None = None,
) -> List[Dict[str, str]]:
    if marker and any(
        m.get("role") == "system" and marker in str(m.get("content", ""))
        for m in messages
    ):
        return messages

    first_system_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
    if first_system_idx >= 0:
        return messages[: first_system_idx + 1] + [system_msg] + messages[first_system_idx + 1 :]
    return [system_msg] + messages

def inject_system_prompt(messages: List[Dict[str, str]], persona_prompt: str | None = None) -> List[Dict[str, str]]:
    prompt = str(persona_prompt or "").strip() or settings.persona_system_prompt
    persona = {"role": "system", "content": prompt}
    filtered = [
        m
        for m in messages
        if not (
            m.get("role") == "system"
            and m.get("content") in {settings.persona_system_prompt, prompt}
        )
    ]
    return [persona] + filtered
