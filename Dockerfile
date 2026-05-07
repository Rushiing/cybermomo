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

# Railway 提供 PORT;本地默认 8000
EXPOSE 8000

# 启动命令
# 注:不用 shell form `CMD foo` 因为要展开 ${PORT};使用 sh -c 显式
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
