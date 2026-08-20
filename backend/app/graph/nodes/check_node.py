"""防漂移复核节点。

在 Agent 准备输出最终答案（无工具调用）时，复核其回答是否偏离用户核心目标；
若偏离则注入提醒并引导回到 agent 重新作答，最多提醒 MAX_DRIFT_WARNINGS 次。
"""
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.prompts import build_check_drift_prompt

MAX_DRIFT_WARNINGS = 2  # 最多复核提醒次数，超过后强制放行，避免死循环


def _build_check_llm() -> ChatOpenAI:
    """构建复核模型（温度 0，保证判断稳定；禁用流式避免内部判断泄露到 SSE）。"""
    return ChatOpenAI(
        model=settings.DEFAULT_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0,
        disable_streaming=True,
    )


def _extract_goal(messages: list) -> str:
    """提取用户核心目标（最新一条人类消息内容）。

    取最新一条而非第一条，避免把已结束的旧话题（如上一轮任务）当作复核基准，
    导致新话题的正确答案被误判为偏离。
    """
    for m in reversed(messages):
        if isinstance(m, HumanMessage) and isinstance(m.content, str):
            return m.content.strip()
    return ""


def _extract_last_answer(messages: list) -> str:
    """提取最后一条无工具调用的 AI 消息文本。"""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


async def _check_drift(goal: str, answer: str) -> bool:
    """用 LLM 判断回答是否偏离核心目标。"""
    llm = _build_check_llm()
    prompt = build_check_drift_prompt(goal, answer)
    response = await llm.ainvoke(prompt)
    content = response.content if isinstance(response.content, str) else str(response.content)
    return content.strip().startswith("是")


async def check_node(state: dict, config: RunnableConfig) -> dict:
    """复核 Agent 最终回答是否偏离核心目标。

    Args:
        state: 当前图状态，含 messages、drift_warnings 字段。
        config: 运行时配置。

    Returns:
        偏离时返回 {"drifted": True, "messages": [提醒], "drift_warnings": 1}；
        未偏离或超出提醒上限时返回 {"drifted": False}。
    """
    # 已提醒多次仍偏离时强制放行，交由 recursion_limit 兜底，避免死循环
    if state.get("drift_warnings", 0) >= MAX_DRIFT_WARNINGS:
        return {"drifted": False}

    goal = _extract_goal(state["messages"])
    answer = _extract_last_answer(state["messages"])
    if not goal or not answer:
        return {"drifted": False}

    drifted = await _check_drift(goal, answer)
    if drifted:
        return {
            "drifted": True,
            "drift_warnings": 1,
            "messages": [
                AIMessage(
                    content=f"【复核提醒】你的回答偏离了核心目标「{goal}」，请重新聚焦后回答。"
                )
            ],
        }
    return {"drifted": False}
