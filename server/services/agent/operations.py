from __future__ import annotations

import re
from typing import Any, Dict, List

from server.services.agent.state import _now_iso

CODE_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+.-]*)\s*\n([\s\S]*?)```", re.MULTILINE)


def _extract_code_operations(reply: str, start_index: int = 1) -> List[Dict[str, Any]]:
    operations: List[Dict[str, Any]] = []
    for match in CODE_FENCE_RE.finditer(reply or ""):
        code = match.group(2).strip("\n")
        if not code.strip():
            continue
        language = (match.group(1) or "text").strip() or "text"
        operations.append(
            {
                "id": f"op-{start_index + len(operations)}",
                "type": "code",
                "title": f"代码片段 · {language}",
                "language": language,
                "code": code[:24000],
                "status": "done",
                "created_at": _now_iso(),
            }
        )
        if len(operations) >= 8:
            break
    return operations
