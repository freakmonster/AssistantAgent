"""异步任务接口（ARQ 入队与状态查询）。"""
import uuid

from arq.jobs import Job
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.database import get_db
from app.models.session import Session
from app.models.user import User
from app.schemas.chat import ChatRequest

router = APIRouter()


async def _resolve_session(
    session_id: str, current_user: User, db: AsyncSession
) -> Session:
    """解析会话并校验归属，返回 thread_id 对应的 Session。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    session = await db.get(Session, session_uuid)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_agent_task(
    request: ChatRequest,
    req: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """将非流式 Agent 任务入队到 ARQ，返回任务 ID。"""
    session = await _resolve_session(request.session_id, current_user, db)
    pool = req.app.state.redis_pool
    job = await pool.enqueue_job(
        "run_agent_task",
        session.thread_id,
        str(current_user.id),
        str(session.id),
        request.message,
        request.attachments,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Task already exists"
        )
    return {"task_id": job.job_id, "status": "queued"}


@router.get("/{task_id}")
async def get_task_status(task_id: str, req: Request) -> dict:
    """查询任务状态（不等待结果）。"""
    pool = req.app.state.redis_pool
    job = Job(task_id, pool)
    job_status = await job.status()
    result_info = await job.result_info()
    return {
        "task_id": task_id,
        "status": job_status.value,
        "result": result_info.result if result_info else None,
    }
