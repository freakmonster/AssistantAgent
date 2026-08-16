"""语音识别（ASR）音频处理工具。

提供音频转码与时长校验的纯函数，供百度语音识别引擎复用：
- ffmpeg 转码：任意音频格式 → pcm 16k 16bit 单声道
- 时长校验：限制单次语音输入最长时间（默认 30 秒）
"""
import subprocess

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
