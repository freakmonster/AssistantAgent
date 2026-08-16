"""FastAPI 应用入口。

注意：Windows 下启动需使用 --reload（uvicorn 才会切换到 SelectorEventLoop，
psycopg 异步驱动才能连接 PostgreSQL），即：
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8016 --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import app.models  # noqa: F401  确保所有模型注册到 Base.metadata
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.endpoints import auth, chat, sessions, tasks
from app.core import redis as redis_pool_module
from app.core.config import settings
from app.models.database import Base, engine
from app.services.mcp.host import mcp_host
from app.services.mcp.server_config import (
    build_amap_server,
    build_arxiv_server,
    build_chart_server,
    build_deepwiki_server,
    build_fetch_server,
    build_flight_compare_server,
    build_food_server,
    build_leetcode_server,
    build_t12306_server,
    build_tavily_server,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import get_global_textmap

from app.services.memory_service import memory_service
from app.utils import logger as app_logger
from app.utils.rate_limit import limiter
from app.utils.telemetry import tracer

# 初始化结构化 JSON 日志（必须在任何日志输出前调用）
app_logger.configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：建表 + 初始化记忆/MCP/任务队列，关闭时释放资源。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 幂等迁移：create_all 不会修改已存在的表，这里为旧库补充新列（置顶/软删除）
        await conn.execute(
            text(
                "ALTER TABLE sessions "
                "ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        )
    await memory_service.initialize()
    await mcp_host.initialize(
        {
            "tavily": build_tavily_server(settings.TAVILY_API_KEY),
            "chart": build_chart_server(settings.MODELSCOPE_TOKEN),
            "amap": build_amap_server(settings.MODELSCOPE_TOKEN),
            # "fetch": build_fetch_server(settings.MODELSCOPE_TOKEN), # 使用效果不佳
            "t12306": build_t12306_server(settings.MODELSCOPE_TOKEN),
            # "deepwiki": build_deepwiki_server(settings.MODELSCOPE_TOKEN), # 使用效果不佳
            "flight_compare": build_flight_compare_server(settings.MODELSCOPE_TOKEN),
            "food": build_food_server(),
            "leetcode": build_leetcode_server(settings.MODELSCOPE_TOKEN),
            "arxiv": build_arxiv_server(settings.MODELSCOPE_TOKEN),
        }
    )
    # ARQ 任务队列连接池（供任务入队与状态查询使用）
    app.state.redis_pool = await create_pool(
        RedisSettings.from_dsn(settings.REDIS_URL)
    )
    redis_pool_module.redis_pool = app.state.redis_pool
    yield
    await app.state.redis_pool.aclose()
    await mcp_host.close()
    await memory_service.close()
    await engine.dispose()


app = FastAPI(
    title="超级个人综合型助手 API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# FastAPI 自动埋点（HTTP 请求根 Span）
FastAPIInstrumentor.instrument_app(app)


@app.middleware("http")
async def trace_middleware(request, call_next):
    """请求级追踪中间件：继承/生成 trace_id，注入日志上下文并返回 X-Trace-Id。

    在 FastAPIInstrumentor 之后添加（位于外层，先执行），
    后续 agent_node/tool_node/tool_call 的 Span 均成为本 Span 的子 Span。
    """
    propagator = get_global_textmap()
    parent_ctx = propagator.extract(carrier=request.headers)
    with tracer.start_as_current_span("http_request", context=parent_ctx) as span:
        span_ctx = span.get_span_context()
        trace_id = format(span_ctx.trace_id, "032x")
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        app_logger.bind_request_context(trace_id=trace_id)
        try:
            response = await call_next(request)
        finally:
            # 请求结束清除上下文，避免跨请求串味
            app_logger.clear_request_context()
        response.headers["X-Trace-Id"] = trace_id
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流：默认 100 req/min，按客户端 IP 隔离
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])

# 挂载媒体静态目录：转存后的长期 URL（/media/...）直接访问本地文件
# 目录不存在时自动创建，保证 /media 路由不 404
_media_dir = Path(settings.MEDIA_UPLOAD_DIR)
_media_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    settings.MEDIA_URL_PREFIX,
    StaticFiles(directory=settings.MEDIA_UPLOAD_DIR),
    name="media",
)


@app.get("/api/v1/health")
async def health_check() -> dict:
    """健康检查接口。"""
    return {"status": "ok"}
