"""语音转写接口。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.models.user import User
from app.services.asr_engine import ASRError, BaiduASREngine

router = APIRouter()

# 进程级单例：复用 access_token 缓存，避免每次请求重复换取
_engine = BaiduASREngine()


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """同步转写：上传音频 → 百度 ASR → 返回文本（仅供回填输入框，不触发对话）。"""
    audio = await file.read()
    try:
        text = await _engine.transcribe(audio, str(current_user.id))
    except ASRError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"text": text}