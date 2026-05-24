import json
from pathlib import Path
from typing import Any, Dict, List


SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"


def list_installed_skills() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not SKILLS_ROOT.exists():
        return items

    for manifest in sorted(SKILLS_ROOT.glob("*/skill.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        items.append(
            {
                "id": str(data.get("id") or manifest.parent.name),
                "name": str(data.get("name") or manifest.parent.name),
                "description": str(data.get("description") or ""),
                "triggers": list(data.get("triggers") or []),
                "permissions": list(data.get("permissions") or []),
                "capabilities": list(data.get("capabilities") or []),
                "path": str(manifest.parent),
            }
        )
    return items

