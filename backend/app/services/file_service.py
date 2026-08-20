"""文件服务层（阶段 9）。

封装文件存储 + 数据库记录的统一操作：
  - save：写存储 + 落库（落库失败回滚存储对象）
  - load_texts / get：读取解析文本（强制 WHERE user_id 隔离）
  - total_size / total_size_all：空间占用统计
  - cleanup_excess / cleanup_expired / cleanup_global_excess：空间清理
存储实现按 settings.FILE_UPLOAD_STORAGE 切换（local / qiniu）。
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file import File
from app.services.file_storage import FileStorage, KodoFileStorage, LocalFileStorage

logger = logging.getLogger(__name__)


def build_storage() -> FileStorage:
    """按配置构建存储实现。

    FILE_UPLOAD_STORAGE=qiniu 时校验 QINIU_* 四项配置齐全，缺失报清晰错误。

    Returns:
        对应存储实现实例。
    """
    if settings.FILE_UPLOAD_STORAGE == "qiniu":
        missing = [
            name
            for name, val in [
                ("QINIU_ACCESS_KEY", settings.QINIU_ACCESS_KEY),
                ("QINIU_SECRET_KEY", settings.QINIU_SECRET_KEY),
                ("QINIU_BUCKET", settings.QINIU_BUCKET),
                ("QINIU_DOMAIN", settings.QINIU_DOMAIN),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"FILE_UPLOAD_STORAGE=qiniu 但缺少配置：{', '.join(missing)}（请检查 .env）"
            )
        return KodoFileStorage(
            settings.QINIU_ACCESS_KEY,
            settings.QINIU_SECRET_KEY,
            settings.QINIU_BUCKET,
            settings.QINIU_DOMAIN,
        )
    return LocalFileStorage(settings.FILE_UPLOAD_DIR)


class FileService:
    """文件上传/读取/清理服务。"""

    def __init__(self, storage: FileStorage | None = None) -> None:
        """初始化服务，默认按配置构建存储实现。

        Args:
            storage: 外部注入的存储实现（测试用），默认 build_storage()。
        """
        self._storage = storage or build_storage()

    async def save(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
        db: AsyncSession,
    ) -> File:
        """保存文件：写存储 + 落库，返回 File 记录。

        落库失败时清理已写入的存储对象，避免孤儿文件。
        """
        file_id = uuid.uuid4()
        key = f"{user_id}/{file_id}"
        await self._storage.save(key, content)
        record = File(
            id=file_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path=key,
        )
        try:
            db.add(record)
            await db.commit()
            await db.refresh(record)
            return record
        except Exception:
            # 落库失败：回滚存储对象，保持存储与 DB 一致
            await db.rollback()
            await self._storage.delete(key)
            raise

    async def create_record(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
        db: AsyncSession,
    ) -> File:
        """仅落库不转存（transient「即解析即删」链路用）。

        原始文件不写入存储层（storage_path 置空），后续 parse_file_task
        直接使用上传时的字节解析，解析结果回写 extracted_text，原始字节用完即弃。
        """
        record = File(
            id=uuid.uuid4(),
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path="",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    async def load_texts(
        self, user_id: uuid.UUID, file_ids: list[uuid.UUID], db: AsyncSession
    ) -> list[dict]:
        """按 file_ids 读取已解析文本，强制 user_id 隔离。

        Args:
            user_id: 当前用户（查询强制 WHERE user_id）。
            file_ids: 附件文件 id 列表。
            db: 数据库会话。

        Returns:
            [{file_id, filename, text}]，仅包含解析成功（extracted_text 非空）的文件。
        """
        if not file_ids:
            return []
        rows = (
            await db.execute(
                select(File).where(
                    File.user_id == user_id, File.id.in_(file_ids)
                )
            )
        ).scalars().all()
        return [
            {"file_id": f.id, "filename": f.filename, "text": f.extracted_text}
            for f in rows
            if f.extracted_text
        ]

    async def get(
        self, user_id: uuid.UUID, file_id: uuid.UUID, db: AsyncSession
    ) -> File | None:
        """按 id 查询文件（强制 user_id 隔离，越权返回 None）。"""
        return await db.scalar(
            select(File).where(File.user_id == user_id, File.id == file_id)
        )

    def url(self, file: File) -> str:
        """返回文件的公开访问 URL。"""
        return self._storage.url(file.storage_path)

    async def total_size(self, user_id: uuid.UUID, db: AsyncSession) -> int:
        """统计单个用户当前总占用字节数。"""
        return (
            await db.scalar(
                select(func.coalesce(func.sum(File.size), 0)).where(
                    File.user_id == user_id
                )
            )
        ) or 0

    async def total_size_all(self, db: AsyncSession) -> int:
        """统计全部用户累计占用字节数（全局配额校验用）。"""
        return (
            await db.scalar(select(func.coalesce(func.sum(File.size), 0)))
        ) or 0

    async def cleanup_excess(
        self, user_id: uuid.UUID, db: AsyncSession, storage: FileStorage | None = None
    ) -> list[uuid.UUID]:
        """每用户空间清理：总占用超配额时删除该用户最旧约一半空间的文件。

        仅清理本用户文件（WHERE user_id 隔离），存储删除失败不中断 DB 清理。

        Args:
            user_id: 目标用户。
            db: 数据库会话。
            storage: 存储实现（默认自身存储）。

        Returns:
            被删除文件 id 列表。
        """
        total = await self.total_size(user_id, db)
        if total <= settings.FILE_QUOTA_BYTES:
            return []
        rows = (
            await db.execute(
                select(File)
                .where(File.user_id == user_id)
                .order_by(File.created_at.asc(), File.id.asc())
            )
        ).scalars().all()
        # 累积最旧文件直到 ≥ 总量一半，释放约一半空间
        target = total / 2
        accumulated = 0
        to_delete = []
        for f in rows:
            accumulated += f.size
            to_delete.append(f)
            if accumulated >= target:
                break
        return await self._delete_files(db, storage or self._storage, to_delete)

    async def cleanup_expired(
        self, db: AsyncSession, storage: FileStorage | None = None
    ) -> list[uuid.UUID]:
        """保留期清理：删除超过 FILE_RETENTION_DAYS 的文件（全用户）。

        供 ARQ cron 每日执行，无论是否超配额。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.FILE_RETENTION_DAYS)
        rows = (
            await db.execute(
                select(File).where(File.created_at < cutoff)
            )
        ).scalars().all()
        return await self._delete_files(db, storage or self._storage, list(rows))

    async def cleanup_global_excess(
        self, db: AsyncSession, storage: FileStorage | None = None
    ) -> list[uuid.UUID]:
        """全局空间清理：全用户累计超全局配额时删除全局最旧约一半空间的文件。

        空间共享（同一 bucket），跨用户删最旧，优先清除使用价值最低的数据。
        """
        total = await self.total_size_all(db)
        if total <= settings.FILE_GLOBAL_QUOTA_BYTES:
            return []
        rows = (
            await db.execute(
                select(File).order_by(File.created_at.asc(), File.id.asc())
            )
        ).scalars().all()
        target = total / 2
        accumulated = 0
        to_delete = []
        for f in rows:
            accumulated += f.size
            to_delete.append(f)
            if accumulated >= target:
                break
        return await self._delete_files(db, storage or self._storage, to_delete)

    async def _delete_files(
        self, db: AsyncSession, storage: FileStorage, files: list[File]
    ) -> list[uuid.UUID]:
        """删除执行体：逐个删存储对象 → DB 批量删。存储失败仅记录日志。"""
        if not files:
            return []
        for f in files:
            if not f.storage_path:
                continue  # transient 模式：无存储对象，仅删 DB 记录
            try:
                await storage.delete(f.storage_path)
            except Exception as exc:
                logger.warning("删除存储对象失败 key=%s err=%s", f.storage_path, exc)
        ids = [f.id for f in files]
        await db.execute(delete(File).where(File.id.in_(ids)))
        await db.commit()
        return ids
