from typing import Any, Dict, List, Literal, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = 5
    document_id: Optional[int] = None
    candidate_limit: int = 1000


class SearchItem(BaseModel):
    chunk_id: int
    content: str
    score: float
    document_id: int
    document_title: str
    page_no: int | None = None


class SearchResponse(BaseModel):
    results: List[SearchItem]


class MaterialItem(BaseModel):
    document_id: int
    course_id: int
    title: str
    file_type: str
    source_path: str
    created_at: str | None = None
    chunk_count: int


class MaterialListResponse(BaseModel):
    items: List[MaterialItem]
    total: int


class MaterialDetail(BaseModel):
    item: MaterialItem


class MaterialDeleteResponse(BaseModel):
    ok: bool
    document_id: int


class CourseCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    term: Optional[str] = None
    owner_id: str = "default_user"


class CourseUpdateRequest(BaseModel):
    name: Optional[str] = None
    term: Optional[str] = None


class CourseItem(BaseModel):
    course_id: int
    name: str
    term: Optional[str] = None
    owner_id: str
    created_at: Optional[str] = None
    doc_count: int
    cover_document_id: Optional[int] = None


class CourseListResponse(BaseModel):
    items: List[CourseItem]
    total: int


class CompanionMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = ""


class CompanionActionIntent(BaseModel):
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class CompanionChatRequest(BaseModel):
    user_id: str = "user1"
    session_id: str
    messages: List[CompanionMessage] = Field(default_factory=list)
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    persona_id: Optional[str] = "default_companion"
    scene: Optional[str] = "desktop"
    model: Optional[str] = None
    route_mode: Optional[str] = "auto"
    capability_ide: bool = False


class CompanionChatResponse(BaseModel):
    reply: str = ""
    tts_text: str = ""
    emotion: str = "neutral"
    action_intents: List[CompanionActionIntent] = Field(default_factory=list)
    latency_ms: int = 0
    delegated_task: Dict[str, Any] | None = None
    route_decision: Dict[str, Any] | None = None


class CompanionActRequest(BaseModel):
    user_id: str
    session_id: str
    action_intents: List[CompanionActionIntent] = Field(default_factory=list)


class CompanionActResponse(BaseModel):
    ok: bool = True
    applied: List[CompanionActionIntent] = Field(default_factory=list)
    rejected: List[str] = Field(default_factory=list)


class CompanionTaskPollRequest(BaseModel):
    user_id: str = "user1"
    session_id: str
    task_id: Optional[str] = None


class CompanionTaskPollResponse(BaseModel):
    ok: bool = True
    task: Dict[str, Any] | None = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str = ""
    speed: float = 1.0
