"""数据库连接与会话管理。

基于 SQLAlchemy 2.0 异步引擎，复用 psycopg3 异步驱动。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _build_sqlalchemy_url(url: str) -> str:
    """将 psycopg 连接串转换为 SQLAlchemy 异步驱动 URL。"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类，供各业务模型继承。"""


engine = create_async_engine(
    _build_sqlalchemy_url(settings.DATABASE_URL),
    echo=False,
    pool_pre_ping=True,
    # 数据库层超时：单条 SQL 超过 SQL_TIMEOUT 秒即终止（超时层级中的最内层）
    connect_args={"options": f"-c statement_timeout={settings.SQL_TIMEOUT * 1000}"},
)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供异步数据库会话。"""
    async with async_session_factory() as session:
        yield session
