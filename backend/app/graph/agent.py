"""Agent 图构建与编译。

使用 LangGraph 构建 ReAct 循环：agent 与 tools 之间通过条件边连接，
并在 agent 输出最终答案前经 check 节点复核，防止长会话漂移。
"""
from langgraph.graph import END, START, StateGraph

from app.graph.nodes.agent_node import agent_node
from app.graph.nodes.check_node import check_node
from app.graph.nodes.summarize_node import summarize_node
from app.graph.nodes.tool_node import tool_node
from app.graph.state import MessagesState
from app.graph.internal_tools import INTERNAL_TOOLS
from app.services.mcp.host import mcp_host
from app.services.memory_service import memory_service

# 内部工具始终注册到 MCPHost，保证 agent_node 与 tool_node 使用同一份工具注册表
# wait_for_task 自管理超时（内部 job.result(timeout=60)），外层超时置 None 绕开默认 30s
mcp_host.register_internal_tools(INTERNAL_TOOLS, timeouts={"wait_for_task": None})


def _route_after_agent(state: dict) -> str:
    """agent 之后的路由：有工具调用则执行工具，否则进入复核节点。"""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "check"


def _route_after_check(state: dict) -> str:
    """check 之后的路由：判定偏离则回到 agent 重新作答，否则结束。"""
    return "agent" if state.get("drifted") else END


def build_agent(checkpointer=None, store=None):
    """构建并编译 Agent 图。

    Args:
        checkpointer: 工作记忆 checkpointer（阶段 2 传入）。
        store: 长期记忆 store（阶段 2 传入）。

    Returns:
        编译后的 LangGraph 图，可通过 invoke/stream 调用。
    """
    builder = StateGraph(MessagesState)

    # 添加节点
    builder.add_node("summarize", summarize_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("check", check_node)

    # 入口先进入 summarize 节点，检查上下文是否需要压缩
    builder.add_edge(START, "summarize")
    builder.add_edge("summarize", "agent")

    # agent 之后：有 tool_calls 进 tools，否则进 check 复核
    builder.add_conditional_edges("agent", _route_after_agent)

    # 工具执行后回到 summarize 节点，再次检查上下文，再进入 agent
    builder.add_edge("tools", "summarize")

    # check 之后：偏离则回到 agent 重新作答，否则结束
    builder.add_conditional_edges("check", _route_after_check)

    return builder.compile(checkpointer=checkpointer, store=store)


# 模块级编译好的图实例（无记忆，供阶段 1 兼容使用）
agent_graph = build_agent()

# 带 checkpointer/store 的编译图单例，供生产环境（startup 后）使用
_compiled_agent = None


def get_agent():
    """返回带记忆（checkpointer/store）的编译图，懒加载单例。

    需在 memory_service.initialize() 完成后调用，否则 checkpointer 为空。
    """
    global _compiled_agent
    if _compiled_agent is None:
        _compiled_agent = build_agent(
            checkpointer=memory_service.checkpointer,
            store=memory_service.store,
        )
    return _compiled_agent
