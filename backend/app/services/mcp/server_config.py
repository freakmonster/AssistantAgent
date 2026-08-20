"""MCP Server 连接配置工厂。

集中管理所有 MCP Server 的连接配置。每接入一个 Server，在此新增一个
build_xxx_server 函数，返回 langchain-mcp-adapters 可识别的配置字典：

- 远程服务：{"transport": "streamable_http", "url": "...", "headers": {...}}
- 本地进程：{"command": "...", "args": [...], "env": {...}}

注意：本模块刻意命名为 server_config.py，而非 servers.py，避免与
同目录下的 servers/ 包（自建 Server 实现）发生模块/包同名冲突。
"""
from app.core.config import settings


def build_tavily_server(api_key: str) -> dict:
    """构造 Tavily MCP Server 的 Streamable HTTP 连接配置。

    Args:
        api_key: Tavily API Key。

    Returns:
        langchain-mcp-adapters 可识别的连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": "https://mcp.tavily.com/mcp/",
        # 密钥经 Authorization 头传递，避免出现在 URL 查询串中被日志/代理明文记录
        "headers": {"Authorization": f"Bearer {api_key}"},
    }


def build_chart_server(token: str) -> dict:
    """构造魔搭可视化图表 MCP Server 的 Streamable HTTP 连接配置。

    Args:
        token: 魔搭（ModelScope）访问令牌，通过 Authorization Bearer 传递。

    Returns:
        langchain-mcp-adapters 可识别的连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_CHART_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_amap_server(token: str) -> dict:
    """构造高德地图 MCP Server 的 SSE 连接配置。

    与 chart 同为魔搭（ModelScope）api-inference 托管服务，鉴权方式一致：
    通过 Authorization Bearer 传递令牌。SSE 为老式传输协议（非 Streamable HTTP）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 sse 连接配置字典。
    """
    return {
        "transport": "sse",
        "url": settings.MODELSCOPE_AMAP_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_fetch_server(token: str) -> dict:
    """构造网页内容抓取 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供 fetch 工具，将网页 HTML 转为
    markdown 返回，支持 start_index 分块读取长页面。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_FETCH_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_t12306_server(token: str) -> dict:
    """构造 12306 车票查询 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供车站编码查询、余票搜索、当前日期等
    8 个工具（含 get-tickets 余票查询）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_T12306_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_deepwiki_server(token: str) -> dict:
    """构造 DeepWiki（GitHub 维基百科）MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供 deepwiki_fetch 工具，将 DeepWiki
    页面爬取并转为清洗后的 Markdown。

    注意（实测发现）：
    - 域名校验有 bug：deepwiki.org 会被拒，实际可用 deepwiki.com 域名。
    - maxDepth 参数实际上限为 1（文档声称 10）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_DEEPWIKI_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_flight_compare_server(token: str) -> dict:
    """构造机票比价 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供 flight_compare 工具，跨飞猪/途牛/
    同程/美团/RG 五平台直飞机票实时比价，按航班号匹配并返回预订链接。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_FLIGHT_COMPARE_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_food_server() -> dict:
    """构造"今天吃什么"美食 MCP Server 的 SSE 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，但该服务**无需鉴权**（实测
    不带 Bearer 即可握手）。提供 5 个工具：查询全部菜谱、按分类查询、智能推荐
    膳食、不知道吃什么（按人数推荐今日菜单）、按 ID 查菜谱。

    注意：getAllRecipes 返回全部菜谱数据，上下文极大（慎用），工具 description
    已标注，agent 应优先使用分类查询/推荐类工具。

    Returns:
        langchain-mcp-adapters 可识别的 sse 连接配置字典。
    """
    return {
        "transport": "sse",
        "url": settings.MODELSCOPE_FOOD_URL,
    }


def build_leetcode_server(token: str) -> dict:
    """构造 LeetCode MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。

    注意（实测发现）：托管版**仅暴露 8 个无需认证的公开工具**（每日一题、
    查题、搜题、用户资料/竞赛排名/近期 AC、题解列表/详情），文档声称的
    run_code / submit_solution / 笔记 / get_user_status 等**需认证工具在托管版
    中不存在**，因此无法通过传 session 使用认证功能（需本地 stdio 自部署）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_LEETCODE_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_arxiv_server(token: str) -> dict:
    """构造 ArXiv 论文助手 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌（实测不带 token 会 401，与 food 不同）。

    提供 4 个工具：search_arxiv（关键词搜索）、get_arxiv_pdf_url（PDF 下载链接）、
    parse_paper_content（内容解析，优先 HTML 回退 PDF）、get_recent_ai_papers
    （AI 领域今日最新论文）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_ARXIV_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_document_generator_server(token: str) -> dict:
    """构造 DOCX/PDF 文档生成 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，提供 markdown_to_document
    工具：接收完整 Markdown 文本，用 Pandoc 转换为 DOCX/PDF 文档并应用字体设置，
    返回文件下载链接。

    注意（实测发现）：该服务鉴权与 chart 等不同，Authorization 头**直接放 token
    值，不带 Bearer 前缀**（带 Bearer 反而会握手失败）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_DOCUMENT_GENERATOR_URL,
        "headers": {"Authorization": token},
    }


def build_bazi_server(token: str) -> dict:
    """构造八字排盘 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供 3 个工具：
    getBaziDetail（公历/农历计算八字）、getSolarTimes（八字反推公历时间）、
    getChineseCalendar（黄历查询）。

    注意（实测发现）：getBaziDetail 的 gender 参数在服务端 schema 中**必填**
    （文档标注可选，但缺省会 422 校验失败），调用时需带上 0（女）/1（男）。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_BAZI_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_qwen_video_server(token: str) -> dict:
    """构造通义千问-视频理解 MCP Server 的 Streamable HTTP 连接配置。

    同为魔搭（ModelScope）api-inference 托管服务，鉴权方式与 chart 一致：
    通过 Authorization Bearer 传递令牌。提供 interpret_video_content 工具，
    通过视频链接和文字描述解读视频内容，返回结构化文字描述。

    注意（实测发现）：
    - text 与 video_url 均需传入（缺 text 会 400）。
    - 单次调用约 10~20s（视视频长度而定），需在 main.py 中对该工具单独
      调大超时（见 mcp_host.set_tool_timeout），默认 30s 有超时风险。

    Args:
        token: 魔搭（ModelScope）访问令牌。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": settings.MODELSCOPE_QWEN_VIDEO_URL,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def build_filesystem_server(allowed_root: str) -> dict:
    """构造本地文件系统 MCP Server 的 stdio 连接配置。

    主应用会以子进程方式拉起 servers/filesystem_server.py，
    并通过环境变量 ALLOWED_ROOT 限定其可访问目录。

    Args:
        allowed_root: 文件系统工具允许访问的根目录。

    Returns:
        langchain-mcp-adapters 可识别的 stdio 连接配置字典。
    """
    return {
        "command": "python",
        "args": ["-m", "app.services.mcp.servers.filesystem_server"],
        "env": {"ALLOWED_ROOT": allowed_root},
    }
