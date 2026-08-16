"""Agent 推理节点。

负责调用 LLM 进行思考，生成回复或工具调用请求，并在推理前检索长期记忆。
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.config import get_store

from app.core.config import settings
from app.prompts import SYSTEM_PROMPT
from app.services.mcp.host import mcp_host
from app.utils import logger as app_logger
from app.utils.resilience import model_breaker, retry_model_call, with_timeout
from app.utils.telemetry import tracer

logger = app_logger.get_logger(__name__)

# DeepSeek 模型实例，通过 langchain-openai 的 ChatOpenAI 兼容接口接入
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
    temperature=0,
)


@with_timeout(settings.MODEL_TIMEOUT)
@model_breaker
@retry_model_call
async def _invoke_llm(llm_with_tools, messages, user_id):
    """带超时/熔断/重试的模型调用，并记录缓存命中指标。

    通过 user 字段上报 user_id，实现 DeepSeek 用户级隔离（内容安全/缓存/并发配额）。
    """
    response = await llm_with_tools.ainvoke(messages, user=user_id)
    usage = getattr(response, "usage_metadata", None) or {}
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    if hit is not None and miss is not None:
        logger.info("缓存命中监控", hit_tokens=hit, miss_tokens=miss)
    return response


ANCHOR_INTERVAL = 10  # 锚点注入间隔（步）


def _extract_goal(messages: list) -> str:
    """提取用户核心目标（第一条人类消息内容）。"""
    for m in messages:
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            return m.content.strip()
    return ""


def _get_available_tools() -> list:
    """获取当前可用工具列表（内部工具已在导入时注册，MCP 工具在 initialize 后追加）。"""
    return mcp_host.get_tools()


@tracer.start_as_current_span("agent_node")
async def agent_node(state: dict, config: RunnableConfig) -> dict:
    """调用 LLM 生成回复或工具调用。

    Args:
        state: 当前图状态，含 messages 字段。
        config: 运行时配置，含 thread_id、user_id 等。

    Returns:
        包含新生成消息的状态更新字典。
    """
    # 检索长期记忆，作为上下文注入
    memory_context = await _retrieve_memories(config)

    # 动态绑定当前可用工具
    llm_with_tools = llm.bind_tools(_get_available_tools())

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # 注入历史对话摘要（会话压缩产物）
    summary = state.get("summary", "")
    if summary:
        messages.append(SystemMessage(content=f"历史对话摘要：\n{summary}"))

    if memory_context:
        messages.append(SystemMessage(content=f"已知用户信息：\n{memory_context}"))

    # 步数追踪与锚点注入：每 10 步重申核心目标，防止长会话漂移
    next_step = state.get("step_count", 0) + 1
    if next_step > 1 and next_step % ANCHOR_INTERVAL == 0:
        goal = _extract_goal(state["messages"])
        if goal:
            messages.append(
                SystemMessage(
                    content=f"【锚点提醒】当前核心目标：{goal}\n请继续围绕该目标推进，避免偏离。"
                )
            )

    messages += list(state["messages"])

    # DeepSeek 用户级隔离：从运行时配置取 user_id 上报
    user_id = str(config.get("configurable", {}).get("user_id", "default"))
    response = await _invoke_llm(llm_with_tools, messages, user_id)
    return {"messages": [response], "step_count": 1}


async def _retrieve_memories(config: RunnableConfig) -> str:
    """从长期记忆 Store 检索当前用户的记忆，拼接为文本。"""
    try:
        store = get_store()
    except Exception:
        # 未编译 store 时跳过记忆检索
        return ""
    if store is None:
        # 未编译 store（阶段 1 无记忆）时跳过
        return ""

    user_id = str(config.get("configurable", {}).get("user_id", "default"))
    namespace = ("user_" + user_id, "memories")
    items = await store.asearch(namespace, limit=50)
    if not items:
        return ""

    lines = []
    for item in items:
        value = item.value if isinstance(item.value, dict) else {"content": str(item.value)}
        lines.append(f"- {value.get('content', str(value))}")
    return "\n".join(lines)
