"""ARQ Worker 任务定义。"""
import asyncio
import sys

from arq.connections import RedisSettings

from app.core.config import settings
from app.services.agent_service import AgentService
from app.tasks.jobs.video_cogvideox_flash import generate_video_task

# Windows 下 arq 默认使用 ProactorEventLoop，而 psycopg 异步驱动只支持 SelectorEventLoop。
# 必须在事件循环创建前（即本模块被 arq CLI 导入时）切换，否则 worker 落库会报 InterfaceError。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def run_agent_task(
    ctx, thread_id: str, user_id: str, session_id: str, message: str
) -> str:
    """ARQ Worker 执行的非流式 Agent 任务。"""
    agent_service = AgentService()
    return await agent_service.run_agent_sync(
        thread_id=thread_id,
        user_id=user_id,
        session_id=session_id,
        message=message,
    )


class WorkerSettings:
    """ARQ Worker 配置。"""

    functions = [run_agent_task, generate_video_task]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 30  # 秒
    default_job_timeout = 300  # 5 分钟
    max_jobs = 10
