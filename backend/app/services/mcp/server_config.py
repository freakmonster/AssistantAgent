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


def build_polygon_server(api_key: str = "") -> dict:
    """构造 Polygon.io（Pipeworx 网关托管）MCP Server 的 Streamable HTTP 连接配置。

    提供金融数据工具（tickers、aggregates、daily_open_close、news 等 12 个），
    实为 Massive（原 Polygon.io）数据源。支持两种鉴权模式（实测确认）：
    - 平台托管模式（推荐）：无需任何请求头，直接握手即可（本函数默认）。
    - 自带密钥模式：在 URL 后追加 ?_apiKey=KEY（通过 POLYGON_API_KEY 注入）。

    注意（实测发现）：
    - 该网关实际暴露 43 个工具，其中 31 个是 Pipeworx 平台通用工具
      （ask_pipeworx、deep_research、polymarket 等），与金融数据无关，已在
      main.py 通过 mcp_host.filter_server_tools 按白名单过滤，只暴露 12 个
      Polygon 数据工具。
    - 免费套餐限制 5 次/分钟，工具描述已提示 LLM 克制调用。
    - 单次调用约 0.2~4s，属同步工具，走默认 MCP_TOOL_TIMEOUT。

    Args:
        api_key: Polygon.io API 密钥，非空时启用自带密钥模式；空则平台托管模式。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    url = "https://gateway.pipeworx.io/polygon-io/mcp"
    if api_key:
        url = f"{url}?_apiKey={api_key}"
    return {
        "transport": "streamable_http",
        "url": url,
    }


def build_calculator_server() -> dict:
    """构造 calculator-mcp-server 的 Streamable HTTP 连接配置。

    公开第三方 MCP 服务（https://calculator.caseyjhand.com/mcp），**无需鉴权**。
    提供 1 个 calculate 工具，基于 math.js 支持三种操作（实测确认）：
    - evaluate：算术、三角函数、对数、统计、矩阵、复数等计算
    - simplify：代数表达式符号化简（2x + 3x -> 5 * x）
    - derivative：符号求导（3x^2 + 2x + 1 -> 6 * x + 2）

    注意（实测发现）：
    - expression 为必填参数；operation 省略时默认 evaluate。
    - 单次调用约 0.3s，属同步工具，走默认 MCP_TOOL_TIMEOUT。
    - 服务端计算能力有限（基于 math.js），超纲表达式会返回错误信息，
      工具 description 已提示 LLM 优先用于数值/符号计算校验。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    return {
        "transport": "streamable_http",
        "url": "https://calculator.caseyjhand.com/mcp",
    }


def build_firecrawl_server(api_key: str) -> dict:
    """构造 Firecrawl MCP Server 的 Streamable HTTP 连接配置。

    Firecrawl 官方托管 MCP 服务。提供 26 个工具（scrape/map/search/crawl/
    parse/agent/monitor 等），核心能力为网页抓取与检索。

    鉴权（实测确认）：API Key 经 Authorization: Bearer 头传递，**不拼进 URL**
    （官方文档的 /{key}/v2/mcp 路径形式不安全，会被日志/代理记录）。
    无密钥也可握手但受速率限制，故 .env 未配置时按无密钥免费层接入。

    注意（实测发现）：
    - 26 个工具中含大量低频工具（monitor_* 监控、research_* 学术论文、
      feedback 反馈、agent 异步研究等），已在 main.py 通过
      mcp_host.filter_server_tools 按白名单只暴露 6 个核心工具。
    - 单次 scrape 约 0.6s，属同步工具，走默认 MCP_TOOL_TIMEOUT。

    Args:
        api_key: Firecrawl API Key（fc- 开头）；空则走无密钥免费层。

    Returns:
        langchain-mcp-adapters 可识别的 streamable_http 连接配置字典。
    """
    config: dict = {
        "transport": "streamable_http",
        "url": "https://mcp.firecrawl.dev/v2/mcp",
    }
    if api_key:
        config["headers"] = {"Authorization": f"Bearer {api_key}"}
    return config


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
