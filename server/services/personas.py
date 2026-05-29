from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Dict, List


PERSONA_DIR = Path(os.getenv("PERSONA_DIR", "data/personas"))
_LOCK = threading.RLock()

DEFAULT_PERSONA_MARKDOWNS = {
    "温和陪伴": (
        "# 温和陪伴\n\n"
        "你是一个稳定、温和、低压的陪伴型 AI。先接住用户的情绪，"
        "再用简短、自然的话继续对话。不要说教，不要突然切换人格，"
        "不要编造自己做过的事。\n"
    ),
    "代码搭子": (
        "# 代码搭子\n\n"
        "你是用户的本地编码搭子。回答要直接、清楚、能落地。"
        "遇到复杂任务时先给任务列表，再逐步推进；不确定时先说明不确定点。\n"
    ),
    "苏格拉底提问": (
        "# 苏格拉底提问\n\n"
        "你通过温和的问题帮助用户澄清想法。每次最多问一到两个关键问题，"
        "必要时给一个小结，不要审问式连环追问。\n"
    ),
}


def _clean_persona_name(value: object, fallback: str = "新建人设") -> str:
    raw = str(value or "").strip()
    if raw.lower().endswith(".md"):
        raw = raw[:-3].strip()
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw).strip(" .")
    return raw[:80] or fallback


def _persona_path_from_name(name: str) -> Path:
    PERSONA_DIR.mkdir(parents=True, exist_ok=True)
    return PERSONA_DIR / f"{_clean_persona_name(name)}.md"


def ensure_persona_dir() -> Path:
    PERSONA_DIR.mkdir(parents=True, exist_ok=True)
    if not any(PERSONA_DIR.glob("*.md")):
        with _LOCK:
            if not any(PERSONA_DIR.glob("*.md")):
                for name, content in DEFAULT_PERSONA_MARKDOWNS.items():
                    _persona_path_from_name(name).write_text(content, encoding="utf-8")
    return PERSONA_DIR


def _persona_item(path: Path, *, include_content: bool = True) -> Dict[str, object]:
    stat = path.stat()
    return {
        "id": path.stem,
        "name": path.stem,
        "content": path.read_text(encoding="utf-8") if include_content else "",
        "path": str(path),
        "updated_at": stat.st_mtime,
    }


def list_personas() -> List[Dict[str, object]]:
    root = ensure_persona_dir()
    with _LOCK:
        return [
            _persona_item(path)
            for path in sorted(root.glob("*.md"), key=lambda p: p.stem.lower())
            if path.is_file()
        ]


def save_persona_markdown(name: str, content: str) -> Dict[str, object]:
    root = ensure_persona_dir()
    base = _clean_persona_name(name)
    path = root / f"{base}.md"
    if path.exists():
        idx = 2
        while True:
            candidate = root / f"{base}-{idx}.md"
            if not candidate.exists():
                path = candidate
                break
            idx += 1

    text = str(content or "").strip()
    if not text:
        text = f"# {path.stem}\n\n写下这个 agent 的人设、语气、边界和工作方式。\n"
    with _LOCK:
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        return _persona_item(path)
