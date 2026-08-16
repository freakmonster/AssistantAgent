"""Redis 连接池全局引用。

内部工具（submit_task/get_result/wait_for_task）与 worker 是模块级函数，
无法直接访问 FastAPI 的 `app.state.redis_pool`，因此通过此模块级变量共享。
"""
# 由 main.py 在 lifespan 启动时赋值；内部工具据此访问 Redis 入队/查询。
redis_pool = None
