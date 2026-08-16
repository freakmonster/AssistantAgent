"""记忆服务封装。

管理工作记忆（AsyncPostgresSaver）与长期记忆（AsyncPostgresStore）的初始化与读写。
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings


class MemoryService:
    """记忆服务，封装 PostgreSQL 双轨记忆。"""

    def __init__(self) -> None:
        self.pool: AsyncConnectionPool | None = None
        self.checkpointer: AsyncPostgresSaver | None = None
        self.store: AsyncPostgresStore | None = None

    async def initialize(self) -> None:
        """初始化连接池、工作记忆 checkpointer 与长期记忆 store。"""
        # autocommit=True 使 CREATE INDEX CONCURRENTLY 迁移可执行；Windows 下 min_size 设小避免并发建连问题
        self.pool = AsyncConnectionPool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=10,
            timeout=10.0,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        await self.pool.open()
        self.checkpointer = AsyncPostgresSaver(self.pool)
        await self.checkpointer.setup()
        self.store = AsyncPostgresStore(self.pool)
        await self.store.setup()

    async def close(self) -> None:
        """关闭连接池，释放资源。"""
        if self.pool is not None:
            await self.pool.close()


# 全局记忆服务单例，供 FastAPI 生命周期与 Agent 图共用
memory_service = MemoryService()
