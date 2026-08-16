"""图片生成内部工具（智谱 CogView-3-Flash）。

智谱图片生成 API 为同步接口：一次 POST /paas/v4/images/generations 直接返回
图片 URL，无需任务提交与轮询，因此以同步内部工具接入（区别于视频的异步队列）。

- 耗时：standard 约 5-10 秒，hd 约 20 秒，均由本工具同步等待完成。
- 返回智谱临时 URL（约 30 天有效）。转存逻辑（media_storage.transfer_media）已注释停用，
  直接存临时 URL 避免本地磁盘增长；如需恢复长期存储，取消下方注释并按需加 TTL/对象存储。
"""
import logging

import httpx
from langchain_core.tools import tool

from app.core.config import settings
# 转存功能已注释停用（直接返回临时 URL）；如需恢复请取消此导入
# from app.services.media_storage import transfer_media

logger = logging.getLogger(__name__)

# 生成图片的接口地址（智谱开放平台）
IMAGES_GENERATIONS_URL = f"{settings.ZHIPU_BASE_URL}/api/paas/v4/images/generations"


@tool
async def generate_image(prompt: str, quality: str = "standard", size: str = "1280x1280") -> str:
    """根据文本描述生成一张图片，返回图片 URL（智谱临时 URL，约 30 天有效）。

    适用场景：
    - 用户需要配图、插画、海报、示意图等视觉内容
    - 用户要求「画一张」「生成图片」等绘图需求

    不适用场景：
    - 生成视频（请用 submit_task 提交视频任务）
    - 生成图表/数据可视化（请用图表工具）

    Args:
        prompt: 图片内容的文本描述（越具体，生成效果越好）。
        quality: 图像质量，"hd"（更精细，约 20 秒）或 "standard"（快速，约 5-10 秒）。
        size: 图片尺寸，如 "1280x1280"。

    Returns:
        图片 URL（智谱临时地址，约 30 天有效）；失败时返回 {"error": ..., "message": ...} 结构。
    """
    headers = {
        "Authorization": f"Bearer {settings.ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "cogview-3-flash",
        "prompt": prompt,
        "quality": quality,
        "size": size,
    }
    try:
        # 图片生成是同步接口，最长约 20 秒，给足超时余量
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(IMAGES_GENERATIONS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        urls = data.get("data") or []
        if not urls or not urls[0].get("url"):
            logger.error("智谱图片生成返回异常：%s", resp.text)
            return '{"error": "ImageGenerateFailed", "message": "图片生成失败，返回结果缺少 URL"}'
        temp_url = urls[0]["url"]
        logger.info("图片生成成功 quality=%s size=%s url=%s", quality, size, temp_url)

        # 转存功能已注释停用：直接返回智谱临时 URL（约 30 天有效），避免本地磁盘增长。
        # 如需恢复转存，取消上方 import 并启用以下逻辑：
        # long_url = await transfer_media(temp_url, media_type="image")
        # try:
        #     json.loads(long_url)  # 转存失败返回的是 {"error": ...} JSON
        #     logger.warning("图片转存失败，降级返回临时 URL：%s", temp_url)
        #     return temp_url
        # except json.JSONDecodeError:
        #     return long_url
        return temp_url
    except httpx.HTTPStatusError as exc:
        logger.error("智谱图片生成 HTTP 错误：%s", exc.response.text)
        return f'{{"error": "ImageGenerateFailed", "message": "图片生成失败：{exc.response.status_code}"}}'
    except httpx.TimeoutException:
        logger.error("智谱图片生成超时")
        return '{"error": "Timeout", "message": "图片生成超时，请稍后重试"}'
    except Exception as exc:
        logger.error("图片生成异常：%s", exc)
        return '{"error": "ImageGenerateFailed", "message": "图片生成失败"}'


__all__ = ["generate_image"]
