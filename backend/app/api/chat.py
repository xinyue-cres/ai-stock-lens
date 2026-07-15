"""个股对话 API：SSE 流式端点。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.services import chat_service

router = APIRouter(prefix="/api/stocks", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    inject_context: bool = True


@router.post("/{code}/chat")
def chat_stream(code: str, body: ChatRequest, session: Session = Depends(get_session)):
    """流式对话：注入个股上下文后与 AI 多轮对话。"""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    return StreamingResponse(
        chat_service.stream_chat(session, code, messages, inject_context=body.inject_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
