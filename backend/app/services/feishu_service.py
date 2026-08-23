"""飞书机器人接入服务。

基于 lark-channel-sdk（官方 channel SDK）与飞书开放平台建立 WebSocket 长连接，
实时接收用户发送给机器人的单聊文本消息，调用 LangGraph Agent 处理后主动回复。

设计要点：
- 单一系统账号：所有飞书用户共用内置机器人账号（feishu-bot@assistant.local），
  启动时幂等创建，不开放登录。
- 单一大会话：所有飞书消息写入同一会话，thread_id 固定为 {user_id}_feishu，
  用 asyncio.Lock 串行化 Agent 调用，避免并发写同一 checkpoint。
- 3 秒时限：飞书长连接要求事件回调 3 秒内返回，故回调仅发送「收到」确认后立即返回，
  实际 Agent 处理放在后台任务，完成后再以 reply 关联原消息发送完整答案。
"""

import asyncio
import concurrent.futures
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
# 单聊确认回复文案（先确认后异步回复，规避 3 秒处理时限）
FEISHU_ACK_TEXT = "收到，正在思考…"


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
        """飞书消息事件回调（须在 3 秒内返回，SDK 已内置去重）。

        Args:
            msg: lark_channel 的 InboundMessage 对象。
        """
        logger = app_logger.get_logger("feishu")
        try:
            # 仅处理单聊（p2p）；群聊 / 话题消息直接忽略
            if getattr(msg, "chat_type", None) != "p2p":
                return
            # 仅处理文本消息；图片 / 文件 / 语音等类型暂不支持
            if getattr(msg, "raw_content_type", None) != "text":
                return
            text = (getattr(msg, "content_text", "") or "").strip()
            if not text:
                return

            logger.info(
                "收到飞书文本消息",
                chat_id=msg.chat_id,
                sender_id=getattr(msg, "sender_id", ""),
                message_id=msg.message_id,
            )
            # 先回复确认并立即返回，避免触发飞书 3 秒超时重推
            await self.channel.send(
                msg.chat_id,
                {"text": FEISHU_ACK_TEXT},
                {"reply_to": msg.message_id},
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

    async def _process_and_reply(self, chat_id: str, message_id: str, text: str) -> None:
        """后台处理消息：调用 Agent 生成回答并 reply 给用户。"""
        logger = app_logger.get_logger("feishu")
        if self._user_id is None or self._session_id is None:
            logger.error("飞书系统账号未初始化，忽略消息")
            return

        # 串行化大会话的 Agent 调用，避免并发写同一 thread_id 的 checkpoint
        async with self._lock:
            try:
                # 主流程总超时兜底：后台任务脱离 HTTP 请求生命周期，必须自行限时
                async with asyncio.timeout(settings.MAIN_FLOW_TIMEOUT):
                    agent_service = AgentService()
                    answer = await agent_service.run_agent_sync(
                        thread_id=f"{self._user_id}_feishu",
                        user_id=self._user_id,
                        session_id=self._session_id,
                        message=text,
                        model=None,  # 使用默认模型
                    )
            except asyncio.TimeoutError:
                answer = "处理超时，请稍后重试。"
                logger.warning("飞书消息处理超时", chat_id=chat_id)
            except Exception as exc:
                # 诊断：记录当前事件循环与记忆连接池状态，定位"拿不到连接"根因
                from app.services.memory_service import memory_service

                pool = memory_service.pool
                pool_state = "未初始化"
                if pool is not None:
                    pool_state = (
                        f"已建连={getattr(pool, '_nconns', '?')} "
                        f"空闲={len(getattr(pool, '_pool', ()))}"
                    )
                logger.exception(
                    "飞书消息处理失败",
                    error=str(exc),
                    chat_id=chat_id,
                    current_loop=f"{type(asyncio.get_running_loop()).__name__}"
                    f"@{id(asyncio.get_running_loop())}",
                    main_loop=f"{type(self._main_loop).__name__}@{id(self._main_loop)}",
                    pool_state=pool_state,
                )
                answer = f"处理失败：{exc}"

        reply_text = answer.strip() or "抱歉，我暂时无法回答这个问题。"
        try:
            result = await self.channel.send(
                chat_id,
                {"text": reply_text},
                {"reply_to": message_id},
            )
            # 上游发送失败通常返回 success=False 而非抛异常，需显式检查
            if getattr(result, "success", True) is False:
                logger.error(
                    "飞书回复发送失败",
                    error=getattr(result, "error", ""),
                    chat_id=chat_id,
                )
        except Exception as exc:
            logger.exception("飞书回复发送异常", error=str(exc), chat_id=chat_id)

    async def _handle_error(self, err) -> None:
        """飞书长连接错误统一上报日志（SDK 自动重连，无需手动恢复）。"""
        app_logger.get_logger("feishu").error("飞书长连接错误", error=str(err))


# 全局单例，供 main.py lifespan 启停使用
feishu_service = FeishuService()
