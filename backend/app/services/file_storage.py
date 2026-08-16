"""文件存储抽象（本地 + 预留对象存储）。

为媒体转存 / 文件上传提供统一存储接口：save / load / delete。
本地实现存 uploads/ 目录，返回相对路径作为 key；对象存储（MinIO/OSS）
留待阶段 8 部署时按同一接口实现，切换存储只换实现类。
"""
from abc import ABC, abstractmethod
from pathlib import Path


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


class LocalFileStorage(FileStorage):
    """本地文件系统实现：存 uploads/ 目录，按用户/类型隔离目录。"""

    def __init__(self, base_dir: str = "uploads") -> None:
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
