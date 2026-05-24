from __future__ import annotations

from typing import Any, Dict, List

from server.services.chat_service import _payload_messages


def _payload_to_messages(payload: Any) -> List[Dict[str, Any]]:
    try:
        return _payload_messages(payload)
    except Exception:
        result: List[Dict[str, Any]] = []
        for item in getattr(payload, "messages", []) or []:
            if hasattr(item, "model_dump"):
                result.append(item.model_dump())
            elif isinstance(item, dict):
                result.append(item)
        return result
