"""
CyberMomo 灵魂快照 · 服务端
- 托管 prototype-v0.4.html
- /api/messages 代理到智谱 GLM-5（通过 dashscope Anthropic 兼容端点）
- /api/log-generation 保存生成记录（consent=true 时）
- /api/log-feedback 保存用户反馈
"""
import json
import os
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
UPSTREAM = "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages"
DATABASE_URL = os.environ.get("DATABASE_URL", "")

INIT_SQL = """
CREATE TABLE IF NOT EXISTS generations (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    prompt_version TEXT,
    quiz_version TEXT,
    model TEXT,
    nickname TEXT,
    age_band TEXT,
    gender TEXT,
    mbti TEXT,
    dimension_scores JSONB,
    raw_answers JSONB,
    supplement JSONB,
    md_output TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    generation_id INTEGER REFERENCES generations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    payload JSONB
);
"""

pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    if DATABASE_URL:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(INIT_SQL)
        print("[startup] postgres pool ready + schema initialized")
    else:
        print("[startup] DATABASE_URL not set — logging endpoints will return skipped:true")
    yield
    if pool:
        await pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return FileResponse("prototype-v0.4.html")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "db": pool is not None}


@app.post("/api/messages")
async def proxy_messages(req: Request):
    if not GLM_API_KEY:
        raise HTTPException(500, "GLM_API_KEY not configured on server")
    body = await req.body()
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                UPSTREAM,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": GLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
            )
    except httpx.HTTPError as e:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"upstream: {e}"}},
        )
    try:
        data = resp.json()
    except ValueError:
        data = {"error": {"message": "upstream returned non-JSON", "raw": resp.text[:500]}}
    return JSONResponse(content=data, status_code=resp.status_code)


@app.post("/api/log-generation")
async def log_generation(req: Request):
    if not pool:
        return {"skipped": True, "reason": "no_database"}
    data = await req.json()
    if not data.get("consent"):
        return {"skipped": True, "reason": "no_consent"}
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO generations
                (prompt_version, quiz_version, model, nickname, age_band, gender, mbti,
                 dimension_scores, raw_answers, supplement, md_output)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11)
            RETURNING id
            """,
            data.get("prompt_version"),
            data.get("quiz_version"),
            data.get("model"),
            data.get("nickname"),
            data.get("age_band"),
            data.get("gender"),
            data.get("mbti"),
            json.dumps(data.get("dimension_scores") or {}, ensure_ascii=False),
            json.dumps(data.get("raw_answers") or [], ensure_ascii=False),
            json.dumps(data.get("supplement") or {}, ensure_ascii=False),
            data.get("md_output"),
        )
    return {"generation_id": row["id"]}


@app.post("/api/log-feedback")
async def log_feedback(req: Request):
    if not pool:
        return {"skipped": True, "reason": "no_database"}
    data = await req.json()
    gen_id = data.get("generation_id")
    payload = data.get("payload")
    if gen_id is None:
        return {"skipped": True, "reason": "no_generation_id"}
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO feedback (generation_id, payload) VALUES ($1, $2::jsonb)",
            gen_id,
            json.dumps(payload, ensure_ascii=False),
        )
    return {"ok": True}
