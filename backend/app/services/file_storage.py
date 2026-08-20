"""文件存储抽象（本地 + 七牛云 Kodo 对象存储）。

为媒体转存 / 文件上传提供统一存储接口：save / load / delete / url。
本地实现存 file_uploads/ 目录；对象存储（七牛 Kodo）按同一接口实现，
切换存储只换实现类（FILE_UPLOAD_STORAGE 配置）。
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from qiniu import Auth, BucketManager, put_data

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileStorage(ABC):
    """文件存储抽象。本地实现与对象存储实现遵循同一接口。"""

    @abstractmethod
    async def save(self, key: str, content: bytes) -> str:
        """保存文件内容到 key，返回存储路径。

        Args:
            key: 存储键（本地为相对路径，对象存储为 bucket/key）。
            content: 文件二进制内容。

        Returns:
            存储路径（与 load/delete 的 key 一致）。
        """

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """按 key 读取文件内容。"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """按 key 删除文件。"""

    @abstractmethod
    def url(self, key: str) -> str:
        """返回 key 对应可公开访问的 URL（本地为 /media 前缀，对象存储为 CDN 域名）。"""


class LocalFileStorage(FileStorage):
    """本地文件系统实现：存 file_uploads/ 目录，按用户/类型隔离目录。"""

    def __init__(self, base_dir: str = "file_uploads") -> None:
        """初始化本地存储根目录。

        Args:
            base_dir: 存储根目录（相对当前工作目录或绝对路径）。
        """
        self.base_dir = Path(base_dir)

    def _resolve(self, key: str) -> Path:
        """把相对 key 解析为绝对路径，并防止路径穿越。"""
        # 规范化后必须仍位于 base_dir 内，杜绝 ../ 越权读写
        path = (self.base_dir / key).resolve()
        root = self.base_dir.resolve()
        if not str(path).startswith(str(root)):
            raise ValueError(f"非法的存储路径：{key}")
        return path

    async def save(self, key: str, content: bytes) -> str:
        """保存文件，父目录自动创建，返回相对路径 key。"""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return key

    async def load(self, key: str) -> bytes:
        """读取文件内容。"""
        return self._resolve(key).read_bytes()

    async def delete(self, key: str) -> None:
        """删除文件（不存在时静默忽略）。"""
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def url(self, key: str) -> str:
        """本地模式返回 /media 前缀 URL（由 main.py 静态挂载提供访问）。"""
        return f"{settings.MEDIA_URL_PREFIX}/{key}"


class KodoFileStorage(FileStorage):
    """七牛云 Kodo 对象存储实现。

    底层使用官方 qiniu SDK（同步 API），通过 asyncio.to_thread 包装避免
    阻塞事件循环。空间为公开权限时，url()/load() 直出裸 CDN URL 即可访问；
    若日后改回私有空间，仅需将 url()/load() 改为 private_download_url 签名。
    """

    def __init__(self, access_key: str, secret_key: str, bucket: str, domain: str) -> None:
        """初始化七牛凭证与空间配置。

        Args:
            access_key: 七牛 AccessKey。
            secret_key: 七牛 SecretKey。
            bucket: 空间名。
            domain: 下载域名（去掉协议/尾斜杠后拼接 URL）。
        """
        self.auth = Auth(access_key, secret_key)
        self.bucket_manager = BucketManager(self.auth)
        self.bucket = bucket
        self.domain = domain.rstrip("/")

    async def save(self, key: str, content: bytes) -> str:
        """上传文件到 bucket（表单直传），返回 key。"""
        token = self.auth.upload_token(self.bucket, key)

        def _do_upload() -> None:
            nonlocal token, key, content
            _, info = put_data(token, key, content)
            if info.status_code != 200:
                raise RuntimeError(f"七牛上传失败：HTTP {info.status_code}，{info.text_body}")

        await asyncio.to_thread(_do_upload)
        return key

    async def load(self, key: str) -> bytes:
        """从公开 CDN URL 下载文件内容（分片并发）。

        分片并发链路当前仅在 persist 模式（FILE_PARSE_MODE=persist）解析回读
        或历史附件下载时走到；transient 模式（默认）不转存、不调用本方法。
        单连接受限于跨境链路速度，多片 Range 并发可显著提速；若 CDN 不支持
        Range（返回 200 全量而非 206），自动回退为单连接全量下载。
        """
        url = self.url(key)
        chunks_count = max(1, settings.FILE_DOWNLOAD_CHUNKS)
        try:
            async with httpx.AsyncClient(timeout=settings.FILE_DOWNLOAD_TIMEOUT) as client:
                # 先 HEAD 取大小，失败则回退单连接
                size = None
                try:
                    head = await client.head(url)
                    head.raise_for_status()
                    size = int(head.headers["Content-Length"])
                except (httpx.HTTPError, KeyError, ValueError):
                    size = None

                if size is None or chunks_count <= 1:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.content

                # 按片并发 Range 下载
                part = size // chunks_count
                bounds = [
                    (i * part, (i + 1) * part - 1 if i < chunks_count - 1 else size - 1)
                    for i in range(chunks_count)
                ]

                async def _fetch(start: int, end: int) -> tuple[int, bytes]:
                    resp = await client.get(
                        url, headers={"Range": f"bytes={start}-{end}"}
                    )
                    resp.raise_for_status()
                    return resp.status_code, resp.content

                results = await asyncio.gather(
                    *[_fetch(s, e) for s, e in bounds]
                )
                if all(status == 206 for status, _ in results):
                    return b"".join(content for _, content in results)
                # CDN 忽略 Range 返回全量：取首片结果（通常为完整内容）
                return results[0][1]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"七牛下载失败：{key}，{exc}") from exc

    async def delete(self, key: str) -> None:
        """删除对象；对象不存在（612）视为成功，其余失败记录日志。"""

        def _do_delete() -> None:
            nonlocal key
            _, info = self.bucket_manager.delete(self.bucket, key)
            if info.status_code != 200 and info.status_code != 612:
                logger.warning("七牛删除对象失败 key=%s http=%s", key, info.status_code)

        await asyncio.to_thread(_do_delete)

    def url(self, key: str) -> str:
        """返回公开可访问的裸 URL（无签名、无过期）。"""
        return f"{self.domain}/{key}"
