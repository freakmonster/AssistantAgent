"""应用配置模块。

使用 pydantic-settings 从环境变量或 .env 文件加载配置。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置。

    字段与 backend/.env.example 保持一致，密钥类配置仅从环境变量读取。
    """

    # 安全相关
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # 数据库与缓存
    DATABASE_URL: str
    REDIS_URL: str

    # 模型与工具
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    TAVILY_API_KEY: str

    # 智谱视频生成
    ZHIPU_API_KEY: str
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn"

    # 媒体转存（阶段 5：URL 真实转存，方案 A：StaticFiles 挂载本地目录）
    MEDIA_UPLOAD_DIR: str = "uploads"  # 本地存储根目录（相对 backend 工作目录）
    MEDIA_URL_PREFIX: str = "/media"  # 静态访问 URL 前缀，需与 main.py 挂载保持一致
    MEDIA_MAX_SIZE: int = 100 * 1024 * 1024  # 单文件转存大小上限（字节，100MB）
    MEDIA_DOWNLOAD_TIMEOUT: int = 60  # 下载临时 URL 超时（秒）

    # 魔搭可视化图表 MCP
    MODELSCOPE_TOKEN: str
    # 魔搭 api-inference 托管的各 MCP 服务地址（真实 URL 只存 .env，不写死在代码里）
    MODELSCOPE_CHART_URL: str
    MODELSCOPE_AMAP_URL: str
    MODELSCOPE_FETCH_URL: str
    MODELSCOPE_T12306_URL: str
    MODELSCOPE_DEEPWIKI_URL: str
    MODELSCOPE_FLIGHT_COMPARE_URL: str
    MODELSCOPE_FOOD_URL: str
    MODELSCOPE_LEETCODE_URL: str
    MODELSCOPE_ARXIV_URL: str

    # 会话压缩（上下文达到阈值时用「摘要 + 最近窗口」替换早期消息）
    SUMMARIZE_TOKEN_THRESHOLD: int = 700_000  # 触发压缩的 token 阈值（1M 窗口的 70%）
    SUMMARIZE_KEEP_MESSAGES: int = 20  # 压缩时保留的最近消息条数

    # JWT 鉴权
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # Token 有效期（分钟，24 小时）

    # 跨域（前端开发服务器）
    CORS_ORIGINS: list[str] = ["*"]

    # 超时层级（阶段 5）：内部组件超时 < 全流程超时
    MAIN_FLOW_TIMEOUT: int = 300  # 主流程总超时（秒）
    MODEL_TIMEOUT: int = 120  # DeepSeek 模型调用超时（秒）
    MCP_TOOL_TIMEOUT: int = 30  # MCP 工具调用超时（秒）
    SQL_TIMEOUT: int = 10  # SQL 查询超时（秒）

    # 日志
    LOG_LEVEL: str = "INFO"

    # 可观测性（阶段 6）
    SERVICE_NAME: str = "agent-orchestrator"  # 追踪中展示的服务名（设计文档 12.4 示例）
    # OTLP HTTP 端点（如 Jaeger http://localhost:4318/v1/traces）；留空则降级为控制台导出
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
