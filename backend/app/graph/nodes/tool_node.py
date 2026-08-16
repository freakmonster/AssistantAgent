"""工具执行节点。

通过 MCPHost 统一执行工具调用（含权限检查与审计日志），并将结果返回给 LLM。
同时实现工具使用纪律护栏：相同参数调用同一工具超过 3 次强制终止，同一工具连续失败 2 次上报。
"""
import json

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.services.mcp.host import mcp_host
from app.utils.telemetry import tracer

MAX_SAME_ARG_CALLS = 3  # 相同参数调用同一工具的最大次数
MAX_CONSECUTIVE_FAILURES = 2  # 同一工具连续失败的最大次数


def _is_error(content: str) -> bool:
    """判断工具结果是否为结构化错误（含 error 字段）。"""
    try:
        data = json.loads(content)
        return isinstance(data, dict) and "error" in data
    except (json.JSONDecodeError, TypeError):
        return False


def _collect_call_history(messages: list) -> tuple[dict, dict]:
    """统计工具调用历史。

    Args:
        messages: 完整消息历史。

    Returns:
        (call_counts, consecutive_failures)：
        - call_counts：{(tool_name, args_key): 调用次数}
        - consecutive_failures：{tool_name: 最近连续失败次数}
    """
    call_counts: dict[tuple[str, str], int] = {}
    consecutive_failures: dict[str, int] = {}

    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                args_key = json.dumps(tc["args"], sort_keys=True, ensure_ascii=False)
                key = (tc["name"], args_key)
                call_counts[key] = call_counts.get(key, 0) + 1
        elif isinstance(m, ToolMessage):
            name = m.name or ""
            if _is_error(m.content):
                consecutive_failures[name] = consecutive_failures.get(name, 0) + 1
            else:
                consecutive_failures[name] = 0

    return call_counts, consecutive_failures


@tracer.start_as_current_span("tool_node")
async def tool_node(state: dict, config: RunnableConfig) -> dict:
    """执行最近一条消息中的工具调用，并施加工具使用纪律护栏。

    Args:
        state: 当前图状态，含 messages 字段。
        config: 运行时配置，含 user_id。

    Returns:
        包含工具结果消息的状态更新字典。
    """
    messages = state["messages"]
    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    user_id = str(config.get("configurable", {}).get("user_id", "default"))

    call_counts, consecutive_failures = _collect_call_history(messages)

    results = []
    for tc in tool_calls:
        name = tc["name"]
        args = tc["args"]
        args_key = json.dumps(args, sort_keys=True, ensure_ascii=False)

        # 护栏 1：相同参数调用同一工具超过 3 次，强制终止
        if call_counts.get((name, args_key), 0) >= MAX_SAME_ARG_CALLS:
            content = json.dumps(
                {"error": "ToolAbuse", "message": "相同参数调用同一工具超过 3 次，已强制终止"},
                ensure_ascii=False,
            )
        # 护栏 2：同一工具连续失败 2 次，上报错误并询问用户
        elif consecutive_failures.get(name, 0) >= MAX_CONSECUTIVE_FAILURES:
            content = json.dumps(
                {"error": "RepeatedFailure", "message": "该工具已连续失败 2 次，请上报错误并询问用户"},
                ensure_ascii=False,
            )
        else:
            content = await mcp_host.call_tool(name, args, user_id)

        results.append(ToolMessage(content=content, tool_call_id=tc["id"], name=name))

    return {"messages": results}
