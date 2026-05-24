from typing import Any, Dict, List, Literal, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field

MessageRole = Literal["system", "user", "assistant"]


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
    project_path: Optional[str] = None


class CourseListResponse(BaseModel):
    items: List[CourseItem]
    total: int


class WorkspaceFileItem(BaseModel):
    name: str
    path: str
    type: Literal["file", "directory"]
    size: int = 0
    modified_at: Optional[float] = None
    children: List["WorkspaceFileItem"] = Field(default_factory=list)


class WorkspaceTreeResponse(BaseModel):
    root: str
    items: List[WorkspaceFileItem] = Field(default_factory=list)


class WorkspaceFileResponse(BaseModel):
    path: str
    name: str
    content: str
    encoding: str = "utf-8"
    size: int = 0
    modified_at: Optional[float] = None


class WorkspaceFileSaveRequest(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"


class WorkspaceFileSaveResponse(BaseModel):
    ok: bool = True
    path: str
    size: int = 0
    modified_at: Optional[float] = None


class WorkspaceFileCreateRequest(BaseModel):
    path: str
    content: str = ""


class WorkspaceDirectoryCreateRequest(BaseModel):
    path: str


class WorkspaceRenameRequest(BaseModel):
    source_path: str
    target_path: str


class WorkspaceDeleteResponse(BaseModel):
    ok: bool = True
    path: str


class ChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    user_id: str = "default_user"
    session_id: str = "default"
    messages: List[ChatMessage] = Field(min_length=1)
    use_retrieval: bool = False
    document_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    use_web_search: bool = False
    workspace_path: Optional[str] = None
    files: Optional[List[UploadFile]] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


class ReferenceItem(BaseModel):
    ref_id: str
    citation_id: Optional[str] = None
    type: Optional[str] = None
    page_no: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    summary: str
    doucument_title: str
    score: float | None = None
    source_path: str | None = None
    document_id: Optional[int] = None
    target: Optional[Dict[str, Any]] = None


class TokenUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cache_hit_tokens: Optional[int] = None
    cache_miss_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    latency_ms: int
    reference: List[ReferenceItem] = Field(default_factory=list)
    usage: Optional[TokenUsage] = None
    model: Optional[str] = None


class AgentRunRequest(BaseModel):
    user_id: str = "default_user"
    session_id: str = "default"
    messages: List[ChatMessage] = Field(min_length=1)
    workspace_path: Optional[str] = None
    document_id: Optional[int] = None
    document_ids: Optional[List[int]] = None
    use_retrieval: bool = False
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    mode: str = "plan_then_act"


class AgentRunStateResponse(BaseModel):
    run_id: str
    status: str
    user_id: str
    session_id: str
    created_at: str
    updated_at: str
    plan: List[Dict[str, Any]] = Field(default_factory=list)
    operations: List[Dict[str, Any]] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    reply: str = ""


class StoredChatMessage(BaseModel):
    role: MessageRole
    content: str
    created_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    refs: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[str]] = None


class ChatSessionResponse(BaseModel):
    user_id: str
    session_id: str
    scope: str
    title: str
    messages: List[StoredChatMessage] = Field(default_factory=list)
    compressed_summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillItem(BaseModel):
    id: str
    name: str
    description: str
    triggers: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    path: Optional[str] = None


class SkillListResponse(BaseModel):
    items: List[SkillItem] = Field(default_factory=list)
    total: int = 0


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str = ""
    speed: float = 1.0


class ProviderConfigUpdateRequest(BaseModel):
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    companion_persona_prompt: Optional[str] = None
