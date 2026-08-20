"""语音识别（ASR）音频处理工具。

提供音频转码与时长校验的纯函数，供百度语音识别引擎复用：
- ffmpeg 转码：任意音频格式 → pcm 16k 16bit 单声道
- 时长校验：限制单次语音输入最长时间（默认 30 秒）
"""
import asyncio
import base64
import subprocess
import time

import httpx

from app.core.config import settings

# pcm 参数：百度短语音识别要求 16k 采样率、16bit、单声道
PCM_RATE = 16000
PCM_BYTES_PER_SAMPLE = 2  # 16bit = 2 字节
PCM_CHANNELS = 1
DEFAULT_MAX_SECONDS = 30  # 单次语音输入最长 30 秒


class ASRError(Exception):
    """语音转写相关异常。"""


def convert_to_pcm16k(audio: bytes) -> bytes:
    """用 ffmpeg 把音频（webm/opus/wav 等）转成 pcm 16k 16bit 单声道。

    Args:
        audio: 原始音频字节（ffmpeg 可识别的任意格式）。

    Returns:
        pcm 字节流。

    Raises:
        ASRError: ffmpeg 转码失败时。
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", "pipe:0",
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", str(PCM_RATE), "-ac", str(PCM_CHANNELS),
            "pipe:1",
        ],
        input=audio,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ASRError(f"音频转码失败: {proc.stderr.decode(errors='replace')[:200]}")
    return proc.stdout


def audio_duration_seconds(pcm: bytes) -> float:
    """根据 pcm 字节数计算音频时长（秒）。"""
    return len(pcm) / (PCM_RATE * PCM_BYTES_PER_SAMPLE * PCM_CHANNELS)


def exceeds_max_duration(pcm: bytes, max_seconds: int = DEFAULT_MAX_SECONDS) -> bool:
    """判断 pcm 音频是否超过最大时长。

    Args:
        pcm: pcm 字节流。
        max_seconds: 最大允许时长（秒），默认 30 秒。

    Returns:
        超过返回 True，否则 False（恰好等于 max_seconds 不超时）。
    """
    return audio_duration_seconds(pcm) > max_seconds


# 百度短语音识别极速版 REST 地址与鉴权地址
BAIDU_ASR_URL = "https://vop.baidu.com/pro_api"
BAIDU_OAUTH_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
# 无有效语音内容（静音/无人声）时百度返回的识别错误码，统一视为「未识别到文字」
NO_SPEECH_ERRNOS = {3301, 3307}
# access_token 临过期提前刷新时间（秒）
TOKEN_REFRESH_MARGIN = 60


class BaiduASREngine:
    """百度短语音识别极速版引擎（REST 直调，httpx）。

    复用 BAIDU_API_KEY / BAIDU_SECRET_KEY 换取 access_token，
    进程内缓存并临过期自动刷新（token 有效期约 30 天）。
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expire_at: float = 0.0  # 到期时间戳（秒）
        self._lock = asyncio.Lock()  # 防止并发重复刷新 token

    async def _get_access_token(self) -> str:
        """获取/刷新 access_token（进程内缓存，临过期自动刷新）。"""
        async with self._lock:
            if self._token and time.time() < self._token_expire_at - TOKEN_REFRESH_MARGIN:
                return self._token
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    BAIDU_OAUTH_TOKEN_URL,
                    params={
                        "grant_type": "client_credentials",
                        "client_id": settings.BAIDU_API_KEY,
                        "client_secret": settings.BAIDU_SECRET_KEY,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            token = data.get("access_token")
            if not token:
                raise ASRError(f"获取百度 access_token 失败: {data}")
            expires_in = int(data.get("expires_in", 2592000))
            self._token = token
            self._token_expire_at = time.time() + expires_in
            return token

    async def transcribe(self, audio: bytes, user_id: str) -> str:
        """语音转写：ffmpeg 转码 → 30s 校验 → 调百度极速版 → 返回文本。

        Args:
            audio: 原始音频字节（ffmpeg 可识别的任意格式）。
            user_id: 用户唯一标识（作为百度 cuid，用于 UV 统计）。

        Returns:
            识别文本；未识别到有效语音时返回空字符串。

        Raises:
            ASRError: 转码失败 / 超时长 / 百度识别失败。
        """
        # 1) ffmpeg 转 pcm 16k 16bit 单声道
        pcm = await asyncio.to_thread(convert_to_pcm16k, audio)
        # 2) 30s 时长校验（后端兜底）
        if exceeds_max_duration(pcm, settings.BAIDU_ASR_MAX_SECONDS):
            raise ASRError(f"语音时长超过 {settings.BAIDU_ASR_MAX_SECONDS} 秒限制")
        # 3) 调百度短语音识别极速版（JSON 方式上传）
        token = await self._get_access_token()
        payload = {
            "format": "pcm",
            "rate": 16000,
            "channel": 1,
            "cuid": user_id,
            "dev_pid": settings.BAIDU_ASR_DEV_PID,
            "token": token,
            "len": len(pcm),
            "speech": base64.b64encode(pcm).decode("ascii"),
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(BAIDU_ASR_URL, json=payload)
                resp.raise_for_status()
                result = resp.json()
        except httpx.HTTPError as exc:
            raise ASRError(f"调用百度识别接口失败: {exc}") from exc
        if result.get("err_no") == 0 and result.get("result"):
            return result["result"][0]
        if result.get("err_no") in NO_SPEECH_ERRNOS:
            return ""  # 未识别到有效文字，作为空文本返回
        raise ASRError(f"百度识别失败: {result}")
