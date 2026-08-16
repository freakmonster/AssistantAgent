"""限流配置与入口限流器。"""
import time

import redis.asyncio as aioredis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# 入口限流器（按客户端 IP，默认 100 req/min）
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# 每个工具的限流配置：每分钟请求数（rpm）与每分钟 token 数（tpm）
RATE_LIMITS = {
    "tavily_search": {"rpm": 10, "tpm": 5000},
    "tavily_extract": {"rpm": 5, "tpm": 2000},
    "get_current_time": {"rpm": 60, "tpm": 60000},
}

# 工具级限流 Redis 客户端（惰性初始化）
_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """返回共享的异步 Redis 客户端。"""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def check_tool_rate_limit(tool_name: str, user_id: str) -> bool:
    """工具级限流（按用户隔离的固定窗口）。

    未在 RATE_LIMITS 中配置的工具不限制；超限返回 False。
    """
    limit = RATE_LIMITS.get(tool_name)
    if not limit:
        return True
    rpm = limit["rpm"]
    window = int(time.time()) // 60
    key = f"ratelimit:{tool_name}:{user_id}:{window}"
    redis = _get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    return count <= rpm
