"""
Session token (JWT) + cookie 工具

设计:
- 用户登录成功 → 创建 JWT,放 HttpOnly + Secure + SameSite=None cookie
  (跨域 web 前端 XHR 需要 SameSite=None;dev/localhost 退化到 Lax 不带 Secure)
- 每次请求 → src.auth.deps.get_current_user 读 cookie → verify_session_token → 拿 user_id
- 登出 → 清 cookie
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response
from jose import JWTError, jwt

from src.shared.settings import get_settings


_ALGO = "HS256"


def create_session_token(user_id: int) -> str:
    """
    给 user_id 签发一个 JWT(HS256)。
    claims: { sub, iat, exp }
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.session_max_age)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def verify_session_token(token: str) -> Optional[int]:
    """
    解码并校验 JWT,返回 user_id;失败返回 None(过期 / 签名错 / 损坏)。
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
    except JWTError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


def read_session_user_id(request: Request) -> Optional[int]:
    """从 cookie 拿出 user_id;没有或无效返回 None"""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return verify_session_token(token)


def set_session_cookie(response: Response, user_id: int) -> None:
    """登录成功后写 session cookie"""
    settings = get_settings()
    token = create_session_token(user_id)
    secure = not settings.is_dev
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        secure=secure,
        # 跨子域 / 跨站 XHR 必须 None+Secure(prod);dev 用 Lax 配合 HTTP
        samesite="none" if secure else "lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """登出 — 清掉 session cookie"""
    settings = get_settings()
    secure = not settings.is_dev
    response.set_cookie(
        key=settings.session_cookie_name,
        value="",
        max_age=0,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
    )


# ========================================
# OAuth state(CSRF nonce)cookie 工具
# ========================================
#
# OAuth state 是 CSRF 防护:
# - /login 时生成随机 state,塞 cookie + 拼到 Google authorize URL
# - /callback 检查 cookie state 跟 query state 一致

OAUTH_STATE_COOKIE = "cm_oauth_state"
OAUTH_STATE_TTL = 600  # 10 分钟


def set_oauth_state_cookie(response: Response, state: str) -> None:
    settings = get_settings()
    secure = not settings.is_dev
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_TTL,
        httponly=True,
        secure=secure,
        samesite="lax",  # state 用 lax 够 — top-level navigation 走得通
        path="/",
    )


def read_oauth_state_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(OAUTH_STATE_COOKIE)


def clear_oauth_state_cookie(response: Response) -> None:
    settings = get_settings()
    secure = not settings.is_dev
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
