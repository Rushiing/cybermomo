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

from src.admin.router import router as admin_router
from src.agent_chat.router import router as agent_chat_router
from src.agent_self.router import router as agent_self_router
from src.auth.router import router as auth_router
from src.human_chat.router import router as chat_router
from src.match.router import router as match_router
from src.md.router import router as md_router
from src.room.router import router as room_router
from src.shared.settings import get_settings
from src.summary.router import router as summary_router


def _init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        print("[startup] Sentry 未启用(SENTRY_DSN 未配置)")
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            traces_sample_rate=0.05 if not settings.is_dev else 1.0,
            send_default_pii=False,  # 不上报用户邮箱等敏感字段
        )
        print(f"[startup] Sentry 启用 · env={settings.env}")
    except Exception as e:
        print(f"[startup] Sentry init 失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[startup] CyberMOMO API · env={settings.env}")
    print(f"[startup] CORS origins: {settings.cors_origins_list}")
    _init_sentry()
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
app.include_router(md_router, prefix="/api/md", tags=["md"])
app.include_router(match_router, prefix="/api/match", tags=["match"])
app.include_router(summary_router, prefix="/api/summary", tags=["summary"])
app.include_router(agent_chat_router, prefix="/api/agent_chat", tags=["agent_chat"])
app.include_router(agent_self_router, prefix="/api/me/agent", tags=["agent_self"])
app.include_router(room_router, prefix="/api/room", tags=["room"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])


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
