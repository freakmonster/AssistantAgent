"""Agent 工具定义。

提供内部工具 get_current_time、save_memory、query_memory，
以及异步任务通用工具 submit_task、get_result、wait_for_task。
阶段 3 起，这些内部工具与 MCP 工具统一由 MCPHost 管理。
"""
import asyncio
import json
import uuid
from datetime import datetime

from arq.jobs import Job, JobStatus
from langchain_core.tools import tool
from langgraph.config import get_config, get_store

from app.core import redis as redis_pool_module
from app.tasks.registry import ASYNC_TASKS


@tool
def get_current_time() -> str:
    """获取当前系统时间。

    适用场景：
    - 用户询问当前时间、日期或星期
    - 需要时间戳进行计算或记录的场合

    不适用场景：
    - 用户询问天气、新闻等非时间类信息

    Returns:
        格式化后的当前时间字符串，例如 "2026-08-12 14:30:00"
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
async def save_memory(content: str) -> str:
    """保存需要长期记住的用户信息。

    适用场景：
    - 用户明确告知姓名、偏好、习惯等应跨会话记住的信息
    - 对话中产生的重要事实或结论

    不适用场景：
    - 临时性、一次性的对话内容

    Args:
        content: 需要记住的内容，用一句话概括。

    Returns:
        保存结果说明。
    """
    try:
        store = get_store()
        config = get_config()
    except Exception:
        return "记忆未保存（长期记忆存储未配置）"

    if store is None:
        return "记忆未保存（长期记忆存储未配置）"

    user_id = str(config.get("configurable", {}).get("user_id", "default"))
    namespace = ("user_" + user_id, "memories")
    key = f"mem_{uuid.uuid4().hex[:8]}"
    await store.aput(namespace, key, {"content": content})
    return f"已记住：{content}"


@tool
async def query_memory(query: str) -> str:
    """检索被压缩的历史对话摘要。

    适用场景：
    - 需要回忆早期对话中已被摘要压缩的具体信息（如用户之前提过的名字、偏好、任务）

    不适用场景：
    - 当前对话中已经明确存在、无需回忆的信息

    Args:
        query: 检索关键词或问题。

    Returns:
        检索到的相关历史摘要文本。
    """
    try:
        store = get_store()
        config = get_config()
    except Exception:
        return "无法检索历史摘要（长期记忆存储未配置）"

    if store is None:
        return "无法检索历史摘要（长期记忆存储未配置）"

    user_id = str(config.get("configurable", {}).get("user_id", "default"))
    namespace = ("user_" + user_id, "summaries")
    items = await store.asearch(namespace, limit=20)
    if not items:
        return "暂无历史摘要"

    # 无向量检索时的降级方案：按关键词做简单过滤
    keywords = [w for w in query.replace("，", " ").replace(",", " ").split() if w]
    matched = []
    for item in items:
        value = item.value if isinstance(item.value, dict) else {"content": str(item.value)}
        content = value.get("content", str(value))
        if not keywords or any(kw in content for kw in keywords):
            matched.append(content)

    if not matched:
        return "未检索到与问题相关的历史摘要"

    return "\n".join(f"- {c}" for c in matched[:5])


def _runtime_context() -> tuple[str, str]:
    """从 LangGraph configurable 提取 user_id 与 session_id。"""
    try:
        config = get_config()
    except Exception:
        return "default", ""
    cfg = config.get("configurable", {})
    user_id = str(cfg.get("user_id", "default"))
    session_id = str(cfg.get("session_id", ""))
    return user_id, session_id


@tool
async def submit_task(task_type: str, prompt: str) -> str:
    """提交一个异步耗时任务（视频生成等），立即返回任务 ID 或结果。

    适用场景：
    - 需要生成视频等耗时较长的媒体任务，避免阻塞当前对话
    - 当前仅支持 task_type="video_cogvideox_flash"，参数为 prompt（视频文本描述）

    不适用场景：
    - 能同步快速完成的操作（查时间、查记忆、联网搜索等）

    Args:
        task_type: 任务类型，当前仅支持 "video_cogvideox_flash"。
        prompt: 任务的文本描述（如视频画面描述）。

    Returns:
        JSON 字符串：快任务直接返回结果；慢任务返回 {"type":"task","task_id":...}。
        拿到 task_id 后应立即停止，把 task_id 告知用户（由前端轮询结果），
        不要在同一轮对话中反复调用 get_result 轮询。
    """
    meta = ASYNC_TASKS.get(task_type)
    if meta is None:
        return json.dumps(
            {"error": "UnknownTaskType", "message": f"未知任务类型 {task_type}"},
            ensure_ascii=False,
        )
    if redis_pool_module.redis_pool is None:
        return json.dumps(
            {"error": "TaskQueueUnavailable", "message": "任务队列未就绪"},
            ensure_ascii=False,
        )

    user_id, session_id = _runtime_context()
    if not session_id:
        return json.dumps(
            {"error": "MissingSession", "message": "缺少会话上下文，无法落库"},
            ensure_ascii=False,
        )

    job = await redis_pool_module.redis_pool.enqueue_job(
        meta["worker"], user_id, session_id, prompt
    )
    if job is None:
        return json.dumps(
            {"error": "TaskExists", "message": "相同任务已存在"},
            ensure_ascii=False,
        )

    try:
        result = await job.result(timeout=meta["fast_timeout"])
        return json.dumps(result, ensure_ascii=False, default=str)
    except asyncio.TimeoutError:
        return json.dumps(
            {
                "type": "task",
                "task_id": job.job_id,
                "status": "running",
                "message": "任务已提交，正在后台生成。请直接告知用户任务已开始及 task_id，不要继续轮询。",
            },
            ensure_ascii=False,
        )


@tool
async def get_result(task_id: str) -> str:
    """查询异步任务的执行状态与结果（主要用于前端/用户侧轮询）。

    适用场景：
    - 需要单次确认某个 task_id 是否已完成

    不适用场景：
    - 不要在同一轮对话中反复调用本工具轮询，那会导致无限循环
    - 需要阻塞等待结果喂给下游工具时，请改用 wait_for_task（一次）

    Args:
        task_id: 由 submit_task 返回的任务 ID。

    Returns:
        JSON 字符串：completed 含 result；未完成时含 status 与提示。
    """
    if redis_pool_module.redis_pool is None:
        return json.dumps(
            {"error": "TaskQueueUnavailable", "message": "任务队列未就绪"},
            ensure_ascii=False,
        )

    job = Job(task_id, redis_pool_module.redis_pool)
    status = await job.status()
    if status == JobStatus.complete:
        info = await job.result_info()
        return json.dumps(
            {"status": "completed", "result": info.result if info else None},
            ensure_ascii=False,
            default=str,
        )
    return json.dumps(
        {
            "status": status.value,
            "message": "任务尚未完成。请停止轮询，使用 wait_for_task 阻塞等待一次，或告知用户稍后查看结果。",
        },
        ensure_ascii=False,
    )


@tool
async def wait_for_task(task_id: str, timeout: int = 60) -> str:
    """阻塞等待异步任务完成，拿到最终结果。

    适用场景：
    - 已通过 submit_task 拿到 task_id，且结果需作为下游工具的入参继续处理

    不适用场景：
    - 结果仅需展示给用户时，请直接告知用户任务进行中（由前端轮询），不要阻塞等待

    Args:
        task_id: 由 submit_task 返回的任务 ID。
        timeout: 最长等待秒数，默认 60。

    Returns:
        JSON 字符串：completed 含 result；超时返回 timeout 状态（超时后停止，不要重试）。
    """
    if redis_pool_module.redis_pool is None:
        return json.dumps(
            {"error": "TaskQueueUnavailable", "message": "任务队列未就绪"},
            ensure_ascii=False,
        )

    job = Job(task_id, redis_pool_module.redis_pool)
    try:
        result = await job.result(timeout=timeout)
        return json.dumps(
            {"status": "completed", "result": result},
            ensure_ascii=False,
            default=str,
        )
    except asyncio.TimeoutError:
        return json.dumps(
            {"status": "timeout", "message": "等待超时，请稍后查询"},
            ensure_ascii=False,
        )


# 内部工具列表（非 MCP 工具）
INTERNAL_TOOLS = [
    get_current_time,
    save_memory,
    query_memory,
    submit_task,
    get_result,
    wait_for_task,
]
