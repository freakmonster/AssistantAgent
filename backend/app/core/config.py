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

    # 模型路由（前端可选模型：不同供应商不同模型由用户单独配置）
    # JSON 数组字符串，每项 {"id","name","base_url","api_key"}；base_url/api_key 留空时回退 DEEPSEEK_*
    # 未配置时默认两条：deepseek-v4-pro / deepseek-v4-flash
    MODEL_ROUTES: str = ""
    DEFAULT_MODEL: str = "deepseek-v4-pro"  # 前端未指定模型时使用的默认模型 id

    # 智谱视频生成
    ZHIPU_API_KEY: str
    ZHIPU_BASE_URL: str = "https://open.bigmodel.cn"

    # 媒体转存（阶段 5：URL 真实转存，方案 A：StaticFiles 挂载本地目录）
    MEDIA_UPLOAD_DIR: str = "uploads"  # 本地存储根目录（相对 backend 工作目录）
    MEDIA_URL_PREFIX: str = "/media"  # 静态访问 URL 前缀，需与 main.py 挂载保持一致
    MEDIA_MAX_SIZE: int = 100 * 1024 * 1024  # 单文件转存大小上限（字节，100MB）
    MEDIA_DOWNLOAD_TIMEOUT: int = 60  # 下载临时 URL 超时（秒）

    # 文件上传与解析（阶段 9）
    FILE_UPLOAD_STORAGE: str = "local"  # 存储实现：local（本地）/ qiniu（七牛云 Kodo）
    FILE_UPLOAD_DIR: str = "file_uploads"  # local 模式存储根目录，与 MEDIA_UPLOAD_DIR 隔离，避免被 /media 静态挂载暴露
    FILE_MAX_SIZE: int = 20 * 1024 * 1024  # 单文件大小上限（字节，20MB）
    FILE_QUOTA_BYTES: int = 512 * 1024 * 1024  # 每用户总占用配额（字节，默认 512MB），超阈值触发清理最旧一半
    FILE_GLOBAL_QUOTA_BYTES: int = 8 * 1024 * 1024 * 1024  # 全部用户累计写入上限（字节，8GB，七牛空间 10GB 留 2GB 余量），达到后拒绝新上传并触发全局清理
    FILE_RETENTION_DAYS: int = 3  # 文件保留天数，超过即自动清理（定时任务每日执行）
    FILE_PARSE_MODE: str = "transient"  # 解析链路开关：transient=即解析即删（默认，不转存原始文件）/ persist=转存存储后解析（切回七牛时用）
    FILE_TEXT_MAX_CHARS: int = 12000  # 附件解析文本注入上下文前的单文件截断上限（字符），同时作为 LLM 压缩的触发阈值与目标长度
    FILE_DOWNLOAD_TIMEOUT: int = 300  # persist 模式解析下载超时（秒），独立于 MEDIA_DOWNLOAD_TIMEOUT
    FILE_DOWNLOAD_CHUNKS: int = 4  # persist 模式分片并发下载片数

    # 文件附件 LLM 语义压缩（阶段 9 增强）
    FILE_COMPRESS_ENABLED: bool = True  # 是否启用 LLM 压缩；关闭或失败时降级为字符截断
    FILE_COMPRESS_MODEL: str = "deepseek-v4-flash"  # 压缩模型 id（DeepSeek 当前仅支持 deepseek-v4-pro / deepseek-v4-flash）
    FILE_COMPRESS_BASE_URL: str = ""  # 压缩模型 base_url，空则回退 DEEPSEEK_BASE_URL
    FILE_COMPRESS_API_KEY: str = ""  # 压缩模型 api_key，空则回退 DEEPSEEK_API_KEY
    FILE_COMPRESS_CHARS_PER_TOKEN: int = 2  # 字符/token 换算比例（与 summarize_node 的 estimate_tokens 一致）
    FILE_COMPRESS_WINDOW_RATIO: float = 0.5  # 单片安全上限 = 模型窗口 × 该比例，留出 prompt 与输出余量
    FILE_COMPRESS_MAX_CHUNKS: int = 8  # 分片并发压缩的最大片数，防止极端文件产生过多并发
    FILE_COMPRESS_TIMEOUT: int = 60  # 单次压缩 LLM 调用超时（秒），超时降级为字符截断；需小于 worker 任务超时（300s）
    FILE_COMPRESS_MODEL_WINDOWS: dict[str, int] = {
        # OpenAI
        "gpt-5.6-sol": 1_050_000,
        "gpt-5.4": 1_050_000,
        "gpt-5.5": 1_000_000,
        "gpt-5.4-mini": 400_000,
        "gpt-4o": 128_000,
        # Anthropic
        "claude-opus-4.7": 1_000_000,
        "claude-opus-4.8": 1_000_000,
        "claude-sonnet-4.6": 1_000_000,
        # Google
        "gemini-3.1-pro": 2_000_000,
        "gemini-2.5-pro": 1_000_000,
        # DeepSeek（保留当前配置使用的兼容别名）
        "deepseek-v4-pro": 1_000_000,
        "deepseek-v4-flash": 1_000_000,  # DeepSeek V4 Flash
        # 阿里云
        "qwen-long": 10_000_000,
        "qwen3.8-max": 1_000_000,
        "qwen3.7-max": 1_000_000,
        "qwen3.5-plus": 1_000_000,
        # Meta
        "llama-4-scout": 10_000_000,
        # 月之暗面
        "kimi-k3": 1_050_000,
        "kimi-k2.6": 262_144,
        # 腾讯、MiniMax 与智谱
        "hy3": 256_000,
        "hunyuan-hy3": 256_000,
        "minimax-m3": 1_000_000,
        "glm-5": 200_000,
        "glm-5.2": 200_000,
    }  # 模型 id -> 上下文窗口（tokens）；未收录模型回退 1_000_000

    # 百度云 OCR（PP-OCRv6，扫描件 PDF 与图片识别）
    BAIDU_OCR_ENABLED: bool = False  # 是否启用；关闭时扫描件/图片保持空文本（现状）
    BAIDU_API_KEY: str = ""         # 百度智能云 API Key（OCR 与 ASR 共用）
    BAIDU_SECRET_KEY: str = ""      # 百度智能云 Secret Key（OCR 与 ASR 共用）
    BAIDU_OCR_MAX_PAGES: int = 20   # 单份扫描件 PDF 最多识别页数（逐页调用，控配额/耗时）

    # 百度云 ASR（短语音识别极速版；AK/SK 复用上方 BAIDU_API_KEY/BAIDU_SECRET_KEY）
    BAIDU_ASR_DEV_PID: int = 80001   # 短语音识别极速版模型
    BAIDU_ASR_MAX_SECONDS: int = 30  # 单次语音输入最长秒数（前后端双层限制）

    # 七牛云 Kodo（FILE_UPLOAD_STORAGE=qiniu 时必填）
    QINIU_ACCESS_KEY: str = ""
    QINIU_SECRET_KEY: str = ""
    QINIU_BUCKET: str = ""  # 空间名
    QINIU_DOMAIN: str = ""  # 下载域名（公开空间直出裸 URL），load 时用它拼接 URL

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
    MODELSCOPE_DOCUMENT_GENERATOR_URL: str
    MODELSCOPE_BAZI_URL: str
    MODELSCOPE_QWEN_VIDEO_URL: str

    # 会话压缩（上下文达到阈值时用「摘要 + 最近窗口」替换早期消息）
    SUMMARIZE_TOKEN_THRESHOLD: int = 700_000  # 触发压缩的 token 阈值（1M 窗口的 70%）
    SUMMARIZE_KEEP_MESSAGES: int = 20  # 压缩时保留的最近消息条数

    # JWT 鉴权
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # Token 有效期（分钟，24 小时）

    # 跨域（前端开发服务器）
    CORS_ORIGINS: list[str] = ["*"]

    # 超时层级（阶段 5）：内部组件超时 < 全流程超时
    MAIN_FLOW_TIMEOUT: int = 180  # 主流程总超时（秒），单轮对话最长等待
    MODEL_TIMEOUT: int = 45  # 模型单次尝试超时（秒）
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
