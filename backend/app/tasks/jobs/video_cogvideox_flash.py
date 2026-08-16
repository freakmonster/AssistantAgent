"""视频生成异步任务 worker（智谱 CogVideoX-Flash）。工具来源：智谱AI开放平台

调用智谱 CogVideoX-Flash 生成视频：提交 -> 轮询 -> 落库 -> 返回结果。

todo: 后续可在提交步骤加 429 限流重试/退避（如 tenacity），避免偶发限流直接失败。
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.models.database import async_session_factory
from app.models.message import Message
from app.models.session import Session
# 转存功能已注释停用（直接返回临时 URL）；如需恢复请取消此导入
# from app.services.media_storage import media_storage

logger = logging.getLogger(__name__)

# 最小骨架固定参数：分辨率 1024x1024、帧率 30、速度优先（实测最快且稳定，≤2048x1080）
VIDEO_SIZE = "1024x1024"
VIDEO_FPS = 30
VIDEO_QUALITY = "speed"

# 轮询参数
POLL_INTERVAL = 5  # 秒
MAX_POLL_SECONDS = 280  # 略小于 ARQ default_job_timeout=300，靠 ARQ 兜底


async def generate_video_task(ctx, user_id: str, session_id: str, prompt: str) -> dict:
    """后台生成视频：提交智谱任务并轮询到完成，落库后返回可渲染结果。

    Args:
        ctx: ARQ 注入的任务上下文。
        user_id: 用户标识（入队时由 submit_task 注入）。
        session_id: 会话标识（字符串，落库时转 uuid）。
        prompt: 视频文本描述。

    Returns:
        视频结果字典，含 type/url/poster/prompt。
    """
    logger.info(
        "开始生成视频 job_id=%s user_id=%s session_id=%s prompt=%s",
        ctx.get("job_id"),
        user_id,
        session_id,
        prompt,
    )
    headers = {
        "Authorization": f"Bearer {settings.ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    submit_url = f"{settings.ZHIPU_BASE_URL}/api/paas/v4/videos/generations"
    query_url = f"{settings.ZHIPU_BASE_URL}/api/paas/v4/async-result/{{task_id}}"

    async with httpx.AsyncClient(timeout=60) as client:
        # 1. 提交视频生成任务
        resp = await client.post(
            submit_url,
            json={
                "model": "cogvideox-flash",
                "prompt": prompt,
                "quality": VIDEO_QUALITY,
                "with_audio": False,
                "size": VIDEO_SIZE,
                "fps": VIDEO_FPS,
            },
            headers=headers,
        )
        resp.raise_for_status()
        task_id = resp.json().get("id")
        if not task_id:
            logger.error("智谱提交失败，缺少任务 id：%s", resp.text)
            raise RuntimeError(f"智谱提交失败，缺少任务 id：{resp.text}")
        logger.info("智谱视频任务已提交 task_id=%s", task_id)

        # 2. 轮询到完成
        elapsed = 0
        video_url = None
        cover_url = None
        while elapsed <= MAX_POLL_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            r = await client.get(query_url.format(task_id=task_id), headers=headers)
            r.raise_for_status()
            data = r.json()
            status = data.get("task_status")
            logger.info("轮询视频任务 task_id=%s elapsed=%ss status=%s", task_id, elapsed, status)
            if status == "SUCCESS":
                video_result = data.get("video_result") or []
                if video_result:
                    video_url = video_result[0].get("url")
                    cover_url = video_result[0].get("cover_image_url")
                break
            if status == "FAIL":
                logger.error("智谱视频生成失败 task_id=%s data=%s", task_id, data)
                raise RuntimeError(f"智谱视频生成失败：{data}")

        if video_url is None:
            logger.error("视频生成超时 task_id=%s elapsed=%ss", task_id, elapsed)
            raise TimeoutError(f"视频生成超时（超过 {MAX_POLL_SECONDS}s）")

    # 3. 返回媒体 URL。转存功能已注释停用：直接返回智谱临时 URL（约 30 天有效），
    #    避免本地磁盘增长；如需恢复转存，取消上方 import 并启用：
    #    url = await media_storage.transfer(video_url, media_type="video")
    #    poster = await media_storage.transfer(cover_url, media_type="image") if cover_url else None
    url = video_url
    poster = cover_url if cover_url else None
    result = {"type": "video", "url": url, "poster": poster, "prompt": prompt}
    logger.info("视频生成成功 task_id=%s url=%s", task_id, url)

    # 4. 完成时落库
    await _save_task_result(session_id, result)
    logger.info("视频结果已落库 session_id=%s", session_id)
    return result


async def _save_task_result(session_id: str, result: dict) -> None:
    """将视频结果写入 messages 表（role=assistant，attachments 存媒体 URL）。

    同时刷新对应会话的 updated_at，保证完成任务的会话能在列表排到最前。
    """
    async with async_session_factory() as session:
        db_session = await session.scalar(
            select(Session).where(Session.id == uuid.UUID(session_id))
        )
        if db_session is not None:
            db_session.updated_at = datetime.now(timezone.utc)
        session.add(
            Message(
                session_id=uuid.UUID(session_id),
                role="assistant",
                content=result.get("prompt") or "生成的视频",
                attachments=[
                    {
                        "type": result["type"],
                        "url": result["url"],
                        "poster": result.get("poster"),
                    }
                ],
            )
        )
        await session.commit()
