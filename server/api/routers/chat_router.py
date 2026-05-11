from fastapi import APIRouter

from server.api.schemas import ChatRequest, ChatResponse, ChatSessionResponse
from server.memory.conversation_store import infer_scope, load_conversation
from server.services.chat_service import create_chat_stream, handle_chat

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    result = await handle_chat(payload)
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    return create_chat_stream(payload)


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    user_id: str = "default_user",
) -> ChatSessionResponse:
    scope = infer_scope(session_id)
    payload = load_conversation(
        user_id=user_id,
        session_id=session_id,
        scope=scope,
    )
    return ChatSessionResponse(**payload)

