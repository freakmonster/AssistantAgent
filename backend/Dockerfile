# 后端 FastAPI 服务镜像
# 说明：容器内以 uvicorn 监听 8000，对外不直接暴露端口，统一由 nginx 网关反代

FROM python:3.12-slim

# 关闭字节码缓存与 Python 输出缓冲，避免日志/交互卡顿
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装 ffmpeg（ASR 音频转码依赖，asr_engine.py 通过 subprocess 调用）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 先拷贝依赖清单并安装，利用 Docker 层缓存加速重复构建
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用源码
COPY app ./app

# 应用内部端口（仅容器网络内可达，对外由 nginx 暴露）
EXPOSE 8000

# 启动 uvicorn；--proxy-headers 让限流/日志读取 nginx 传入的真实客户端 IP
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
