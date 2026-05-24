import os
import re
from pathlib import Path

from server.services.project.memory import ensure_project_memory_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACES_ROOT = Path(
    os.getenv("PROJECT_WORKSPACES_DIR", str(PROJECT_ROOT / "data" / "projects"))
)


def safe_path_name(name: str, fallback: str = "project") -> str:
    text = str(name or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text[:80] or fallback


def get_course_workspace_path(course_id: int, course_name: str) -> Path:
    safe_name = safe_path_name(course_name, fallback=f"course-{course_id}")
    return WORKSPACES_ROOT / f"{safe_name}-{int(course_id)}"


def ensure_course_workspace(course_id: int, course_name: str) -> Path:
    path = get_course_workspace_path(course_id, course_name)
    path.mkdir(parents=True, exist_ok=True)
    ensure_project_memory_file(path)
    return path


def unique_child_path(parent: Path, filename: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    raw_name = safe_path_name(Path(filename).stem, fallback="file")
    suffix = Path(filename).suffix.lower()
    candidate = parent / f"{raw_name}{suffix}"
    if not candidate.exists():
        return candidate

    idx = 2
    while True:
        candidate = parent / f"{raw_name}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1
