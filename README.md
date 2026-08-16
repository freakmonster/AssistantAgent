# 超级个人综合型助手

基于 FastAPI + LangGraph(ReAct) + DeepSeek + MCP + PostgreSQL + Redis 的全栈个人 AI 助手，支持工具调用、流式回答、异步任务、双轨记忆与多端前端界面。

## 技术栈

| 端 | 技术 |
| --- | --- |
| 后端 | FastAPI + Uvicorn，LangGraph（ReAct 循环：agent → tools → check 防漂移 → summarize 压缩） |
| 模型 | DeepSeek API（deepseek-chat，经 langchain-openai 兼容接入） |
| 工具 | MCP（Tavily、魔搭图表/地图/机票/12306/arXiv/菜谱/LeetCode 等）+ 内部工具（图片生成、视频生成） |
| 数据库 | PostgreSQL 15（pgvector），双轨记忆：工作记忆（AsyncPostgresSaver）+ 长期记忆（AsyncPostgresStore） |
| 队列 | Redis 7 + ARQ（异步任务：视频生成等） |
| 前端 | React 18 + TypeScript + Zustand + Vite，SSE 流式渲染（react-markdown） |
| 可观测 | OpenTelemetry（OTLP）+ structlog 结构化日志 |

## 功能

- 对话式交互：SSE 流式回答、Markdown 渲染、图片/视频内嵌展示、工具调用卡片实时状态
- 联网搜索：Tavily 实时搜索最新信息
- 图片生成：智谱 CogView 图片生成（同步返回）
- 视频生成：智谱 CogVideoX 视频生成（异步任务，前端轮询结果）
- 可视化图表：魔搭图表生成
- 地图服务：高德地理编码、天气、路径规划、周边 POI
- 火车票 / 机票查询：12306 余票、跨平台机票比价
- 美食菜谱 / LeetCode / arXiv 论文检索
- 记忆能力：会话压缩摘要 + 长期记忆检索（`WHERE user_id=...` 隔离）
- 会话管理：侧边栏按置顶/时间分组，支持重命名、置顶、软删除

## 目录结构

```
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # REST 接口（auth / chat / sessions / tasks / users）
│   │   ├── core/            # 配置、Redis、安全
│   │   ├── graph/           # LangGraph 图与节点（agent / tools / check / summarize）
│   │   ├── models/          # SQLAlchemy 模型
│   │   ├── prompts/         # 系统提示词、摘要、防漂移复核
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # Agent 服务、MCP 主机、记忆、媒体存储
│   │   ├── tasks/           # ARQ 异步任务（worker + jobs）
│   │   └── utils/           # 日志、限流、熔断重试、遥测
│   ├── requirements.txt
│   ├── .env.example         # 环境变量模板（密钥只写这里）
│   └── start-dev.ps1        # 一键启动 uvicorn + ARQ worker
├── frontend/                # React 前端
│   └── src/                 # components / hooks / stores / services / types
├── docker-compose.yml       # PostgreSQL(pgvector) + Redis + worker
└── install_ffmpeg.ps1       # 视频/媒体处理依赖安装脚本
```

## 快速开始

### 1. 启动基础设施（PostgreSQL + Redis）

```bash
docker compose up -d postgres redis
```

### 2. 配置后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env   # 然后填入真实密钥（DeepSeek / Tavily / 智谱 / 魔搭等）
```

### 3. 启动后端（uvicorn + ARQ worker）

```powershell
cd backend
.\start-dev.ps1
```

脚本会打开两个新窗口分别运行：

- uvicorn：`http://127.0.0.1:8016`（`--reload` 热重载）
- ARQ worker：消费 `run_agent_task`、`generate_video_task` 等异步任务

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5178`（Vite 已将 `/api` 代理到 `http://localhost:8016`）。

### 5. 验证

```
GET http://127.0.0.1:8016/api/v1/health   # 返回 {"status":"ok"}
```

## 环境变量

所有密钥通过 `backend/.env` 注入（模板见 `backend/.env.example`），核心项：

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 签名密钥 |
| `DATABASE_URL` | PostgreSQL 连接串（与 docker-compose 中 postgres 服务一致） |
| `REDIS_URL` | Redis 连接串 |
| `DEEPSEEK_API_KEY` | DeepSeek 模型密钥 |
| `TAVILY_API_KEY` | Tavily 联网搜索密钥 |
| `MODELSCOPE_TOKEN` / `MODELSCOPE_*_URL` | 魔搭 api-inference 托管的 MCP 服务 |
| `ZHIPU_API_KEY` | 智谱视频生成密钥 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry 上报端点（留空则控制台输出 span） |

## 关键设计

- **API 前缀**：`/api/v1`，Bearer 鉴权，所有查询强制 `WHERE user_id=:user_id`
- **双轨记忆**：`thread_id = f"{user_id}_{conversation_id}"`，长期记忆 `namespace = ("user_{user_id}", "memories")`
- **SSE 流式**：`stream_mode=["messages","updates","custom"]`，前端用 `fetch + ReadableStream`（EventSource 无法带自定义 Header）
- **防漂移**：agent 输出经 check 节点复核（以最新用户消息为基准），偏离则回到 agent 重新作答，最多提醒 2 次
- **会话压缩**：上下文超阈值时对早期对话生成摘要，用「摘要 + 最近消息」替换完整历史
- **异步任务**：视频等长耗时任务经 ARQ 入队，前端轮询状态并渲染结果

## 其他

- 设计文档 / 阶段执行计划 / 验收清单见仓库内相关文档
- 前端单独说明见 `frontend/README.md`
