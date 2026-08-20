"""LLM 实例工厂。

集中构建 ChatOpenAI 实例，供压缩/摘要等辅助类任务复用，避免各处硬编码
模型 id 与密钥；后续引入多模型路由时在此层统一扩展。
"""
from langchain_openai import ChatOpenAI


def build_chat_llm(
    model: str,
    api_key: str,
    base_url: str,
    temperature: float = 0,
) -> ChatOpenAI:
    """按参数构建 ChatOpenAI 实例。

    Args:
        model: 模型 id（如 deepseek-chat / deepseek-flash）。
        api_key: API 密钥。
        base_url: API 端点。
        temperature: 采样温度，默认 0 以保证摘要/压缩结果稳定。

    Returns:
        配置好的 ChatOpenAI 实例。
    """
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )