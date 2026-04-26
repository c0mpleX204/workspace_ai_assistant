from typing import List, Literal, Optional

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from server.services.chat_service import create_chat_stream, handle_chat

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    user_id: str = "default_user"
    session_id: str = "default"
    messages: List[ChatMessage] = Field(min_length=1)
    use_retrieval: bool = False
    document_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    use_web_search: bool = False
    files: Optional[List[UploadFile]] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


class ReferenceItem(BaseModel):
    ref_id: str
    page_no: int | None = None
    summary: str
    doucument_title: str
    score: float | None = None


class ChatResponse(BaseModel):
    reply: str
    latency_ms: int
    reference: List[ReferenceItem] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    result = await handle_chat(payload)
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    return create_chat_stream(payload)

