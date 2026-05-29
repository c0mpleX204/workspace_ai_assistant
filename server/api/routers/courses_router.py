import shutil
from pathlib import Path
from typing import Dict
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from server.infra.repo import (
    create_course,
    delete_course,
    get_course,
    list_courses,
    list_documents,
    update_course,
)
from server.api.schemas import (
    CourseCreateRequest,
    CourseItem,
    CourseListResponse,
    CourseUpdateRequest,
    MaterialItem,
    MaterialListResponse,
    WorkspaceDeleteResponse,
    WorkspaceDirectoryCreateRequest,
    WorkspaceFileCreateRequest,
    WorkspaceFileItem,
    WorkspaceFileResponse,
    WorkspaceFileSaveRequest,
    WorkspaceFileSaveResponse,
    WorkspaceRenameRequest,
    WorkspaceTreeResponse,
)
from server.services.project.workspace import ensure_course_workspace
from server.services.project.memory import PROJECT_MEMORY_FILENAME

router = APIRouter(tags=["courses"])

TEXT_READ_LIMIT = 2 * 1024 * 1024
TREE_DEPTH_LIMIT = 8
TREE_ITEM_LIMIT = 1200
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16-le", "utf-16-be")
IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".cache",
}
IGNORED_FILES = {
    PROJECT_MEMORY_FILENAME,
}


def _with_project_path(raw: Dict[str, object]) -> Dict[str, object]:
    course_id = int(raw["course_id"])
    name = str(raw["name"])
    return {**raw, "project_path": str(ensure_course_workspace(course_id, name))}


def _workspace_for_course(course_id: int) -> Path:
    raw = get_course(course_id)
    if not raw:
        raise HTTPException(status_code=404, detail="课程不存在")
    return ensure_course_workspace(course_id, str(raw["name"])).resolve()


def _resolve_workspace_file(root: Path, raw_path: str) -> Path:
    rel = unquote(str(raw_path or "")).replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件路径越界")
    return target


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    if b"\x00" in sample:
        for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                data.decode(encoding)
                return False
            except UnicodeDecodeError:
                continue
        return True
    control = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return control / max(len(sample), 1) > 0.08


def _decode_text(data: bytes) -> tuple[str, str]:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=415, detail="不是可识别的文本文件")


def _build_workspace_tree(root: Path) -> list[WorkspaceFileItem]:
    count = 0

    def walk(path: Path, depth: int) -> WorkspaceFileItem | None:
        nonlocal count
        if count >= TREE_ITEM_LIMIT:
            return None
        try:
            stat = path.stat()
        except OSError:
            return None

        rel = "" if path == root else _relative_path(root, path)
        if path.is_dir():
            if path != root and path.name in IGNORED_DIRS:
                return None
            count += 1
            children: list[WorkspaceFileItem] = []
            if depth < TREE_DEPTH_LIMIT:
                try:
                    entries = sorted(
                        path.iterdir(),
                        key=lambda p: (not p.is_dir(), p.name.lower()),
                    )
                except OSError:
                    entries = []
                for child in entries:
                    item = walk(child, depth + 1)
                    if item is not None:
                        children.append(item)
                    if count >= TREE_ITEM_LIMIT:
                        break
            return WorkspaceFileItem(
                name=path.name or root.name,
                path=rel,
                type="directory",
                size=0,
                modified_at=stat.st_mtime,
                children=children,
            )

        count += 1
        if path.name in IGNORED_FILES:
            return None
        return WorkspaceFileItem(
            name=path.name,
            path=rel,
            type="file",
            size=stat.st_size,
            modified_at=stat.st_mtime,
            children=[],
        )

    result: list[WorkspaceFileItem] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        entries = []
    for entry in entries:
        item = walk(entry, 1)
        if item is not None:
            result.append(item)
        if count >= TREE_ITEM_LIMIT:
            break
    return result


@router.post("/courses", response_model=CourseItem)
def api_create_course(payload: CourseCreateRequest) -> CourseItem:
    try:
        cid = create_course(name=payload.name, term=payload.term, owner_id=payload.owner_id)
        raw = get_course(cid)
        return CourseItem(**_with_project_path(raw))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鍒涘缓璇剧▼澶辫触: {exc}")


