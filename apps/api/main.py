"""
CyberMOMO API · FastAPI entrypoint

MVP 阶段 monolith,模块通过 router 划分。

Phase 0:auth router skeleton + healthz
Phase 1:Google OAuth 完整 + .md 创建
Phase 2:匹配 + Agent 互聊
Phase 3:摘要 + 个人房间
Phase 4:真人聊天 + callout + 观察报告
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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


_DEFAULT_JWT_SECRET = "dev-jwt-secret-not-for-prod-replace-me"


def _assert_prod_config_safe() -> None:
    """
    非 dev 环境启动时 fail-fast 校验关键安全配置。

    背景(audit-2026-06 P0-3):所有配置都有默认值,`env` 默认 dev → `is_dev=True`
    会启用 X-Mock-User-Id 越权 + 非 Secure cookie + 默认 JWT secret。一次 env 丢失
    (新 deploy / fork / 误清变量)就静默全站敞开。这里把"配置错"从"静默不安全"
    变成"启动即 crash",逼运维补齐。
    """
    settings = get_settings()
    if settings.is_dev:
        return  # dev 环境允许宽松配置

    problems: list[str] = []
    if settings.jwt_secret == _DEFAULT_JWT_SECRET or len(settings.jwt_secret) < 16:
        problems.append("JWT_SECRET 仍是默认值或过短(需 ≥16 字符的随机串)")
    if not settings.admin_secret:
        problems.append("ADMIN_SECRET 未设置")
    if any("localhost" in o or "127.0.0.1" in o for o in settings.cors_origins_list):
        problems.append(f"CORS_ORIGINS 含 localhost(当前:{settings.cors_origins_list})")
    if not settings.cors_origins_list:
        problems.append("CORS_ORIGINS 为空")

    if problems:
        msg = (
            f"[startup] 生产配置不安全,拒绝启动(env={settings.env}):\n  - "
            + "\n  - ".join(problems)
        )
        raise RuntimeError(msg)
    print(f"[startup] 生产配置校验通过 · env={settings.env}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[startup] CyberMOMO API · env={settings.env}")
    print(f"[startup] CORS origins: {settings.cors_origins_list}")
    _assert_prod_config_safe()  # 非 dev 配置不安全直接 crash
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
    expose_headers=["X-Duration-Ms"],
)


# Timing middleware — 写 response header + 慢请求日志
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Duration-Ms"] = f"{elapsed_ms:.0f}"
    # 只打慢请求(> 300ms),避免日志洪水
    if elapsed_ms > 300:
        print(
            f"[slow] {request.method} {request.url.path} "
            f"{elapsed_ms:.0f}ms status={response.status_code}"
        )
    return response


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
