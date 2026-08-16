"""Agent 服务封装。

封装 LangGraph 图的调用，提供非流式与流式两种对话方式。
"""
import asyncio
import json
from typing import Any, AsyncGenerator

from sqlalchemy import select

from app.core.config import settings
from app.graph.agent import get_agent
from app.models.database import async_session_factory
from app.models.message import Message
from app.models.session import Session


class AgentService:
    """LangGraph Agent 封装。"""

    def __init__(self) -> None:
        self.agent = get_agent()

    @staticmethod
    def _build_config(thread_id: str, user_id: str, session_id: str) -> dict:
        """构造 LangGraph 运行时配置（含防死循环护栏）。"""
        return {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
                "session_id": session_id,
            },
            "recursion_limit": 25,
        }

    async def run_agent_sync(
        self, thread_id: str, user_id: str, session_id: str, message: str
    ) -> str:
        """非流式执行 Agent，返回最终回答文本。"""
        config = self._build_config(thread_id, user_id, session_id)
        inputs = {"messages": [{"role": "user", "content": message}]}
        result = await self.agent.ainvoke(inputs, config=config)
        messages = result.get("messages", [])
        if not messages:
            return ""
        await self._persist_messages(thread_id, message, messages)
        last = messages[-1]
        content = getattr(last, "content", "")
        return content if isinstance(content, str) else str(content)

    async def stream_agent_response(
        self, thread_id: str, user_id: str, session_id: str, message: str
    ) -> AsyncGenerator[str, None]:
        """流式执行 Agent，生成 SSE 事件。"""
        config = self._build_config(thread_id, user_id, session_id)
        inputs = {"messages": [{"role": "user", "content": message}]}
        try:
            # 主流程总超时（阶段 5）
            async with asyncio.timeout(settings.MAIN_FLOW_TIMEOUT):
                async for event in self.agent.astream(
                    inputs,
                    config=config,
                    stream_mode=["messages", "updates", "custom"],
                ):
                    formatted = self._format_sse_event(event)
                    if formatted:
                        yield formatted
        except asyncio.TimeoutError:
            yield self._sse("error", {"error": "请求超时"})
        except Exception as exc:
            yield self._sse("error", {"error": str(exc)})
        else:
            # 流正常完整结束后才落库（超时/异常不会进入 else，避免写入残缺消息）
            state = await self.agent.aget_state(config)
            await self._persist_messages(
                config["configurable"]["thread_id"],
                message,
                state.values.get("messages", []),
            )
        finally:
            yield self._sse("done", {"status": "completed"})

    async def _persist_messages(
        self, thread_id: str, user_message: str, messages: list
    ) -> None:
        """将本次用户消息与最终 assistant 回答写入 messages 表。

        使用独立 DB session（不复用请求级 db，因为 SSE 流生命周期更长）。
        """
        final_answer = ""
        tool_calls: list | None = None
        for msg in messages:
            if getattr(msg, "type", "") != "ai":
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content:
                final_answer = content
            if getattr(msg, "tool_calls", None):
                tool_calls = self._serialize_tool_calls(msg.tool_calls)

        async with async_session_factory() as session:
            db_session = await session.scalar(
                select(Session).where(Session.thread_id == thread_id)
            )
            if db_session is None:
                return
            session_id = db_session.id

            # 会话自动命名：标题仍为默认值（未命名/新对话）时，用首条用户消息截取生成
            if db_session.title in (None, "", "新对话"):
                db_session.title = self._gen_session_title(user_message)

            session.add(
                Message(session_id=session_id, role="user", content=user_message)
            )
            session.add(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content=final_answer,
                    tool_calls=tool_calls,
                )
            )
            await session.commit()

    @staticmethod
    def _gen_session_title(message: str, max_len: int = 9) -> str:
        """用首条用户消息生成会话标题（去空白后截取前 max_len 字）。"""
        text = " ".join(message.split())
        if not text:
            return "新对话"
        return text[:max_len] + ("…" if len(text) > max_len else "")

    @staticmethod
    def _serialize_tool_calls(tool_calls: list) -> list:
        """将 LangChain tool_calls 转为可 JSON 序列化的 dict 列表。"""
        result = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                result.append(tc)
                continue
            result.append(
                {
                    "name": getattr(tc, "name", ""),
                    "args": getattr(tc, "args", {}),
                    "id": getattr(tc, "id", None),
                }
            )
        return result

    @staticmethod
    def _format_sse_event(event: Any) -> str:
        """将 LangGraph 流事件转换为 SSE 文本。"""
        mode, data = event
        if mode == "messages":
            msg, meta = data
            node = meta.get("langgraph_node")
            # 过滤内部节点（check 防漂移复核 / tools 工具结果）的消息，避免泄漏到 text 事件流
            if node in ("check", "tools"):
                return ""
            content = getattr(msg, "content", "")
            if content:
                return AgentService._sse("text", {"content": content})
            # 工具调用不在此发送：流式 chunk 的 args 逐块补全、首个 chunk 为空，
            # 统一由 updates 模式在 agent 节点完成时发出完整 tool_calls
            return ""
        if mode == "updates":
            # 优先提取 agent 节点产出的完整 tool_calls（args 完整）
            tool_call_event = AgentService._extract_tool_call_event(data)
            if tool_call_event:
                return tool_call_event
            return AgentService._sse("update", data)
        if mode == "custom":
            return AgentService._sse("custom", data)
        return ""

    @staticmethod
    def _extract_tool_call_event(data: Any) -> str:
        """从 updates 事件的 agent 节点输出中提取完整 tool_calls，生成 tool_call 事件。

        流式 messages 模式下 tool_call 的 args 逐块补全、首个 chunk 为空，故改从
        agent 节点完成后的完整 AIMessage 中提取，保证前端展示的 args 完整。
        """
        if not isinstance(data, dict):
            return ""
        agent_update = data.get("agent")
        if not isinstance(agent_update, dict):
            return ""
        messages = agent_update.get("messages")
        if not isinstance(messages, list):
            return ""
        for msg in messages:
            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                continue
            valid_calls = []
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if name and tid:
                    valid_calls.append(tc)
            if valid_calls:
                return AgentService._sse("tool_call", {"tool_calls": valid_calls})
        return ""

    @staticmethod
    def _to_jsonable(obj: Any) -> Any:
        """递归将对象转为可 JSON 序列化的结构。

        LangChain 消息对象（BaseMessage）含 model_dump，转为 dict 保留 content 等字段，
        使前端能从 update 事件中可靠解析工具结果（如 type=task 的 task_id）。
        其余无法序列化的对象降级为字符串。
        """
        if isinstance(obj, dict):
            return {k: AgentService._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [AgentService._to_jsonable(v) for v in obj]
        if hasattr(obj, "model_dump"):
            return AgentService._to_jsonable(obj.model_dump())
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        return str(obj)

    @staticmethod
    def _sse(event: str, data: Any) -> str:
        """构造一条 SSE 事件（对无法序列化的对象降级为字符串）。"""
        return (
            f"event: {event}\n"
            f"data: {json.dumps(AgentService._to_jsonable(data), ensure_ascii=False)}\n\n"
        )
