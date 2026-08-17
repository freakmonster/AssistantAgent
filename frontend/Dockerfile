# 前端构建镜像：多阶段构建，产出静态产物 dist
# 说明：本镜像仅负责构建前端静态产物（位于 /app/dist），运行期由 nginx 服务挂载托管

# ---------- 构建阶段：node 编译 ----------
FROM node:22-alpine AS build

WORKDIR /app

# 先拷贝依赖清单，利用 Docker 层缓存加速重复构建
COPY package.json package-lock.json ./
RUN npm ci

# 拷贝源码并构建生产产物
COPY . .
RUN npm run build

# ---------- 运行阶段：仅保留静态产物，供 nginx 挂载 ----------
FROM alpine:3.20
WORKDIR /app
COPY --from=build /app/dist ./dist
