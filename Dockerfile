# CyberMOMO API · Dockerfile
#
# Railway 默认 service 跑 apps/api/(后端 FastAPI)
# Railway 检测到 Dockerfile 后会优先用它,不再走 Nixpacks 自动检测,避开 monorepo 里
# apps/web/package.json 干扰 Python 识别的问题。
#
# 如果以后要单独部署 apps/web/,在 Railway 新建一个 service,Root Directory 设为 apps/web/

FROM python:3.11-slim

# 系统依赖
# - gcc / libpq-dev:asyncpg + pydantic 编译可能需要
# - curl:healthcheck 备用
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 工作目录直接进 apps/api/(让 main.py / src.* / alembic 都在 cwd 下)
WORKDIR /app/apps/api

# 先 COPY 依赖清单,利用 docker layer 缓存
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 再 COPY 业务代码(改代码不会让 pip 缓存失效)
COPY apps/api/ ./

# 安全(audit P0-3 + codex P0-a):部署镜像默认 ENV=prod。
# 这样 Railway 的 ENV 变量即使丢失,容器仍是 prod → 启动守卫触发严格校验、
# mock-auth 永远关。本地裸跑 uvicorn(不走 Docker)才是 dev 默认。
# Railway 仍可用变量覆盖(如 staging),但 dev 不会成为线上静默默认值。
ENV ENV=prod

# Railway 提供 PORT;本地默认 8000
EXPOSE 8000

# 启动命令
# 注:不用 shell form `CMD foo` 因为要展开 ${PORT};使用 sh -c 显式
# 先跑 alembic upgrade(单进程,在 fork worker 前完成,migration 不并发),再起服务。
#
# --workers 4:Railway Hobby 8 vCPU 充裕。单 worker 时 LLM `await chat.completions`
# 不 yield CPU,event loop 上其他请求被挤几十秒("Failed to fetch")。4 worker
# 把请求散开,真人内测(100 人陆续)的并发能扛。
# 连接数:4 × (pool 10 + overflow 10) = 80 < PG usable 97(见 src/shared/db.py)。
# 注意:workers>1 后 admin seed 的 in-memory job state(_PIPELINE_JOB 等)会分散到
# 各 worker 进程,/seed/status 可能读不到 — seed 是一次性 ops,内测期不跑就没影响。
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
