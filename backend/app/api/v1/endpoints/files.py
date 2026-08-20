"""文件上传接口（阶段 9）。

POST /api/v1/files：上传文件 → 校验类型/大小/全局配额 → 落存储+落库 →
异步入队解析任务与空间清理任务。返回 file_id + task_id 供前端轮询解析状态。
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.database import get_db
from app.models.user import User
from app.services.file_parser import coerce_content_type, is_supported
from app.services.file_service import FileService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile,
    req: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上传文件：异步解析为纯文本并注入后续对话上下文。

    Returns:
        {file_id, task_id, status, filename}，前端按 task_id 轮询解析状态。
    """
    # 1. 类型校验（MIME 白名单；浏览器对 .md 等扩展名上报的 Content-Type 不稳定，先按扩展名回退规范化）
    content_type = coerce_content_type(file.filename, file.content_type)
    if not is_supported(content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型：{file.content_type or '未知'}，支持 txt/md/json/csv/pdf/docx/xlsx/图片(jpg/png/bmp)",
        )

    # 2. 读取内容 + 单文件大小校验
    content = await file.read()
    if len(content) > settings.FILE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件超过大小上限（20MB）",
        )

    service = FileService()

    # 3. 全局空间上限：仅 persist（转存存储）模式校验；transient 即解析即删不占存储
    if settings.FILE_PARSE_MODE == "persist":
        total_all = await service.total_size_all(db)
        if total_all >= settings.FILE_GLOBAL_QUOTA_BYTES:
            pool = req.app.state.redis_pool
            await pool.enqueue_job("cleanup_global_files_task")
            logger.warning(
                "全局存储空间已满 user_id=%s total_bytes=%d", current_user.id, total_all
            )
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail="存储空间已满，请稍后再试",
            )

    # 4. 落库（transient 仅落库；persist 转存存储后落库）
    try:
        if settings.FILE_PARSE_MODE == "persist":
            # persist：转存存储（local/qiniu）后落库，解析任务再从存储下载回读
            record = await service.save(
                user_id=current_user.id,
                filename=file.filename or "unnamed",
                content_type=content_type,
                content=content,
                db=db,
            )
        else:
            # transient（默认）：即解析即删，仅落库不转存，字节直接传给解析任务
            record = await service.create_record(
                user_id=current_user.id,
                filename=file.filename or "unnamed",
                content_type=content_type,
                content=content,
                db=db,
            )
    except Exception as exc:
        logger.error("文件保存失败 user_id=%s err=%s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件保存失败：{exc}",
        )

    # 5. 异步解析任务（transient 传 content 字节；persist 不传，任务内自行下载）
    pool = req.app.state.redis_pool
    if settings.FILE_PARSE_MODE == "persist":
        parse_job = await pool.enqueue_job(
            "parse_file_task", str(record.id), str(current_user.id)
        )
    else:
        parse_job = await pool.enqueue_job(
            "parse_file_task", str(record.id), str(current_user.id), content
        )
    if parse_job is None:
        logger.error("解析任务入队失败 file_id=%s", record.id)

    # 6. 每用户空间配额：仅 persist 模式校验；transient 不占存储
    if settings.FILE_PARSE_MODE == "persist":
        if await service.total_size(current_user.id, db) > settings.FILE_QUOTA_BYTES:
            await pool.enqueue_job("cleanup_files_task", str(current_user.id))

    logger.info(
        "文件上传成功 file_id=%s user_id=%s size=%d",
        record.id, current_user.id, record.size,
    )
    return {
        "file_id": str(record.id),
        "task_id": parse_job.job_id if parse_job else None,
        "status": "parsing",
        "filename": record.filename,
    }


@router.get("/{file_id}/url")
async def get_file_url(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回文件的公开访问 URL（历史消息附件展示用）。"""
    try:
        fuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")
    service = FileService()
    record = await service.get(current_user.id, fuid, db)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"file_id": file_id, "url": service.url(record), "filename": record.filename}
