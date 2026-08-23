"""影刀 RPA 热键触发内部工具。

提供 trigger_rpa_app：通过本地影刀客户端热键触发指定 RPA 应用（同步，注入毫秒级）。

与视频生成等异步任务不同，热键注入是瞬时操作，因此以同步内部工具接入。
"""
from langchain_core.tools import tool

from app.services.rpa_hotkey import trigger_rpa_app as _trigger_rpa_app


@tool
def trigger_rpa_app(app_name: str) -> str:
    """通过本地影刀 RPA 客户端的热键触发，启动指定的自动化应用。

    适用场景：
    - 用户明确要求"启动/打开/运行/开始"某个已配置的 RPA 应用，如"启动竞品监控日报系统"
    - 触发关键词：启动、打开、运行、开始、竞品监控、日报系统

    不适用场景：
    - 用户仅询问应用的功能或用途（如"竞品监控日报系统是做什么的？"）——直接回答即可，不要触发
    - 影刀客户端未运行，或应用未在客户端配置热键触发

    Args:
        app_name: 影刀 RPA 应用名称，必须是配置中存在的应用（如"竞品监控日报系统"）。

    Returns:
        结构化 JSON：
        {"success": true, "message": "...", "hotkey": "ctrl+shift+alt+c", "app_name": "..."}
        或错误结构 {"error": "app_not_found|client_offline|inject_failed|config_error|not_configured", "message": "..."}。

    注意事项：
    - success 仅代表热键已成功注入，不代表 RPA 流程执行完成（应用在影刀客户端后台异步运行）
    """
    return _trigger_rpa_app(app_name)


__all__ = ["trigger_rpa_app"]
