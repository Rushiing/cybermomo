"""
CyberMOMO API · FastAPI entrypoint

MVP 阶段 monolith,模块通过 router 划分。
- /healthz       健康检查
- /api/auth/*    Google OAuth + session
- /api/md/*      .md 创建(v3 规则引擎产出 profile JSON 入库)
- /api/match/*   匹配引擎
- /api/agent-chat/*  Agent 互聊
- /api/room/*    个人房间
- /api/summary/* Agent 简报
- /api/chat/*    真人聊天
"""
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] CyberMOMO API · monorepo init")
    # TODO: 初始化 DB pool / LLM gateway / Sentry
    yield
    print("[shutdown] CyberMOMO API")


app = FastAPI(
    title="CyberMOMO API",
    version="0.1.0",
    description="AI 先行社交平台后端",
    lifespan=lifespan,
)

# CORS
_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "CyberMOMO API",
        "version": "0.1.0",
        "status": "alive",
    }


@app.get("/healthz")
async def healthz():
    """Railway healthcheck endpoint."""
    return {"ok": True}


# TODO: 各业务模块 router 在这里挂上
# from src.auth.router import router as auth_router
# app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
