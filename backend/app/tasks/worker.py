"""ARQ Worker 任务定义。"""
import asyncio
import logging
import sys
import uuid

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.services.agent_service import AgentService
from app.services.file_compress import compress_file_text
from app.services.file_parser import (
    UnsupportedFileType,
    build_file_meta_block,
    extract_file_meta,
    parse_file,
)
from app.services.file_service import FileService
from app.services.ocr_engine import OCRError, get_ocr_engine, needs_ocr
from app.tasks.jobs.video_cogvideox_flash import generate_video_task

logger = logging.getLogger(__name__)

# Windows 下 arq 默认使用 ProactorEventLoop，而 psycopg 异步驱动只支持 SelectorEventLoop。
# 必须在事件循环创建前（即本模块被 arq CLI 导入时）切换，否则 worker 落库会报 InterfaceError。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def run_agent_task(
    ctx, thread_id: str, user_id: str, session_id: str, message: str,
    attachments: list[str] | None = None,
) -> str:
    """ARQ Worker 执行的非流式 Agent 任务。"""
    agent_service = AgentService()
    return await agent_service.run_agent_sync(
        thread_id=thread_id,
        user_id=user_id,
        session_id=session_id,
        message=message,
        attachments=attachments or [],
    )


async def parse_file_task(
    ctx, file_id: str, user_id: str, content: bytes | None = None
) -> dict:
    """解析上传文件为纯文本并回写 extracted_text。

    返回结构化结果供前端轮询判断：
        成功: {"ok": True}
        失败: {"ok": False, "error": "具体原因"}（不抛异常，避免 ARQ 重试）。

    Args:
        ctx: ARQ 任务上下文。
        file_id: 文件记录 id（字符串）。
        user_id: 文件归属用户（查询强制 WHERE user_id）。
        content: 文件原始字节。transient 模式（即解析即删）由上传接口直接传入，
            不再从存储下载；persist 模式为 None，任务内从存储 load 回读。
    """
    from sqlalchemy import select

    from app.models.database import async_session_factory
    from app.models.file import File

    service = FileService()
    async with async_session_factory() as db:
        file = await db.scalar(
            select(File).where(
                File.id == uuid.UUID(file_id), File.user_id == uuid.UUID(user_id)
            )
        )
        if file is None:
            logger.error("解析任务找不到文件 file_id=%s user_id=%s", file_id, user_id)
            return {"ok": False, "error": "文件不存在或已清理"}
        try:
            if content is None:
                # persist 模式：从存储下载回读（KodoFileStorage.load 已含分片并发）
                content = await service._storage.load(file.storage_path)
            text = await asyncio.to_thread(parse_file, content, file.content_type)
            # 扫描件（图片或无文本层 PDF）转 OCR 提取文字；未启用/缺密钥时保持现状
            if needs_ocr(file.content_type, text):
                ocr = get_ocr_engine()
                if ocr is not None:
                    text = await ocr.recognize(content, file.content_type)
            # 压缩前记录原始字符数，并提取结构性元信息（页数/工作表数）
            char_count = len(text)
            meta = await asyncio.to_thread(extract_file_meta, content, file.content_type)
        except UnsupportedFileType as exc:
            logger.error("文件类型不支持 file_id=%s err=%s", file_id, exc)
            return {"ok": False, "error": f"不支持的文件类型：{exc}"}
        except OCRError as exc:
            logger.error("扫描件 OCR 识别失败 file_id=%s err=%s", file_id, exc)
            return {"ok": False, "error": f"扫描件识别失败：{exc}"}
        except Exception as exc:
            logger.error("解析文件失败 file_id=%s err=%s", file_id, exc)
            return {"ok": False, "error": f"解析失败：{exc}"}
        # 可选：超长文本做 LLM 语义压缩（失败内部降级字符截断，不会抛异常）
        try:
            text = await compress_file_text(text, file.content_type)
        except Exception as exc:  # noqa: BLE001 - 双保险：压缩异常不阻断解析落库
            logger.warning("附件压缩失败，降级为原文 file_id=%s err=%s", file_id, exc)
        # 元信息强制加回：不参与压缩，保证页数/字符数等完整且不被模型改写
        meta_block = build_file_meta_block(meta, char_count, file.size, file.content_type)
        file.extracted_text = meta_block + "\n\n" + text
        await db.commit()
        logger.info("文件解析完成 file_id=%s size=%d 文本长度=%d", file_id, file.size, len(text))
        return {"ok": True}


async def cleanup_files_task(ctx, user_id: str) -> dict:
    """每用户空间清理：超配额时删除该用户最旧约一半空间的文件。"""
    from app.models.database import async_session_factory

    service = FileService()
    async with async_session_factory() as db:
        deleted = await service.cleanup_excess(uuid.UUID(user_id), db)
    result = {"deleted_files": len(deleted)}
    logger.info("每用户空间清理完成 user_id=%s 删除文件数=%d", user_id, len(deleted))
    return result


async def cleanup_global_files_task(ctx) -> dict:
    """全局空间清理：全用户累计超 8GB 时删除全局最旧约一半空间的文件。"""
    from app.models.database import async_session_factory

    service = FileService()
    async with async_session_factory() as db:
        deleted = await service.cleanup_global_excess(db)
    result = {"deleted_files": len(deleted)}
    logger.info("全局空间清理完成 删除文件数=%d", len(deleted))
    return result


async def expire_files_task(ctx) -> dict:
    """保留期清理：删除超过 FILE_RETENTION_DAYS 的文件（每日 cron 执行）。"""
    from app.models.database import async_session_factory

    service = FileService()
    async with async_session_factory() as db:
        deleted = await service.cleanup_expired(db)
    result = {"deleted_files": len(deleted)}
    logger.info("保留期清理完成 删除文件数=%d", len(deleted))
    return result


class WorkerSettings:
    """ARQ Worker 配置。"""

    functions = [
        run_agent_task,
        generate_video_task,
        parse_file_task,
        cleanup_files_task,
        cleanup_global_files_task,
        expire_files_task,
    ]
    # 每日 03:00 执行保留期清理；worker 启动时先跑一次
    cron_jobs = [cron(expire_files_task, hour=3, minute=0, run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 30  # 秒
    default_job_timeout = 300  # 5 分钟
    max_jobs = 10
