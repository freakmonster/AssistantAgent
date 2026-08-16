"""可靠性与超时控制工具。

封装模型调用与工具调用的超时、重试与熔断逻辑（tenacity + pybreaker）。
"""
import asyncio
from functools import wraps

import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential

# DeepSeek 模型调用熔断器：连续 5 次失败后熔断 60 秒
model_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)


def with_timeout(timeout: float):
    """给异步函数加超时装饰器。"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with asyncio.timeout(timeout):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def retry_model_call(func):
    """模型调用重试：指数退避，最多 3 次。"""

    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )(func)
