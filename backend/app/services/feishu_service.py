"""飞书机器人接入服务。

基于 lark-channel-sdk（官方 channel SDK）与飞书开放平台建立 WebSocket 长连接，
实时接收用户发送给机器人的消息（单聊全部消息 + 群聊中 @ 机器人的消息），调用
LangGraph Agent 并以流式 markdown 卡片回复（CardKit 打字机效果）。

设计要点：
- 单一系统账号：所有飞书用户共用内置机器人账号（feishu-bot@assistant.local），
  启动时幂等创建，不开放登录。
- 单一大会话：所有飞书消息（单聊 + 群聊）写入同一会话，thread_id 固定为
  {user_id}_feishu，用 asyncio.Lock 串行化 Agent 调用，避免并发写同一 checkpoint。
  如需按群隔离上下文，改 _resolve_thread_id 即可（见该方法说明）。
- 流式卡片回复：channel.stream({"markdown": producer}) 走 CardKit 预分配流程，
  Agent 每产出一段文本就更新卡片的 markdown 组件，SDK 负责节流、保序与收尾。
- 事件回调只做解析与调度：长连接模式下由 SDK 协议层即时回 ack，回调不等待
  Agent，故不受处理耗时影响。
"""

import asyncio
import concurrent.futures
import re
import secrets
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.models.database import async_session_factory
from app.models.session import Session
from app.models.user import User
from app.services.agent_service import AgentService
from app.utils import logger as app_logger

# 飞书机器人专用系统账号邮箱（仅内部使用）
FEISHU_BOT_EMAIL = "feishu-bot@assistant.local"
# 飞书大会话标题
FEISHU_SESSION_TITLE = "飞书助手"
# 卡片首屏等待文案（建卡后立即展示，替代独立「收到」文本消息）
FEISHU_THINKING_TEXT = "正在思考…"

# 强调标记正则：** 优先于 *（正则按顺序尝试匹配）
_EMPHASIS_RE = re.compile(r"\*\*|\*")
# 行内代码标记
_CODE_RE = re.compile(r"`")


def _can_open_emphasis(text: str, end: int) -> bool:
    """简化左侧界定符判断：标记后不能是空白或文本结尾。

    对应 CommonMark 的 left-flanking 规则，用于区分真正的强调标记与字面符号
    （如 `3 * 5` 中的乘号）。
    """
    return end < len(text) and not text[end].isspace()


def _can_close_emphasis(text: str, start: int) -> bool:
    """简化右侧界定符判断：标记前不能是空白或文本开头。"""
    return start > 0 and not text[start - 1].isspace()


def strip_unclosed_emphasis(text: str) -> str:
    """移除未闭合的强调标记（** / *）与行内代码标记（`）。

    飞书卡片富文本组件严格按 CommonMark 解析：未闭合的标记不会生效，而是原样
    显示（如模型输出「**定额税率」时，卡片里会看到裸露的 **）。这里用简化的
    flanking 规则找出真正的标记并按顺序配对，未配对的直接删除。

    两侧均为空白或边界（如 `3 * 5`）的符号不构成强调，作为字面量保留。
    """
    if not text:
        return text

    tokens = [(m.start(), m.end(), m.group()) for m in _EMPHASIS_RE.finditer(text)]
    paired = [False] * len(tokens)
    stacks: dict[str, list[int]] = {"**": [], "*": []}
    for i, (start, end, mark) in enumerate(tokens):
        can_open = _can_open_emphasis(text, end)
        can_close = _can_close_emphasis(text, start)
        if can_close and stacks[mark]:
            # 与最近的同类未闭合标记配对
            j = stacks[mark].pop()
            paired[i] = paired[j] = True
        elif can_open:
            stacks[mark].append(i)
        elif not can_close:
            # 两侧均为空白/边界，属字面符号，保留
            paired[i] = True

    removals = [(s, e) for i, (s, e, _) in enumerate(tokens) if not paired[i]]

    # 反引号不适用 flanking 规则，按数量奇偶判断是否有未闭合
    code_positions = [m.start() for m in _CODE_RE.finditer(text)]
    if len(code_positions) % 2:
        pos = code_positions[-1]
        removals.append((pos, pos + 1))

    # 从后往前删除，避免下标错位
    chars = list(text)
    for s, e in sorted(removals, reverse=True):
        del chars[s:e]
    return "".join(chars)


