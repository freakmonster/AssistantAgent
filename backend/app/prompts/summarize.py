"""会话摘要压缩提示词。

提供摘要压缩的提示词模板与组装函数，供 summarize_node 调用。
"""

_SUMMARY_INSTRUCTION = (
    "请将以下对话历史压缩成一段简洁的中文摘要，保留关键事实"
    "（人名、偏好、任务、结论、待办），去除寒暄与冗余。只输出摘要正文。\n\n"
)
_SUMMARY_PREVIOUS_TEMPLATE = "已有的历史摘要：\n{previous_summary}\n\n"
_SUMMARY_HISTORY_TEMPLATE = "待压缩的对话：\n{history_text}"


def build_summarize_prompt(history_text: str, previous_summary: str = "") -> str:
    """组装会话摘要压缩的完整提示词。

    Args:
        history_text: 待压缩的对话历史文本。
        previous_summary: 已有的历史摘要，为空时省略该段。

    Returns:
        完整的摘要压缩提示词。
    """
    prompt = _SUMMARY_INSTRUCTION
    if previous_summary:
        prompt += _SUMMARY_PREVIOUS_TEMPLATE.format(previous_summary=previous_summary)
    prompt += _SUMMARY_HISTORY_TEMPLATE.format(history_text=history_text)
    return prompt
