"""防漂移复核提示词。

供 check_node 判断 Agent 回答是否偏离用户核心目标。
"""

CHECK_DRIFT_PROMPT_TEMPLATE = (
    "请判断以下回答是否偏离了用户的核心目标，仅输出「是」或「否」。\n\n"
    "核心目标：{goal}\n"
    "回答：{answer}\n\n"
    "是否偏离："
)


def build_check_drift_prompt(goal: str, answer: str) -> str:
    """组装防漂移复核提示词。

    Args:
        goal: 用户的核心目标。
        answer: 待复核的回答。

    Returns:
        完整的复核提示词。
    """
    return CHECK_DRIFT_PROMPT_TEMPLATE.format(goal=goal, answer=answer)