class FeishuService:
    """飞书长连接消息接入服务。

    通过 FeishuChannel 接收 im.message.receive_v1 事件（SDK 内置消息去重），
    过滤出单聊文本消息后交给 Agent 处理并回复。
    """

    def __init__(self) -> None:
        self.channel = None  # lark_channel.FeishuChannel 实例，未配置时为 None
        self._lock = asyncio.Lock()  # 串行化大会话的 Agent 调用
        self._user_id: str | None = None  # 系统账号 user_id（字符串缓存）
        self._session_id: str | None = None  # 飞书大会话 id（字符串缓存）
        self._main_loop: asyncio.AbstractEventLoop | None = None  # uvicorn 主事件循环
        self._background_tasks: set = set()  # 持有后台任务强引用，防止被 GC

    async def start(self) -> None:
        """应用启动时调用：幂等准备系统账号与会话，建立飞书长连接。"""
        if not settings.LARK_APP_ID or not settings.LARK_APP_SECRET:
            app_logger.get_logger("feishu").info(
                "飞书接入未配置（LARK_APP_ID / LARK_APP_SECRET 为空），跳过启动"
            )
            return
        # 保存 uvicorn 主事件循环：Agent 调用必须回到主循环执行。
        # 原因：SDK 后台线程的 bg loop 在 Windows 下默认是 ProactorEventLoop，
        # 不支持 add_reader，psycopg 异步驱动会抛 NotImplementedError；
        # 而主循环是 SelectorEventLoop（与网页聊天一致），数据库/记忆/MCP
        # 等共享资源也都绑定主循环，跨循环调度可保证资源在同一循环上使用。
        self._main_loop = asyncio.get_running_loop()
        await self._ensure_bot_account()
        # 延迟导入：未安装 lark-channel-sdk 时不阻塞应用其他功能启动
        from lark_channel import FeishuChannel

        # 修复 SDK 事件循环绑定问题：
        # lark_channel.ws.client 在模块导入时执行 asyncio.get_event_loop()，
        # 将模块级 loop 绑定到"当时的当前循环"。在 uvicorn lifespan 中导入时，
        # 该 loop 正是 uvicorn 正在运行的主循环；SDK 后台线程随后对其调用
        # run_until_complete() 会抛 RuntimeError: This event loop is already running。
        # 这里将 SDK 的模块级 loop 替换为独立的新循环，专供其 ws 后台线程使用。
        import lark_channel.ws.client as _lark_ws_client

        if sys.platform == "win32":
            # Windows 下使用 SelectorEventLoop，与项目既有约定保持一致
            _lark_ws_client.loop = asyncio.SelectorEventLoop()
        else:
            _lark_ws_client.loop = asyncio.new_event_loop()

        # 修复本机 Anaconda Python 3.11 + OpenSSL 3.5 兼容性问题：
        # ssl.create_default_context() 加载 Windows 证书库时，CPython 将原始 DER
        # 拼接作为 cadata 传给 OpenSSL 3.5，会解析失败（ASN1: NOT_ENOUGH_DATA），
        # 导致所有依赖系统证书库的 wss 连接失败（requests/httpx 走 certifi 不受影响）。
        # 这里将 SDK 的 websockets.connect 包装为使用 certifi CA 包，绕开系统证书库。
        import ssl as _ssl

        import certifi

        _orig_ws_connect = _lark_ws_client.websockets.connect

        def _ws_connect_with_certifi(url, **kwargs):
            if kwargs.get("ssl") is None or kwargs.get("ssl") is True:
                kwargs["ssl"] = _ssl.create_default_context(cafile=certifi.where())
            return _orig_ws_connect(url, **kwargs)

        _lark_ws_client.websockets.connect = _ws_connect_with_certifi

        self.channel = FeishuChannel(
            app_id=settings.LARK_APP_ID,
            app_secret=settings.LARK_APP_SECRET,
        )
        self.channel.on("message", self._handle_message)
        self.channel.on("error", self._handle_error)
        await self.channel.connect_until_ready()
        app_logger.get_logger("feishu").info("飞书长连接已建立")

    async def stop(self) -> None:
        """应用关闭时调用：断开飞书长连接，并等待后台任务收尾。"""
        if self.channel is not None:
            try:
                await self.channel.disconnect()
                app_logger.get_logger("feishu").info("飞书长连接已关闭")
            except Exception as exc:
                app_logger.get_logger("feishu").warning(
                    "关闭飞书长连接异常", error=str(exc)
                )
            self.channel = None
        # 快照后等待后台任务收尾（最多 5 秒），避免在回调 discard 期间并发修改 set
        futures = list(self._background_tasks)
        if futures:
            done, _ = concurrent.futures.wait(futures, timeout=5)
            for fut in futures:
                if not fut.done():
                    fut.cancel()

    def _task_done(self, fut: concurrent.futures.Future) -> None:
        """后台任务完成回调：从集合移除引用并消费潜在异常。"""
        self._background_tasks.discard(fut)
        try:
            fut.exception()
        except Exception:
            pass

    async def _ensure_bot_account(self) -> None:
        """幂等创建飞书机器人系统账号与大会话，并缓存 id。"""
        async with async_session_factory() as db:
            user = await db.scalar(select(User).where(User.email == FEISHU_BOT_EMAIL))
            if user is None:
                # 随机密码仅用于满足字段非空约束，系统账号不开放登录
                user = User(
                    email=FEISHU_BOT_EMAIL,
                    password_hash=hash_password(secrets.token_urlsafe(24)),
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

            thread_id = f"{user.id}_feishu"
            session = await db.scalar(
                select(Session).where(Session.thread_id == thread_id)
            )
            if session is None:
                session = Session(
                    user_id=user.id,
                    title=FEISHU_SESSION_TITLE,
                    thread_id=thread_id,
                )
                db.add(session)
                await db.commit()
                await db.refresh(session)

            self._user_id = str(user.id)
            self._session_id = str(session.id)
            app_logger.get_logger("feishu").info(
                "飞书系统账号与大会话就绪",
                user_id=self._user_id,
                session_id=self._session_id,
            )

    async def _handle_message(self, msg) -> None:
        """飞书消息事件回调（须尽快返回，SDK 已内置去重）。

        只做解析与任务调度：回复由后台任务的流式卡片完成，回调本身不等待 Agent，
        也不会被 Agent 耗时拖住（长连接模式下由 SDK 协议层即时回 ack）。

        支持单聊与群聊：单聊全部处理；群聊仅处理 @ 了本机器人的消息。

        Args:
            msg: lark_channel 的 InboundMessage 对象。
        """
        logger = app_logger.get_logger("feishu")
        try:
            chat_type = getattr(msg, "chat_type", None)
            # 仅处理单聊（p2p）与群聊（group）；话题等类型忽略
            if chat_type not in ("p2p", "group"):
                return
            # 群聊仅处理 @ 了本机器人的消息。当前权限为 group_at_msg 系列，
            # 飞书只会推送 @ 机器人的消息；此处再判一次，便于后续开通群内
            # 全量消息权限（im:message.group_msg）时仍只响应被 @ 的场景。
            if chat_type == "group" and not getattr(msg, "mentioned_bot", False):
                return
            # 仅处理文本消息；图片 / 文件 / 语音等类型暂不支持
            if getattr(msg, "raw_content_type", None) != "text":
                return
            if chat_type == "group":
                # 群聊正文用 safe_content_text：SDK 已移除对本机器人的 @ 占位符
                # （如「@_user_1 你好」→「你好」），避免脏标记进入模型输入
                text = (getattr(msg, "safe_content_text", "") or "").strip()
            else:
                text = (getattr(msg, "content_text", "") or "").strip()
            if not text:
                return

            logger.info(
                "收到飞书文本消息",
                chat_type=chat_type,
                chat_id=msg.chat_id,
                sender_id=getattr(msg, "sender_id", ""),
                message_id=msg.message_id,
            )
            # 后台执行 Agent 处理，不阻塞事件回调。
            # 注意：本回调运行在 SDK 后台线程的 bg loop（Windows 下默认
            # ProactorEventLoop，不支持 add_reader，psycopg 异步驱动会抛
            # NotImplementedError），因此通过 run_coroutine_threadsafe 将
            # Agent 任务调度回 uvicorn 主事件循环（SelectorEventLoop）执行，
            # 保证与网页聊天共用同一套数据库/记忆/MCP 等共享资源。
            if self._main_loop is not None and self._main_loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(
                    self._process_and_reply(msg.chat_id, msg.message_id, text),
                    self._main_loop,
                )
                self._background_tasks.add(fut)
                fut.add_done_callback(self._task_done)
            else:
                # 兜底：主循环未就绪（如单元测试直接调用回调）时，就地创建任务
                task = asyncio.create_task(
                    self._process_and_reply(msg.chat_id, msg.message_id, text)
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._task_done)
        except Exception as exc:
            logger.exception("飞书消息回调异常", error=str(exc))

    def _resolve_thread_id(self, chat_id: str) -> str:
        """解析消息归属的会话 thread_id。

        当前策略：单聊与所有群聊共用同一大会话（{系统账号}_feishu），
        便于快速验证收发链路。

        后续如需按群隔离上下文（各群历史与记忆互不干扰），在此返回
        f"{self._user_id}_{chat_id}"，并将 _session_id 由单值缓存改为
        按 thread_id 缓存的字典即可，其余逻辑无需改动。
        """
        return f"{self._user_id}_feishu"

    async def _process_and_reply(self, chat_id: str, message_id: str, text: str) -> None:
        """后台处理消息：以流式 markdown 卡片回复用户。

        通过 channel.stream 驱动 CardKit 打字机：Agent 每产出一段文本就更新卡片的
        markdown 组件，用户可实时看到回答逐步生成。超时与异常在 producer 内消化，
        以卡片内文案呈现，保证卡片能正常收尾（关闭 streaming_mode）。

        单聊与群聊共用同一会话，故用全局锁串行化 Agent 调用，避免并发写同一
        thread_id 的 checkpoint。
        """
        logger = app_logger.get_logger("feishu")
        if self._user_id is None or self._session_id is None:
            logger.error("飞书系统账号未初始化，忽略消息")
            return

        thread_id = self._resolve_thread_id(chat_id)

        # 串行化大会话的 Agent 调用，避免并发写同一 thread_id 的 checkpoint
        async with self._lock:
            agent_service = AgentService()
            # 卡片状态：has_text 标记是否已进入正文（决定覆盖首屏还是追加），
            # raw 累积原始全文（收尾时统一做标记规范化）。用可变容器便于闭包共享。
            state = {"has_text": False, "raw": ""}

            async def producer(ctl) -> None:
                """流式生产者：把 Agent 文本增量推入卡片。"""

                async def emit(chunk: str) -> None:
                    """输出内容：正文开始前覆盖首屏提示，开始后按增量追加。"""
                    state["raw"] += chunk
                    if state["has_text"]:
                        await ctl.append(chunk)
                        return
                    # 首个内容直接覆盖首屏提示，避免与「正在思考…」拼接
                    await ctl.set_content(chunk.lstrip("\n"))
                    state["has_text"] = True

                # 建卡后立即展示中文等待提示（SDK 默认文案为英文 Thinking...）
                await ctl.set_content(FEISHU_THINKING_TEXT)
                try:
                    async for kind, chunk in agent_service.stream_agent_text(
                        thread_id=thread_id,
                        user_id=self._user_id,
                        session_id=self._session_id,
                        message=text,
                        model=None,  # 使用默认模型
                    ):
                        if kind == "reset":
                            # 复核判定偏离、即将重新作答：清空已被否决的答案
                            logger.info(
                                "飞书回答触发复核重答，重置卡片正文", chat_id=chat_id
                            )
                            await ctl.set_content(FEISHU_THINKING_TEXT)
                            state["has_text"] = False
                            state["raw"] = ""
                            continue
                        await emit(chunk)
                except asyncio.TimeoutError:
                    logger.warning("飞书消息处理超时", chat_id=chat_id)
                    await emit("\n\n⏱️ 处理超时，请稍后重试。")
                except Exception as exc:
                    logger.exception(
                        "飞书消息处理失败", error=str(exc), chat_id=chat_id
                    )
                    await emit(f"\n\n❌ 处理失败：{exc}")
                else:
                    # Agent 未产出任何文本（空回答）时给一个兜底文案
                    if not state["has_text"]:
                        await emit("抱歉，我暂时无法回答这个问题。")

                # 收尾修正：飞书卡片严格按 CommonMark 解析，模型输出中未闭合的
                # 强调标记会裸露显示，这里统一清理后覆盖一次全文。
                # 不在流式过程中逐块处理：那样会破坏打字机的前缀匹配。
                normalized = strip_unclosed_emphasis(state["raw"])
                if normalized != state["raw"]:
                    logger.info("飞书卡片正文规范化：移除未闭合标记", chat_id=chat_id)
                    await ctl.set_content(normalized)

            try:
                await self.channel.stream(
                    chat_id,
                    {"markdown": producer},
                    {"reply_to": message_id},
                )
            except Exception as exc:
                # 卡片链路不可用（如未开通 cardkit:card:write 权限、建卡失败）：
                # 降级为纯文本回复，保证用户至少能收到一条提示
                logger.exception(
                    "飞书流式卡片发送失败", error=str(exc), chat_id=chat_id
                )
                try:
                    await self.channel.send(
                        chat_id,
                        {"text": "抱歉，本次回复发送失败，请联系管理员查看服务端日志。"},
                        {"reply_to": message_id},
                    )
                except Exception as send_exc:
                    logger.exception(
                        "飞书降级文本回复也失败", error=str(send_exc), chat_id=chat_id
                    )

    async def _handle_error(self, err) -> None:
        """飞书长连接错误统一上报日志（SDK 自动重连，无需手动恢复）。"""
        app_logger.get_logger("feishu").error("飞书长连接错误", error=str(err))


# 全局单例，供 main.py lifespan 启停使用
feishu_service = FeishuService()
