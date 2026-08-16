"""对话相关 Schema。"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """对话请求。"""

    session_id: str
    message: str


class ChatResponse(BaseModel):
    """对话响应。"""

    session_id: str
    response: str