@router.get("/courses", response_model=CourseListResponse)
def api_list_courses(owner_id: str = "default_user", limit: int = 50, offset: int = 0) -> CourseListResponse:
    try:
        items_raw = list_courses(owner_id=owner_id, limit=limit, offset=offset)
        items = [CourseItem(**_with_project_path(r)) for r in items_raw]
        return CourseListResponse(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鑾峰彇璇剧▼鍒楄〃澶辫触: {exc}")


@router.get("/courses/{course_id}", response_model=CourseItem)
def api_get_course(course_id: int) -> CourseItem:
    try:
        raw = get_course(course_id)
        if not raw:
            raise HTTPException(status_code=404, detail="课程不存在")
        return CourseItem(**_with_project_path(raw))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鑾峰彇璇剧▼璇︽儏澶辫触: {exc}")


@router.put("/courses/{course_id}", response_model=CourseItem)
def api_update_course(course_id: int, payload: CourseUpdateRequest) -> CourseItem:
    try:
        update_course(course_id, name=payload.name, term=payload.term)
        raw = get_course(course_id)
        if not raw:
            raise HTTPException(status_code=404, detail="课程不存在")
        return CourseItem(**_with_project_path(raw))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鏇存柊璇剧▼澶辫触: {exc}")


@router.delete("/courses/{course_id}")
def api_delete_course(course_id: int) -> Dict[str, object]:
    try:
        ok = delete_course(course_id)
        if not ok:
            raise HTTPException(status_code=404, detail="课程不存在")
        return {"ok": True, "course_id": course_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鍒犻櫎璇剧▼澶辫触: {exc}")


@router.get("/courses/{course_id}/materials", response_model=MaterialListResponse)
def list_course_materials(course_id: int, limit: int = 50, offset: int = 0) -> MaterialListResponse:
    try:
        items_raw = list_documents(course_id=course_id, limit=limit, offset=offset)
        items = [
            MaterialItem(
                document_id=int(x["document_id"]),
                course_id=int(x["course_id"]),
                title=str(x["title"]),
                file_type=str(x["file_type"]),
                source_path=str(x["source_path"]),
                created_at=str(x["created_at"]) if x.get("created_at") else None,
                chunk_count=int(x.get("chunk_count", 0)),
            )
            for x in items_raw
        ]
        return MaterialListResponse(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"鑾峰彇璇剧▼璧勬枡澶辫触: {exc}")


@router.get("/courses/{course_id}/workspace/tree", response_model=WorkspaceTreeResponse)
def api_workspace_tree(course_id: int) -> WorkspaceTreeResponse:
    root = _workspace_for_course(course_id)
    return WorkspaceTreeResponse(root=str(root), items=_build_workspace_tree(root))


@router.get("/courses/{course_id}/workspace/file", response_model=WorkspaceFileResponse)
def api_read_workspace_file(course_id: int, path: str) -> WorkspaceFileResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    stat = target.stat()
    if stat.st_size > TEXT_READ_LIMIT:
        raise HTTPException(status_code=413, detail="文件过大，暂不在编辑器中打开")

    data = target.read_bytes()
    if _looks_binary(data):
        raise HTTPException(status_code=415, detail="该文件不是文本文件")
    content, encoding = _decode_text(data)
    return WorkspaceFileResponse(
        path=_relative_path(root, target),
        name=target.name,
        content=content,
        encoding=encoding,
        size=stat.st_size,
        modified_at=stat.st_mtime,
    )


@router.get("/courses/{course_id}/workspace/file/raw")
def api_read_workspace_file_raw(course_id: int, path: str):
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(target))


@router.put("/courses/{course_id}/workspace/file", response_model=WorkspaceFileSaveResponse)
def api_save_workspace_file(course_id: int, payload: WorkspaceFileSaveRequest) -> WorkspaceFileSaveResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, payload.path)
    if target.exists() and not target.is_file():
        raise HTTPException(status_code=400, detail="目标路径不是文件")
    target.parent.mkdir(parents=True, exist_ok=True)

    encoding = payload.encoding if payload.encoding in TEXT_ENCODINGS else "utf-8"
    try:
        target.write_text(payload.content, encoding=encoding)
    except UnicodeEncodeError:
        target.write_text(payload.content, encoding="utf-8")

    stat = target.stat()
    return WorkspaceFileSaveResponse(
        ok=True,
        path=_relative_path(root, target),
        size=stat.st_size,
        modified_at=stat.st_mtime,
    )


@router.post("/courses/{course_id}/workspace/file", response_model=WorkspaceFileSaveResponse)
def api_create_workspace_file(course_id: int, payload: WorkspaceFileCreateRequest) -> WorkspaceFileSaveResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, payload.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="文件已存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    stat = target.stat()
    return WorkspaceFileSaveResponse(
        ok=True,
        path=_relative_path(root, target),
        size=stat.st_size,
        modified_at=stat.st_mtime,
    )


@router.post("/courses/{course_id}/workspace/directory", response_model=WorkspaceDeleteResponse)
def api_create_workspace_directory(course_id: int, payload: WorkspaceDirectoryCreateRequest) -> WorkspaceDeleteResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, payload.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="目录已存在")
    target.mkdir(parents=True, exist_ok=True)
    return WorkspaceDeleteResponse(ok=True, path=_relative_path(root, target))


@router.delete("/courses/{course_id}/workspace/file", response_model=WorkspaceDeleteResponse)
def api_delete_workspace_file(course_id: int, path: str) -> WorkspaceDeleteResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="路径不是文件")
    target.unlink()
    return WorkspaceDeleteResponse(ok=True, path=_relative_path(root, target))


@router.delete("/courses/{course_id}/workspace/directory", response_model=WorkspaceDeleteResponse)
def api_delete_workspace_directory(course_id: int, path: str, recursive: bool = False) -> WorkspaceDeleteResponse:
    root = _workspace_for_course(course_id)
    target = _resolve_workspace_file(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="目录不存在")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="路径不是目录")
    if recursive:
        shutil.rmtree(str(target))
    else:
        try:
            next(target.iterdir())
            raise HTTPException(status_code=400, detail="目录不为空，请使用 recursive=true")
        except StopIteration:
            pass
        target.rmdir()
    return WorkspaceDeleteResponse(ok=True, path=_relative_path(root, target))


@router.post("/courses/{course_id}/workspace/rename", response_model=WorkspaceDeleteResponse)
def api_rename_workspace_item(course_id: int, payload: WorkspaceRenameRequest) -> WorkspaceDeleteResponse:
    root = _workspace_for_course(course_id)
    source = _resolve_workspace_file(root, payload.source_path)
    target = _resolve_workspace_file(root, payload.target_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="源文件不存在")
    if target.exists():
        raise HTTPException(status_code=409, detail="目标路径已存在")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return WorkspaceDeleteResponse(ok=True, path=_relative_path(root, target))

