"""会话压缩节点。

在 Agent 推理前检查上下文 token 数，超过阈值时对早期对话生成一次性摘要，
用「摘要 + 最近消息」替换完整历史，避免上下文无限增长导致成本与延迟上升。
"""
import uuid

from langchain_core.messages import BaseMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.config import get_store

from app.core.config import settings
from app.prompts import build_summarize_prompt
from app.utils.llm import build_chat_llm


def estimate_tokens(messages: list[BaseMessage]) -> int:
    """粗略估算消息列表 token 数（中英混合，约 1 token = 2 字符）。"""
    total = 0
    for message in messages:
        content = message.content
        if isinstance(content, str):
            total += len(content)
        else:
            total += len(str(content))
    return total // 2


def _build_summary_llm() -> ChatOpenAI:
    """构建用于生成摘要的模型（温度 0，保证摘要稳定）。"""
    return build_chat_llm(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


def _format_message(message: BaseMessage) -> str:
    """将消息格式化为文本，便于交给摘要模型。"""
    role = message.__class__.__name__
    content = message.content if isinstance(message.content, str) else str(message.content)
    return f"{role}: {content}"


async def _summarize(messages: list[BaseMessage], previous_summary: str) -> str:
    """对早期对话生成一次性摘要，并融合已有摘要。"""
    history_text = "\n".join(_format_message(m) for m in messages)
    prompt = build_summarize_prompt(history_text, previous_summary)

    llm = _build_summary_llm()
    response = await llm.ainvoke(prompt)
    return response.content


async def _store_summary(config: RunnableConfig, summary_text: str) -> None:
    """把摘要写入长期记忆 Store，供 query_memory 工具检索。"""
    try:
        store = get_store()
    except Exception:
        return
    if store is None:
        return

    user_id = str(config.get("configurable", {}).get("user_id", "default"))
    namespace = ("user_" + user_id, "summaries")
    key = f"sum_{uuid.uuid4().hex[:8]}"
    await store.aput(namespace, key, {"content": summary_text})


async def summarize_node(state: dict, config: RunnableConfig) -> dict:
    """检查上下文长度，超阈值时压缩早期消息。

    Args:
        state: 当前图状态，含 messages 与 summary 字段。
        config: 运行时配置，含 user_id。

    Returns:
        需要压缩时返回 {"summary": 新摘要, "messages": [RemoveMessage...]}；
        无需压缩时返回空字典。
    """
    messages = state.get("messages", [])
    summary = state.get("summary", "")

    keep_count = settings.SUMMARIZE_KEEP_MESSAGES
    if len(messages) <= keep_count:
        return {}

    # 摘要与消息一起估算 token
    total_tokens = estimate_tokens(messages) + len(summary) // 2
    if total_tokens < settings.SUMMARIZE_TOKEN_THRESHOLD:
        return {}

    to_summarize = messages[:-keep_count]
    if not to_summarize:
        return {}

    new_summary = await _summarize(to_summarize, summary)
    await _store_summary(config, new_summary)

    # 移除被压缩的早期消息，保留最近 keep_count 条
    deletes = [RemoveMessage(id=m.id) for m in to_summarize if m.id]
    return {"summary": new_summary, "messages": deletes}
