"""Agent 服务封装。

封装 LangGraph 图的调用，提供非流式与流式两种对话方式。
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import select

from app.core.config import settings
from app.graph.agent import get_agent
from app.models.database import async_session_factory
from app.models.message import Message
from app.models.session import Session
from app.services.file_service import FileService


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
        self,
        thread_id: str,
        user_id: str,
        session_id: str,
        message: str,
        attachments: list[str] | None = None,
    ) -> str:
        """非流式执行 Agent，返回最终回答文本。"""
        config = self._build_config(thread_id, user_id, session_id)
        inputs = {
            "messages": [
                {
                    "role": "user",
                    "content": await self._resolve_attachments(
                        user_id, attachments or [], message
                    ),
                }
            ]
        }
        result = await self.agent.ainvoke(inputs, config=config)
        messages = result.get("messages", [])
        if not messages:
            return ""
        await self._persist_messages(thread_id, user_id, message, messages, attachments or [])
        last = messages[-1]
        content = getattr(last, "content", "")
        return content if isinstance(content, str) else str(content)

    async def stream_agent_response(
        self,
        thread_id: str,
        user_id: str,
        session_id: str,
        message: str,
        attachments: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式执行 Agent，生成 SSE 事件。"""
        config = self._build_config(thread_id, user_id, session_id)
        inputs = {
            "messages": [
                {
                    "role": "user",
                    "content": await self._resolve_attachments(
                        user_id, attachments or [], message
                    ),
                }
            ]
        }
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
        except asyncio.CancelledError:
            # 客户端主动断开（前端暂停/取消）：不落库、不发 done，直接退出，
            # 交由上层取消传播，避免在 finally 中对已关闭的流 yield 引发异常
            raise
        except asyncio.TimeoutError:
            yield self._sse("error", {"error": "请求超时"})
            yield self._sse("done", {"status": "completed"})
        except Exception as exc:
            yield self._sse("error", {"error": str(exc)})
            yield self._sse("done", {"status": "completed"})
        else:
            # 流正常完整结束后才落库（超时/异常/取消不会进入 else，避免写入残缺消息）
            state = await self.agent.aget_state(config)
            await self._persist_messages(
                config["configurable"]["thread_id"],
                user_id,
                message,
                state.values.get("messages", []),
                attachments or [],
            )
            yield self._sse("done", {"status": "completed"})

    async def _resolve_attachments(
        self, user_id: str, attachments: list[str], message: str
    ) -> str:
        """把附件文件解析文本拼接到用户消息，构造 LLM 输入。

        Args:
            user_id: 当前用户 id（字符串）。
            attachments: 附件 file_id 列表。
            message: 用户原始问题。

        Returns:
            拼接后的消息内容：附件文本在前，用户问题在后。
        """
        if not attachments:
            return message

        file_ids = []
        for aid in attachments:
            try:
                file_ids.append(uuid.UUID(aid))
            except ValueError:
                continue

        async with async_session_factory() as db:
            files = await FileService().load_texts(uuid.UUID(user_id), file_ids, db)

        blocks = []
        for f in files:
            blocks.append(
                f"【用户提供的文件内容：{f['filename']}】\n"
                f"{self._truncate_text(f['text'], settings.FILE_TEXT_MAX_CHARS)}"
            )
        if not blocks:
            return message
        attachment_text = "\n---\n".join(blocks)
        # 设计文档 14.5.4：附件解析文本 + 用户问题，两者一并注入 LLM
        return f"{attachment_text}\n\n用户问题：\n{message}"

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """注入 LLM 前截断超长解析文本，避免撑爆模型 context。

        超过 max_chars 时保留前 3/4 + 尾部 1/4，中间以省略提示替代，
        兼顾开头概述与结尾结论，同时保留完整长度信息供模型感知。
        """
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        head = text[: max_chars * 3 // 4]
        tail = text[-(max_chars // 4):]
        return f"{head}\n\n……（内容过长已截断，完整共 {len(text)} 字符）……\n\n{tail}"

    async def _persist_messages(
        self,
        thread_id: str,
        user_id: str,
        user_message: str,
        messages: list,
        attachments: list[str] | None = None,
    ) -> None:
        """将本次用户消息与最终 assistant 回答写入 messages 表。

        使用独立 DB session（不复用请求级 db，因为 SSE 流生命周期更长）。
        attachments 为用户消息携带的附件 file_id 列表，落库为附件元数据。
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

        # 用户消息附件元数据：file_id + filename（用于前端气泡展示）
        attachment_meta = []
        if attachments:
            async with async_session_factory() as db:
                file_ids = []
                for aid in attachments:
                    try:
                        file_ids.append(uuid.UUID(aid))
                    except ValueError:
                        continue
                files = await FileService().load_texts(
                    uuid.UUID(user_id), file_ids, db
                )
            attachment_meta = [
                {"type": "file", "file_id": str(f["file_id"]), "filename": f["filename"]}
                for f in files
            ]

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

            # 显式刷新会话更新时间：onupdate 只在 sessions 行被 UPDATE 时触发，
            # 历史会话仅新增消息不触碰该行，会导致 updated_at 永远停留在创建时间
            db_session.updated_at = datetime.now(timezone.utc)

            session.add(
                Message(
                    session_id=session_id,
                    role="user",
                    content=user_message,
                    attachments=attachment_meta or None,
                )
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
