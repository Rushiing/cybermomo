"""
CyberMOMO API · FastAPI entrypoint

MVP 阶段 monolith,模块通过 router 划分。

Phase 0:auth router skeleton + healthz
Phase 1:Google OAuth 完整 + .md 创建
Phase 2:匹配 + Agent 互聊
Phase 3:摘要 + 个人房间
Phase 4:真人聊天 + callout + 观察报告
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.auth.router import router as auth_router
from src.shared.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[startup] CyberMOMO API · env={settings.env}")
    print(f"[startup] CORS origins: {settings.cors_origins_list}")
    # TODO Phase 0 完成后:DB 连通性自检 / Sentry init / Redis(future)
    yield
    print("[shutdown] CyberMOMO API")


app = FastAPI(
    title="CyberMOMO API",
    version="0.1.0",
    description="AI 先行社交平台后端",
    lifespan=lifespan,
)

# ========================================
# 中间件
# ========================================
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================
# Router 挂载
# ========================================
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# TODO Phase 1+:逐模块挂上
# from src.md.router import router as md_router
# app.include_router(md_router, prefix="/api/md", tags=["md"])
# from src.match.router import router as match_router
# app.include_router(match_router, prefix="/api/match", tags=["match"])
# from src.room.router import router as room_router
# app.include_router(room_router, prefix="/api/room", tags=["room"])
# from src.summary.router import router as summary_router
# app.include_router(summary_router, prefix="/api/summary", tags=["summary"])
# from src.human_chat.router import router as chat_router
# app.include_router(chat_router, prefix="/api/chat", tags=["chat"])


# ========================================
# 顶级路由
# ========================================
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
