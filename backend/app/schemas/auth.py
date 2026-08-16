"""认证相关 Schema。"""
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """注册请求。"""

    email: str
    password: str


class LoginRequest(BaseModel):
    """登录请求。"""

    email: str
    password: str


class TokenResponse(BaseModel):
    """Token 响应。"""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """用户信息响应。"""

    id: str
    email: str
    is_active: bool
