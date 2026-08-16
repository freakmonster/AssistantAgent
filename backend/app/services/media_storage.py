"""媒体转存服务。

把供应商返回的临时媒体 URL（如智谱视频/图片，约 30 天有效）下载到本地
存储，生成长期可访问的 URL 落库，避免链接过期失效。

流程：下载 → 校验（大小/类型）→ 存本地 → 返回长期 URL。
存储层复用 file_storage.py 的抽象，本地存 uploads/，对象存储留待阶段 8。
"""
import logging
import uuid

import httpx

from app.core.config import settings
from app.services.file_storage import FileStorage, LocalFileStorage

logger = logging.getLogger(__name__)

# 允许转存的媒体类型前缀（白名单校验，防止下载任意文件）
ALLOWED_CONTENT_PREFIXES = ("image/", "video/", "audio/")

# Content-Type 到文件扩展名的简单映射
CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


class MediaStorage:
    """媒体下载转存：临时 URL → 本地长期存储 → 可访问 URL。"""

    def __init__(self, storage: FileStorage | None = None) -> None:
        """初始化转存服务。

        Args:
            storage: 底层存储实现，默认本地文件系统（uploads/）。
        """
        self._storage = storage or LocalFileStorage(settings.MEDIA_UPLOAD_DIR)

    async def transfer(self, url: str, media_type: str = "media") -> str:
        """转存媒体 URL，返回长期可访问地址。

        Args:
            url: 供应商返回的临时媒体 URL。
            media_type: 媒体类别（media/image/video），用于目录隔离。

        Returns:
            长期可访问 URL（如 /media/image/xxx.jpg）。
            下载失败或校验不通过时返回 {"error": ...} 结构。
        """
        try:
            content, content_type = await self._download(url)
            ext = CONTENT_TYPE_EXT.get(content_type, "")
            # 按日期分目录 + uuid 命名，避免重名与目录过大
            date_dir = uuid.uuid4().hex[:8]
            key = f"{media_type}/{date_dir}/{uuid.uuid4().hex}{ext}"
            await self._storage.save(key, content)
            long_url = f"{settings.MEDIA_URL_PREFIX}/{key}"
            logger.info(
                "媒体转存成功 url=%s long_url=%s size=%dB type=%s",
                url,
                long_url,
                len(content),
                content_type,
            )
            return long_url
        except Exception as exc:
            logger.error("媒体转存失败 url=%s err=%s", url, exc)
            return f'{{"error": "TransferFailed", "message": "媒体转存失败"}}'

    async def _download(self, url: str) -> tuple[bytes, str]:
        """下载临时 URL，校验大小与类型，返回 (内容, Content-Type)。

        Raises:
            HTTPError / TimeoutException / ValueError: 下载或校验失败。
        """
        if not url or not str(url).startswith(("http://", "https://")):
            raise ValueError(f"非法的媒体 URL：{url}")

        async with httpx.AsyncClient(
            timeout=settings.MEDIA_DOWNLOAD_TIMEOUT, follow_redirects=True
        ) as client:
            # 流式下载：边下边累计，超限立即中断，避免大文件占满内存
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                # 类型白名单校验
                if not content_type.startswith(ALLOWED_CONTENT_PREFIXES):
                    raise ValueError(f"不支持的媒体类型：{content_type}")

                chunks = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > settings.MEDIA_MAX_SIZE:
                        raise ValueError(
                            f"媒体超过大小上限：{size} > {settings.MEDIA_MAX_SIZE}"
                        )
                    chunks.append(chunk)
        return b"".join(chunks), content_type


media_storage = MediaStorage()


async def transfer_media(url: str, media_type: str = "media") -> str:
    """模块级便捷函数：转存媒体 URL，返回长期可访问地址。

    复用全局 MediaStorage 单例，供任意任务（图片/视频/文件解析等）直接调用，
    无需自行实例化或持有 media_storage 对象：
        from app.services.media_storage import transfer_media
        long_url = await transfer_media(temp_url, media_type="image")

    Args:
        url: 供应商返回的临时媒体 URL。
        media_type: 媒体类别（media/image/video），用于目录隔离。

    Returns:
        长期可访问 URL（如 /media/image/xxx.jpg）；
        失败时返回 {"error": "TransferFailed", ...} 结构。
    """
    return await media_storage.transfer(url, media_type=media_type)
