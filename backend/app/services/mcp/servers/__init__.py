"""自建 MCP Server 实现。

每个文件对应一个通过 stdio 拉起的 MCP Server（使用官方 mcp 包的 FastMCP）。
新增自建 Server 时：在此目录新增一个 *_server.py，并在上级 server_config.py 中
新增对应的 build_xxx_server 连接配置。
"""
