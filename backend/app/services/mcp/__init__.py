"""MCP 模块。

包含三部分：
- host.py：MCP Host 管理层（工具注册表 + 权限/限流/超时/审计 + 统一调用入口）
- server_config.py：MCP Server 连接配置工厂（Streamable HTTP / stdio）
- servers/：自建 MCP Server 实现（每个文件一个 stdio Server）
"""
