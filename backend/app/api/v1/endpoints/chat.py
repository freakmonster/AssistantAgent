"""对话接口。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.database import get_db
from app.models.session import Session
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent_service import AgentService
from app.utils import logger as app_logger
from app.utils.llm import list_available_models, resolve_model

router = APIRouter()


def _resolve_model_id(model: str | None) -> str:
    """校验前端传入的模型 id，返回规范 id；非法时抛 400。"""
    try:
        return resolve_model(model).id
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/models")
async def list_models() -> list[dict]:
    """返回前端可选的模型列表（仅 id + name，不暴露供应商密钥）。"""
    return list_available_models()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """非流式对话：前端传 session_id，后端定位 thread_id 后调用 Agent。"""
    try:
        session_uuid = uuid.UUID(request.session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await db.get(Session, session_uuid)
    # 会话隔离：会话必须属于当前用户
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # 绑定 user_id/session_id 到结构化日志上下文（trace_id 已由中间件绑定）
    app_logger.bind_request_context(user_id=str(current_user.id), session_id=str(session.id))

    model_id = _resolve_model_id(request.model)

    agent_service = AgentService()
    response = await agent_service.run_agent_sync(
        thread_id=session.thread_id,
        user_id=str(current_user.id),
        session_id=str(session.id),
        message=request.message,
        attachments=request.attachments,
        model=model_id,
    )
    return ChatResponse(session_id=request.session_id, response=response)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式对话（SSE）。前端传 session_id，后端定位 thread_id 后调用 Agent。"""
    try:
        session_uuid = uuid.UUID(request.session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await db.get(Session, session_uuid)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # 绑定 user_id/session_id 到结构化日志上下文（trace_id 已由中间件绑定）
    app_logger.bind_request_context(user_id=str(current_user.id), session_id=str(session.id))

    model_id = _resolve_model_id(request.model)

    agent_service = AgentService()
    event_generator = agent_service.stream_agent_response(
        thread_id=session.thread_id,
        user_id=str(current_user.id),
        session_id=str(session.id),
        message=request.message,
        attachments=request.attachments,
        model=model_id,
    )
    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
