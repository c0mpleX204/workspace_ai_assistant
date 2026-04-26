import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from server.documents.parser import parse_document
from server.infra.repo import (
    create_document,
    delete_doc_chunks,
    get_document_detail,
    insert_chunks,
    list_chunks_emb,
    list_documents,
)
from server.api.schemas import (
    MaterialDeleteResponse,
    MaterialDetail,
    MaterialItem,
    MaterialListResponse,
    SearchItem,
    SearchRequest,
    SearchResponse,
)
from server.services.embedding_service import embed_document_chunks, embed_text, rank_chunks

router = APIRouter(tags=["materials"])

UPLOAD_DIR = Path("data/upload")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _embed_chunks_async(document_id: int) -> None:
    try:
        embed_document_chunks(document_id=document_id)
    except Exception:
        pass


@router.post("/materials/upload")
async def upload_material(
    course_id: int = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, object]:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".txt", ".pdf"]:
        raise HTTPException(status_code=400, detail="仅支持 txt/pdf")

    save_name = f"{uuid.uuid4().hex}{suffix}"
    save_path = UPLOAD_DIR / save_name

    try:
        data = await file.read()
        save_path.write_bytes(data)

        file_type, chunks = parse_document(str(save_path), chunk_size=600, overlap=80)
        document_id = create_document(
            course_id=course_id,
            title=title,
            file_type=file_type,
            source_path=str(save_path),
        )
        chunk_count = insert_chunks(document_id, chunks)
        threading.Thread(target=_embed_chunks_async, args=(document_id,), daemon=True).start()

        return {
            "document_id": document_id,
            "file_type": file_type,
            "chunk_count": chunk_count,
            "source_path": str(save_path),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传解析失败: {exc}")


@router.get("/materials", response_model=MaterialListResponse)
def list_materials(
    course_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
) -> MaterialListResponse:
    try:
        items_raw = list_documents(course_id=course_id, limit=limit, offset=offset)
        items: List[MaterialItem] = []
        for x in items_raw:
            created_at = x.get("created_at")
            items.append(
                MaterialItem(
                    document_id=int(x["document_id"]),
                    course_id=int(x["course_id"]),
                    title=str(x["title"]),
                    file_type=str(x["file_type"]),
                    source_path=str(x["source_path"]),
                    created_at=str(created_at) if created_at is not None else None,
                    chunk_count=int(x.get("chunk_count", 0)),
                )
            )
        return MaterialListResponse(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取资料列表失败: {exc}")


@router.get("/materials/{document_id}", response_model=MaterialDetail)
def get_material(document_id: int) -> MaterialDetail:
    try:
        raw = get_document_detail(document_id)
        if not raw:
            raise HTTPException(status_code=404, detail="资料不存在")
        created_at = raw.get("created_at")
        item = MaterialItem(
            document_id=int(raw["document_id"]),
            course_id=int(raw["course_id"]),
            title=str(raw["title"]),
            file_type=str(raw["file_type"]),
            source_path=str(raw["source_path"]),
            created_at=str(created_at) if created_at is not None else None,
            chunk_count=int(raw.get("chunk_count", 0)),
        )
        return MaterialDetail(item=item)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取资料详情失败: {exc}")


@router.delete("/materials/{document_id}", response_model=MaterialDeleteResponse)
def delete_material(document_id: int) -> MaterialDeleteResponse:
    try:
        ok = delete_doc_chunks(document_id)
        if not ok:
            raise HTTPException(status_code=404, detail="资料不存在")
        return MaterialDeleteResponse(ok=True, document_id=document_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除资料失败: {exc}")


@router.get("/materials/{document_id}/view")
def api_view_material(document_id: int):
    try:
        raw = get_document_detail(document_id)
        if not raw:
            raise HTTPException(status_code=404, detail="资料不存在")
        file_path = Path(raw["source_path"])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        media_type = "application/pdf" if raw["file_type"] == "pdf" else "text/plain; charset=utf-8"
        return FileResponse(
            str(file_path),
            media_type=media_type,
            headers={"Content-Disposition": f"inline; filename={file_path.name}"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取文件失败: {exc}")


@router.post("/materials/search", response_model=SearchResponse)
def search_materials(payload: SearchRequest) -> SearchResponse:
    try:
        query_vec = embed_text(payload.query)
        candidates = list_chunks_emb(
            document_id=payload.document_id,
            limit=payload.candidate_limit,
        )
        if not candidates:
            return SearchResponse(results=[])

        ranked = rank_chunks(
            query_vec=query_vec,
            chunks=candidates,
            top_k=payload.top_k,
        )
        return SearchResponse(results=[SearchItem(**x) for x in ranked])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败: {exc}")

