"""LangGraph 状态定义。

定义 Agent 对话过程中的共享状态。
"""
import operator
from typing import Annotated

from langgraph.graph import MessagesState as _MessagesState


class MessagesState(_MessagesState):
    """Agent 对话状态。

    继承 LangGraph 内置的 MessagesState，核心字段 messages 为消息列表，
    由 add_messages reducer 自动追加合并。

    扩展字段：
    - summary：历史对话压缩后的摘要，由 summarize_node 在上下文超阈值时生成，
      通过 checkpointer 跨轮持久化，供 agent_node 注入上下文。
    - step_count：ReAct 循环步数，由 agent_node 每次执行累加，用于锚点注入。
    - drift_warnings：防漂移复核警告次数，由 check_node 累加，避免复核死循环。
    - drifted：最近一次复核是否判定偏离，由 check_node 写入，供条件路由。
    """

    summary: str
    step_count: Annotated[int, operator.add]
    drift_warnings: Annotated[int, operator.add]
    drifted: bool
