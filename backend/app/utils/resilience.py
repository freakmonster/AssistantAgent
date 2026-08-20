"""可靠性与超时控制工具。

封装模型调用的超时、重试与熔断逻辑（tenacity + 自研异步熔断器）。
熔断器按模型 id 隔离：单个模型连续失败不影响其他模型的调用。
"""
import asyncio
import time
from functools import wraps

from tenacity import retry, stop_after_attempt, wait_exponential


class CircuitOpenError(Exception):
    """熔断器打开时抛出的异常，供上层识别为「可降级」的模型故障。"""


class AsyncCircuitBreaker:
    """进程内、按模型隔离的极简异步熔断器。

    语义：
    - 连续 fail_max 次失败后进入 open 状态，持续 reset_timeout 秒。
    - open 期间直接抛 CircuitOpenError，快速失败，不再发起真实调用。
    - 冷却结束后的首次调用恢复正常（closed），成功则计数清零、失败则重新累积。

    说明：状态读写均发生在单个 await 的前后，无并发交错，故不加锁。
    """

    def __init__(self, fail_max: int = 5, reset_timeout: float = 60):
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._fail_count = 0
        self._state = "closed"  # closed / open
        self._opened_at = 0.0

    async def call(self, func, *args, **kwargs):
        """按熔断规则执行异步 func，成功返回结果，失败按规则计数并抛出原始异常。"""
        self._ensure_ready()
        try:
            result = await func(*args, **kwargs)
        except BaseException:
            self._on_failure()
            raise
        self._on_success()
        return result

    def _ensure_ready(self) -> None:
        if self._state != "open":
            return
        if time.monotonic() - self._opened_at < self._reset_timeout:
            raise CircuitOpenError(f"模型熔断已打开，{self._reset_timeout:.0f} 秒后重试")
        self._fail_count = 0
        self._state = "closed"

    def _on_success(self) -> None:
        self._fail_count = 0
        self._state = "closed"

    def _on_failure(self) -> None:
        self._fail_count += 1
        if self._fail_count >= self._fail_max:
            self._state = "open"
            self._opened_at = time.monotonic()


# 模型熔断参数：连续 5 次失败熔断 60 秒（与原全局熔断器保持一致）
_BREAKER_FAIL_MAX = 5
_BREAKER_RESET_TIMEOUT = 60.0

# 按模型 id 缓存熔断器实例，避免重复创建
_breakers: dict[str, AsyncCircuitBreaker] = {}


def get_model_breaker(model_id: str) -> AsyncCircuitBreaker:
    """返回指定模型的熔断器（懒创建 + 缓存），实现按模型隔离。"""
    breaker = _breakers.get(model_id)
    if breaker is None:
        breaker = AsyncCircuitBreaker(_BREAKER_FAIL_MAX, _BREAKER_RESET_TIMEOUT)
        _breakers[model_id] = breaker
    return breaker


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
    """模型调用重试：指数退避，最多 2 次尝试。"""

    return retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )(func)