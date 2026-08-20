"""OCR 引擎抽象（扫描件 PDF 识别，阶段 9 增强）。

仿照 file_storage.py 的「抽象 + 工厂」范式：OCREngine 抽象 + 百度云 PP-OCRv6
实现；进程级单例复用 access_token（有效期约 30 天），避免每个文件重复换取。
后续扩展或改用其他 OCR 工具，只需新增一个 OCREngine 实现类并调整 get_ocr_engine。

扫码件 PDF 判定的依据：pypdf 仅能提取 PDF 内嵌文本层，扫描件（图片型 PDF）
提取结果为空，此时转 OCR 识别。
"""
import asyncio
import base64
import logging
import time
from abc import ABC, abstractmethod
from io import BytesIO

import httpx
from pypdf import PdfReader

from app.core.config import settings

logger = logging.getLogger(__name__)

# 百度智能云鉴权与 PP-OCRv6 接口地址（文档标题为 PP-OCRv6，请求 URL 为 pp_ocrv5）
TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/pp_ocrv5"
# 百度 OCR 单文件 base64 后大小上限（字节，约原始 7.5MB）
MAX_B64_BYTES = 10 * 1024 * 1024


class OCRError(Exception):
    """OCR 识别相关异常。"""


def needs_ocr(content_type: str, parsed_text: str) -> bool:
    """判定是否需要 OCR：图片类型，或 PDF 且 pypdf 提取为空（扫描件/图片型 PDF）。

    Args:
        content_type: MIME 类型。
        parsed_text: parse_file 已提取的纯文本。

    Returns:
        True 表示需要调用 OCR。
    """
    if content_type.startswith("image/"):
        return True
    if content_type == "application/pdf":
        return not parsed_text.strip()
    return False


def _extract_page_text(data: dict) -> str:
    """从单页 OCR 返回中抽取文本（优先 lines，回退 words）。"""
    lines: list[str] = []
    for page in data.get("page_result") or []:
        page_lines = page.get("lines") or []
        if page_lines:
            lines.extend(page_lines)
        elif page.get("words"):
            lines.append(str(page["words"]))
    return "\n".join(lines)


class OCREngine(ABC):
    """OCR 引擎抽象，各实现遵循同一接口。"""

    @abstractmethod
    async def recognize(self, content: bytes, content_type: str) -> str:
        """对扫描件/图片做 OCR，返回识别纯文本。"""


class BaiduPPOCREngine(OCREngine):
    """百度云 PP-OCRv6 实现：图片走 image 参数，PDF 走 pdf_file 逐页识别。"""

    def __init__(self, api_key: str, secret_key: str, max_pages: int) -> None:
        """初始化凭证与页数上限。

        Args:
            api_key: 百度智能云 API Key。
            secret_key: 百度智能云 Secret Key。
            max_pages: 单份扫描件最多识别页数（逐页调用，控制配额与耗时）。
        """
        self._api_key = api_key
        self._secret_key = secret_key
        self._max_pages = max_pages
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        """换取 access_token，进程内存缓存至过期前 60 秒。"""
        if self._token and time.time() < self._token_expire_at:
            return self._token
        async with self._token_lock:
            # 双检：并发下避免重复换取 token
            if self._token and time.time() < self._token_expire_at:
                return self._token
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._api_key,
                        "client_secret": self._secret_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            if "access_token" not in data:
                raise OCRError(f"获取百度 OCR access_token 失败：{data}")
            self._token = data["access_token"]
            expires_in = int(data.get("expires_in", 2592000))
            self._token_expire_at = time.time() + expires_in - 60
            return self._token

    async def recognize(self, content: bytes, content_type: str) -> str:
        """按类型分发：PDF 走 pdf_file 逐页识别，其余（image/*）走 image 单图识别。"""
        if content_type == "application/pdf":
            return await self._recognize_pdf(content)
        return await self._recognize_image(content)

    async def _recognize_image(self, content: bytes) -> str:
        """单张图片用 image 参数识别，返回文本。"""
        b64 = base64.b64encode(content).decode()
        if len(b64) > MAX_B64_BYTES:
            raise OCRError("图片过大，超出百度 OCR 单图上限（约 7.5MB）")
        token = await self._get_access_token()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OCR_URL}?access_token={token}",
                data={"image": b64},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            if "error_code" in data:
                raise OCRError(
                    f"OCR 识别失败：{data.get('error_code')} {data.get('error_msg')}"
                )
        return _extract_page_text(data)

    async def _recognize_pdf(self, content: bytes) -> str:
        """逐页调用 pdf_file + pdf_file_num 识别 PDF，返回拼接文本。"""
        b64 = base64.b64encode(content).decode()
        if len(b64) > MAX_B64_BYTES:
            raise OCRError("扫描件 PDF 过大，超出百度 OCR 单文件上限（约 7.5MB）")
        pages = len(PdfReader(BytesIO(content)).pages)
        page_count = min(pages, self._max_pages)
        token = await self._get_access_token()

        parts: list[str] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(1, page_count + 1):
                resp = await client.post(
                    f"{OCR_URL}?access_token={token}",
                    data={"pdf_file": b64, "pdf_file_num": str(i)},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error_code" in data:
                    raise OCRError(
                        f"OCR 识别失败：{data.get('error_code')} {data.get('error_msg')}"
                    )
                parts.append(_extract_page_text(data))

        text = "\n".join(p for p in parts if p)
        if pages > self._max_pages:
            text += f"\n\n……（扫描件共 {pages} 页，已识别前 {self._max_pages} 页）……"
        return text


# 进程级单例：access_token 有效期约 30 天，跨 ARQ 任务复用
_engine: OCREngine | None = None
_engine_inited = False


def get_ocr_engine() -> OCREngine | None:
    """按配置构建并缓存 OCR 引擎实例；未启用或密钥缺失返回 None。

    Returns:
        OCR 引擎实例；BAIDU_OCR_ENABLED=False 或密钥缺失时返回 None（扫描件保持现状）。
    """
    global _engine, _engine_inited
    if _engine_inited:
        return _engine
    _engine_inited = True
    if not settings.BAIDU_OCR_ENABLED:
        return None
    if not settings.BAIDU_OCR_API_KEY or not settings.BAIDU_OCR_SECRET_KEY:
        logger.warning("百度 OCR 已启用但缺少 API Key/Secret Key，扫描件将保持空文本")
        return None
    _engine = BaiduPPOCREngine(
        settings.BAIDU_OCR_API_KEY,
        settings.BAIDU_OCR_SECRET_KEY,
        settings.BAIDU_OCR_MAX_PAGES,
    )
    return _engine