"""会话相关 Schema。"""
from pydantic import BaseModel


class SessionCreate(BaseModel):
    """创建会话请求。"""

    title: str | None = None


class SessionUpdate(BaseModel):
    """更新会话请求（重命名等，字段可选）。"""

    title: str | None = None


class SessionResponse(BaseModel):
    """会话响应。"""

    id: str
    title: str | None
    thread_id: str
    is_pinned: bool = False
    created_at: str
    updated_at: str
    message_count: int = 0
