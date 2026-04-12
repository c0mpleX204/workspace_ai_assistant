from typing import Dict

from fastapi import APIRouter, HTTPException

from infra.repo import (
    create_course,
    delete_course,
    get_course,
    list_courses,
    list_documents,
    update_course,
)
from api.routers.schemas import (
    CourseCreateRequest,
    CourseItem,
    CourseListResponse,
    CourseUpdateRequest,
    MaterialItem,
    MaterialListResponse,
)

router = APIRouter(tags=["courses"])


@router.post("/courses", response_model=CourseItem)
def api_create_course(payload: CourseCreateRequest) -> CourseItem:
    try:
        cid = create_course(name=payload.name, term=payload.term, owner_id=payload.owner_id)
        raw = get_course(cid)
        return CourseItem(**raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建课程失败: {exc}")


@router.get("/courses", response_model=CourseListResponse)
def api_list_courses(owner_id: str = "default_user", limit: int = 50, offset: int = 0) -> CourseListResponse:
    try:
        items_raw = list_courses(owner_id=owner_id, limit=limit, offset=offset)
        items = [CourseItem(**r) for r in items_raw]
        return CourseListResponse(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取课程列表失败: {exc}")


@router.get("/courses/{course_id}", response_model=CourseItem)
def api_get_course(course_id: int) -> CourseItem:
    try:
        raw = get_course(course_id)
        if not raw:
            raise HTTPException(status_code=404, detail="课程不存在")
        return CourseItem(**raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取课程详情失败: {exc}")


@router.put("/courses/{course_id}", response_model=CourseItem)
def api_update_course(course_id: int, payload: CourseUpdateRequest) -> CourseItem:
    try:
        update_course(course_id, name=payload.name, term=payload.term)
        raw = get_course(course_id)
        if not raw:
            raise HTTPException(status_code=404, detail="课程不存在")
        return CourseItem(**raw)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新课程失败: {exc}")


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
        raise HTTPException(status_code=500, detail=f"删除课程失败: {exc}")


@router.get("/courses/{course_id}/materials", response_model=MaterialListResponse)
def api_list_course_materials(course_id: int, limit: int = 50, offset: int = 0) -> MaterialListResponse:
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
        raise HTTPException(status_code=500, detail=f"获取课程资料失败: {exc}")
