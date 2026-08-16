"""消息相关 Schema。"""

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """历史消息响应（用于前端加载会话历史）。"""

    id: str
    role: str
    content: str | None
    tool_calls: list | None
    attachments: list | None
    created_at: str
