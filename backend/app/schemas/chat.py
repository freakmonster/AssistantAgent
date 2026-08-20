"""对话相关 Schema。"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """对话请求。"""

    session_id: str
    message: str
    attachments: list[str] = []  # 已上传文件的 file_id 列表（阶段 9）
    model: str | None = None  # 前端选择的模型 id；未指定时后端回退 DEFAULT_MODEL


class ChatResponse(BaseModel):
    """对话响应。"""

    session_id: str
    response: str
