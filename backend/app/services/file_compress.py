"""文件附件 LLM 语义压缩服务。

将超长解析文本交给压缩模型做忠实摘要，替换字符级截断以减少关键信息损失。

设计要点：
- 仅在超过注入上限（FILE_TEXT_MAX_CHARS）时才触发压缩，短文本原样返回；
- 按压缩模型的上下文窗口动态计算单片安全上限，超限时分片并发压缩后按序拼接；
- 压缩失败/关闭时降级为头尾字符截断，保证解析结果始终可落库。
"""
import asyncio
import math
import logging

from app.core.config import settings
from app.prompts.file_compress import build_file_compress_prompt
from app.utils.llm import build_chat_llm

logger = logging.getLogger(__name__)

# 结构化数据类 MIME：内容以键值/表格为主，走 LLM 语义压缩收益低且易破坏结构，
# 直接字符截断保持原始数据，不调用 LLM
_STRUCTURED_DATA_TYPES = {
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
}


def _char_truncate(text: str, max_chars: int) -> str:
    """字符级截断（压缩降级用），保留头 3/4 + 尾 1/4。

    与 agent_service._truncate_text 采用相同算法，避免循环依赖。
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = text[: max_chars * 3 // 4]
    tail = text[-(max_chars // 4):]
    return f"{head}\n\n……（内容过长已截断，完整共 {len(text)} 字符）……\n\n{tail}"


def _extract_content(message) -> str:
    """从 LLM 返回消息中提取纯文本内容。"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content)


def _build_llm():
    """按配置构建压缩模型实例，密钥/base_url 未单独配置时回退 DeepSeek。"""
    base_url = settings.FILE_COMPRESS_BASE_URL or settings.DEEPSEEK_BASE_URL
    api_key = settings.FILE_COMPRESS_API_KEY or settings.DEEPSEEK_API_KEY
    return build_chat_llm(settings.FILE_COMPRESS_MODEL, api_key, base_url)


async def _compress_chunk(
    llm, text: str, target_chars: int, chunk_index: int, chunk_total: int
) -> str:
    """压缩单片文本，返回该片摘要。"""
    prompt = build_file_compress_prompt(
        text, target_chars, chunk_index=chunk_index, chunk_total=chunk_total
    )
    # 显式超时：压缩模型偶发慢响应时快速失败，交由外层 except 降级为字符截断。
    # asyncio.wait_for 超时抛出 asyncio.TimeoutError（Exception 子类），可被外层 except Exception 捕获。
    message = await asyncio.wait_for(
        llm.ainvoke(prompt),
        timeout=settings.FILE_COMPRESS_TIMEOUT,
    )
    return _extract_content(message).strip()


def _split_text(text: str, chunk_count: int) -> list[str]:
    """将文本按字符等分为 chunk_count 片，尽量在换行或句号处切分。"""
    if chunk_count <= 1:
        return [text]
    length = len(text)
    chunk_size = math.ceil(length / chunk_count)
    chunks: list[str] = []
    start = 0
    while start < length:
        end = min(start + chunk_size, length)
        # 向后扫描，尽量对齐换行或句号，避免切断句子（最多回退 200 字符）
        if end < length:
            for back in range(min(200, end - start)):
                if text[end - back] in "\n。！？":
                    end -= back
                    break
        chunks.append(text[start:end])
        start = end
    return chunks


async def compress_file_text(text: str, content_type: str) -> str:
    """对解析文本按需做 LLM 语义压缩。

    Args:
        text: 解析出的全文。
        content_type: 文件 MIME 类型（当前仅占位，后续可据类型微调提示词）。

    Returns:
        压缩后的文本；未触发压缩或压缩失败时返回（降级后的）原文。
    """
    target_chars = settings.FILE_TEXT_MAX_CHARS
    # 未启用或未超阈值：原样返回，不调用 LLM
    if not settings.FILE_COMPRESS_ENABLED or len(text) <= target_chars:
        return text

    # 结构化数据（JSON/CSV/XLSX）不进 LLM：键值/表格数据语义压缩收益低且易破坏结构
    if content_type in _STRUCTURED_DATA_TYPES:
        return _char_truncate(text, target_chars)

    window = settings.FILE_COMPRESS_MODEL_WINDOWS.get(
        settings.FILE_COMPRESS_MODEL, 1_000_000
    )
    safe_chars = int(
        window * settings.FILE_COMPRESS_WINDOW_RATIO * settings.FILE_COMPRESS_CHARS_PER_TOKEN
    )

    try:
        llm = _build_llm()
        # 单次压缩（绝大多数 20MB 内文件，1M 窗口下无需分片）
        if len(text) <= safe_chars:
            return await _compress_chunk(llm, text, target_chars, 1, 1)

        # 分片并发压缩：超出单片上限时计算片数，必要时先粗截断到最大片数容量内
        max_capacity = safe_chars * settings.FILE_COMPRESS_MAX_CHUNKS
        source = text
        if len(source) > max_capacity:
            source = _char_truncate(source, max_capacity)
        chunk_count = min(
            settings.FILE_COMPRESS_MAX_CHUNKS,
            max(1, math.ceil(len(source) / safe_chars)),
        )
        chunks = _split_text(source, chunk_count)
        summaries = await asyncio.gather(
            *[
                _compress_chunk(llm, chunk, target_chars, idx + 1, chunk_count)
                for idx, chunk in enumerate(chunks)
            ]
        )
        # 按片序直接拼接，不做二次合并
        return "\n\n".join(s for s in summaries if s)
    except Exception as exc:  # noqa: BLE001 - 降级路径：任何压缩异常都回退字符截断
        logger.warning("附件 LLM 压缩失败，降级为字符截断 err=%s", exc)
        return _char_truncate(text, target_chars)