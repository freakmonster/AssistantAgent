"""MCP Host 管理层。

负责管理多个 MCP Server 的工具，统一提供工具列表、权限检查、审计日志与工具调用。
"""
import asyncio
import json
import time
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from opentelemetry import trace

from app.core.config import settings
from app.utils import logger as app_logger
from app.utils.rate_limit import check_tool_rate_limit
from app.utils.telemetry import tracer

logger = app_logger.get_logger(__name__)


class MCPHost:
    """MCP Host，管理 MCP 工具并统一执行入口。"""

    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        self.tools: list = []
        self._tool_registry: dict[str, Any] = {}
        self._servers: dict[str, Any] = {}
        # 工具级超时覆盖：None 表示该工具自管理超时（如 wait_for_task），
        # 其余未登记的工具仍使用默认 MCP_TOOL_TIMEOUT。
        self._tool_timeouts: dict[str, float | None] = {}

    def register_server(self, name: str, server_config: dict) -> None:
        """注册一个 MCP Server 的连接配置。

        注册后会在调用 `initialize` 时统一建立连接并获取工具列表。

        Args:
            name: Server 名称（如 "tavily"）。
            server_config: 连接配置，形如
                {"transport": "streamable_http", "url": "..."}。
        """
        self._servers[name] = server_config

    def register_internal_tools(
        self, internal_tools: list, timeouts: dict | None = None
    ) -> None:
        """同步注册内部工具（无需建立连接）。

        Args:
            internal_tools: 内部工具列表（如 get_current_time、save_memory）。
            timeouts: 工具级超时覆盖，形如 {"wait_for_task": None}。
                值 None 表示该工具自管理超时（内部自行控制），其余工具仍用默认超时。
        """
        timeouts = timeouts or {}
        for tool in internal_tools:
            if tool.name not in self._tool_registry:
                self._tool_registry[tool.name] = tool
                self.tools.append(tool)
            if tool.name in timeouts:
                self._tool_timeouts[tool.name] = timeouts[tool.name]

    def set_tool_timeout(self, tool_name: str, timeout: float | None) -> None:
        """覆盖单个工具的超时（秒）。

        MCP 工具初始化后默认用 MCP_TOOL_TIMEOUT；对耗时型工具（如视频理解、
        文档生成）可单独调大。值 None 表示该工具自管理超时（内部自行控制）。

        Args:
            tool_name: 工具名称（须与 MCP 工具列表中的名字一致）。
            timeout: 超时秒数，None 表示自管理超时。
        """
        self._tool_timeouts[tool_name] = timeout

    def augment_tool_description(self, tool_name: str, suffix: str) -> None:
        """给指定工具的描述追加补充说明。

        服务端返回的工具 description 无法直接修改，但本地可追加说明，
        用于引导 LLM 正确构造参数。典型场景：schema 未把某参数标为必填，
        但服务端实际要求必填（如视频理解的 text），可在此告知 LLM
        「参数必填；若用户未提供，请自动补通用默认值」。

        Args:
            tool_name: 工具名称（须与已注册工具名一致）。
            suffix: 追加到原描述末尾的补充说明。
        """
        tool = self._tool_registry.get(tool_name)
        if tool is None:
            logger.warning("工具 %s 未注册，无法追加描述说明", tool_name)
            return
        tool.description = f"{tool.description} {suffix}"

    async def initialize(self, servers: dict | None = None) -> None:
        """连接所有已注册的 MCP Server 并注册其工具。

        单个 Server 握手失败只跳过该 Server 并记 warning 日志，
        不会拖垮整个初始化（避免任一远端 MCP 故障导致应用无法启动）。

        Args:
            servers: 额外的 MCP Server 连接配置，会与 `register_server` 注册的配置合并。

        todo: 暂不实现热更新。当前工具列表仅在启动时一次性 get_tools 并缓存，
        运行中新增 Server 或 MCP 端工具增删不会自动刷新。后续如需支持运行中接入新
        Server / 热刷新工具，可增加可重入的 refresh()/add_server() 接口（agent_node
        的 get_tools() 已支持即时读取，只需触发重新拉取即可）。
        """
        merged = dict(self._servers)
        if servers:
            merged.update(servers)

        if merged:
            self._client = MultiServerMCPClient(merged)
            # 逐 Server 拉取工具：gather + return_exceptions 隔离故障，
            # 单个 Server 连接失败仅记录日志，不影响其他 Server 与整体启动。
            results = await asyncio.gather(
                *(self._client.get_tools(server_name=name) for name in merged),
                return_exceptions=True,
            )
            for name, tools in zip(merged, results):
                if isinstance(tools, Exception):
                    logger.warning(
                        "MCP Server %s 初始化失败，已跳过：%s", name, tools
                    )
                    continue
                for tool in tools:
                    if tool.name not in self._tool_registry:
                        self._tool_registry[tool.name] = tool
                        self.tools.append(tool)

    def get_tools(self) -> list:
        """返回全部工具列表（内部工具 + MCP 工具）。"""
        return self.tools

    @tracer.start_as_current_span("tool_call")
    async def call_tool(self, tool_name: str, arguments: dict, user_id: str) -> str:
        """执行工具调用，含权限检查与审计日志。

        Args:
            tool_name: 工具名称。
            arguments: 工具调用参数。
            user_id: 当前用户标识。

        Returns:
            工具执行结果字符串。
        """
        span = trace.get_current_span()
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("user.id", user_id)
        _start = time.perf_counter()

        tool = self._tool_registry.get(tool_name)
        if tool is None:
            return json.dumps(
                {"error": "ToolNotFound", "message": f"未知工具 {tool_name}"},
                ensure_ascii=False,
            )

        # 权限检查（Host 职责，阶段 3 默认放行）
        if not self._has_permission(user_id, tool_name):
            return json.dumps(
                {"error": "PermissionDenied", "message": "无权使用该工具"},
                ensure_ascii=False,
            )

        # 工具级限流（按用户隔离，超限直接拒绝）
        if not await check_tool_rate_limit(tool_name, user_id):
            return json.dumps(
                {"error": "RateLimited", "message": "工具调用过于频繁，请稍后再试"},
                ensure_ascii=False,
            )

        try:
            # 工具级超时覆盖：None 表示工具自管理超时（asyncio.timeout(None) 不超时）
            timeout = self._tool_timeouts.get(tool_name, settings.MCP_TOOL_TIMEOUT)
            async with asyncio.timeout(timeout):
                result = await tool.ainvoke(arguments)
        except asyncio.TimeoutError:
            result = json.dumps(
                {"error": "Timeout", "message": "工具调用超时"},
                ensure_ascii=False,
            )
        except Exception as exc:
            result = json.dumps(
                {"error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )

        # 审计日志（含耗时）
        latency_ms = int((time.perf_counter() - _start) * 1000)
        span.set_attribute("latency_ms", latency_ms)
        await self._log_audit(user_id, tool_name, arguments, result, latency_ms)

        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False)
        return result

    def _has_permission(self, user_id: str, tool_name: str) -> bool:
        """检查用户是否有权使用指定工具。阶段 3 默认放行。"""
        return True

    async def _log_audit(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict,
        result: str,
        latency_ms: int | None = None,
    ) -> None:
        """写入审计日志。阶段 3 使用结构化日志，阶段 4 落库 audit_logs 表。"""
        logger.info(
            "工具调用审计",
            user_id=user_id,
            tool=tool_name,
            args=json.dumps(arguments, ensure_ascii=False),
            result=result[:500],
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        """关闭 MCP 客户端（工具每次调用自行管理会话，此处仅释放引用）。"""
        self._client = None


# 全局 MCPHost 实例
mcp_host = MCPHost()
