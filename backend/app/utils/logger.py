"""structlog 结构化 JSON 日志配置。

统一应用日志为 JSON 输出，并通过 contextvars 在每条日志中自动注入
trace_id / user_id / session_id 等请求级上下文字段。
"""
import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """初始化 structlog，输出 JSON 到标准输出。

    处理链：合并 contextvars 上下文 -> 注入日志级别 -> 时间戳 -> 堆栈/异常 -> JSON 渲染。
    """
    # 先配置标准库根 logger，确保 structlog（stdlib LoggerFactory）有输出 handler
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout)

    # 降低第三方库日志级别：httpx / MCP SDK 会在 INFO 级打印每条 HTTP 请求与 SSE 重连，
    # 导致启动后日志刷屏，这里统一降到 WARNING 只保留真正错误；应用自身 structlog 输出不受影响。
    for _name in ("httpx", "httpcore", "mcp", "langchain_mcp_adapters"):
        logging.getLogger(_name).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    """获取结构化日志记录器。"""
    return structlog.get_logger(name)


def bind_request_context(
    trace_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """绑定当前请求的 trace_id/user_id/session_id 到上下文。

    仅绑定非空字段，多次调用（如中间件绑 trace_id、端点绑 user_id）互不覆盖。

    Args:
        trace_id: 追踪 ID。
        user_id: 用户 ID。
        session_id: 会话 ID。
    """
    ctx: dict = {}
    if trace_id is not None:
        ctx["trace_id"] = trace_id
    if user_id is not None:
        ctx["user_id"] = user_id
    if session_id is not None:
        ctx["session_id"] = session_id
    if ctx:
        structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    """清除当前请求绑定的上下文（请求结束时调用，避免跨请求串味）。"""
    structlog.contextvars.clear_contextvars()
