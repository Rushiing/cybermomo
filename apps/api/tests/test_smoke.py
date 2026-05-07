"""
基础 smoke test · 验证 FastAPI 应用能起来 + 顶级路由通

不依赖数据库,只测应用能 import + 路由响应。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_root(client: AsyncClient):
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "CyberMOMO API"
    assert body["status"] == "alive"


async def test_auth_me_requires_auth(client: AsyncClient):
    """/api/auth/me 需要 auth(mock 或 JWT)"""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_oauth_login_not_implemented(client: AsyncClient):
    """OAuth 接入前 /api/auth/google/login 应 501"""
    resp = await client.get("/api/auth/google/login")
    assert resp.status_code == 501


async def test_md_me_requires_auth(client: AsyncClient):
    """/api/md/me 需要 auth 头(mock 或 JWT)"""
    resp = await client.get("/api/md/me")
    assert resp.status_code == 401
