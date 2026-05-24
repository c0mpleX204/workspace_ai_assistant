from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict
from uuid import uuid4

AGENT_RUN_DIR = Path("data/agent_runs")
AGENT_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_path(run_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(run_id or "").strip())[:120]
    if not safe:
        safe = uuid4().hex
    return AGENT_RUN_DIR / f"{safe}.json"


def _save_run(run: Dict[str, Any]) -> None:
    run["updated_at"] = _now_iso()
    _run_path(str(run["run_id"])).write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_agent_run(run_id: str) -> Dict[str, Any]:
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"agent run not found: {run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to read agent run: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("agent run state is invalid")
    return data
