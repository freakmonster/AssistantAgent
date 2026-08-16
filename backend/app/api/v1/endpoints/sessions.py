"""会话管理接口。"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.database import get_db
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.message import MessageResponse
from app.schemas.session import SessionCreate, SessionResponse

router = APIRouter()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """创建会话，thread_id 使用 {user_id}_{conversation_id} 复合键。"""
    thread_id = f"{current_user.id}_{uuid.uuid4()}"
    session = Session(
        user_id=current_user.id,
        title=request.title,
        thread_id=thread_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _to_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """列出当前用户的所有会话（强制 user_id 过滤，附带消息数量）。"""
    result = await db.execute(
        select(Session, func.count(Message.id).label("message_count"))
        .outerjoin(Message, Message.session_id == Session.id)
        .where(Session.user_id == current_user.id)
        .group_by(Session.id)
        .order_by(Session.updated_at.desc())
    )
    return [
        _to_response(s, message_count=count) for s, count in result.all()
    ]


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除会话（强制归属校验，先删消息再删会话）。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await db.get(Session, session_uuid)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    # 外键无 ON DELETE CASCADE，先删消息再删会话
    await db.execute(delete(Message).where(Message.session_id == session.id))
    await db.delete(session)
    await db.commit()
    return {"deleted": True}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """列出会话的历史消息（强制归属校验，仅限当前用户自己的会话）。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await db.get(Session, session_uuid)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session.id)
        # 同事务内 user/assistant 的 created_at 相同（func.now() 为事务开始时间），
        # 用 role 作二级排序键，保证同时间戳下 user 在前、assistant 在后。
        .order_by(
            Message.created_at.asc(),
            case((Message.role == "user", 0), else_=1).asc(),
        )
    )
    messages = result.scalars().all()
    return [_to_message_response(m) for m in messages]


def _to_message_response(message: Message) -> MessageResponse:
    """将 ORM 消息对象转换为响应 Schema。"""
    return MessageResponse(
        id=str(message.id),
        role=message.role,
        content=message.content,
        tool_calls=message.tool_calls,
        attachments=message.attachments,
        created_at=message.created_at.isoformat() if message.created_at else "",
    )


def _to_response(session: Session, message_count: int = 0) -> SessionResponse:
    """将 ORM 对象转换为响应 Schema。"""
    return SessionResponse(
        id=str(session.id),
        title=session.title,
        thread_id=session.thread_id,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
        message_count=message_count,
    )
