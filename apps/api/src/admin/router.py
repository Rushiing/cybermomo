"""
Admin API · 给外部 cron / 一次性 ops 调用,需要 X-Admin-Secret 头

- POST /api/admin/observation-sweep        24h 沉默自动结束 + 观察报告
- POST /api/admin/rerun-pipeline/{uid}     给某 user_id 重跑完整 pipeline(debug)
- POST /api/admin/backfill-embeddings      回填存量 md_segments / summaries 的 embedding(幂等)
- POST /api/admin/seed/insert              冷启动 · 插 20 mock 用户(同步,几秒)
- POST /api/admin/seed/run-pipeline        冷启动 · BackgroundTask 跑 mock pipeline
- GET  /api/admin/seed/status              冷启动 · 看 pipeline 进度
- GET  /api/admin/seed/verify              冷启动 · 只读校验 mock pool 数据

Railway Cron Jobs 配置示例(observation sweep · 每小时):
   curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" \
        https://cybermomo-production.up.railway.app/api/admin/observation-sweep
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_self.backfill import backfill_all
from src.agent_self.revisit import seed_revisit_after_silent_sweep
from src.human_chat.models import ChatSession
from src.human_chat.observation import run_observation_for_session
from src.match.pipeline import run_full_pipeline_for_user
from src.seed.operations import (
    get_pipeline_job_state,
    get_redo_summaries_job_state,
    insert_all_mock_users,
    is_pipeline_running,
    is_redo_summaries_running,
    redo_summaries_for_mock_pool,
    run_pipeline_for_all_mock_users,
    verify_all,
)
from src.shared.db import SessionLocal, get_session
from src.shared.settings import get_settings

router = APIRouter()


def _require_admin(secret: Optional[str]) -> None:
    settings = get_settings()
    if not settings.admin_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_SECRET 未配置 — admin endpoints 关闭",
        )
    if secret != settings.admin_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid admin secret")


SILENCE_THRESHOLD = timedelta(hours=24)


async def _bg_observation_and_revisit(session_id: int, host_user_id: int) -> None:
    """BackgroundTask:跑一份观察报告 + 种 Agent 回访 conversation(LLM 重活)"""
    try:
        async with SessionLocal() as bg_db:
            fresh_session = (await bg_db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )).scalar_one_or_none()
            if fresh_session:
                await run_observation_for_session(
                    bg_db, session=fresh_session, host_user_id=host_user_id
                )
    except Exception as e:
        print(f"[sweep-bg] observation failed session={session_id} host={host_user_id}: {e}")

    try:
        await seed_revisit_after_silent_sweep(session_id, host_user_id)
    except Exception as e:
        print(f"[sweep-bg] revisit failed session={session_id} host={host_user_id}: {e}")


@router.post("/observation-sweep")
async def observation_sweep(
    background_tasks: BackgroundTasks,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    扫描 active 但 last_message_at > 24h 之前的 chat_sessions,
    标 ended_quit(同步,快 SQL),然后用 BackgroundTask 异步跑双方
    观察报告 + Agent 回访(慢 LLM)。

    设计:cron HTTP 请求一秒返回,LLM 工作在 api 服务后台跑完。
    幂等:已结束的 session 不会重复处理。
    """
    _require_admin(x_admin_secret)

    cutoff = datetime.now(timezone.utc) - SILENCE_THRESHOLD

    # 找 silent sessions:
    # 1) last_message_at 早于 cutoff,或
    # 2) 还没人发消息(NULL)且 created_at 早于 cutoff(空 session 也清)
    stmt = select(ChatSession).where(
        ChatSession.status == "active",
        or_(
            ChatSession.last_message_at < cutoff,
            and_(
                ChatSession.last_message_at.is_(None),
                ChatSession.created_at < cutoff,
            ),
        ),
    )
    silent_sessions = (await db.execute(stmt)).scalars().all()

    swept: list[dict] = []
    for session in silent_sessions:
        session.status = "ended_quit"
        session.exit_action = "quit"
        session.ended_at = datetime.now(timezone.utc)
        await db.commit()

        # 调度异步 LLM 工作 — 响应返回后才开始跑(BackgroundTask 在 api 服务里跑)
        for host_uid in [session.user_a_id, session.user_b_id]:
            background_tasks.add_task(
                _bg_observation_and_revisit, session.id, host_uid
            )

        swept.append({
            "session_id": session.id,
            "user_a_id": session.user_a_id,
            "user_b_id": session.user_b_id,
            "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
        })

    return {
        "cutoff": cutoff.isoformat(),
        "swept_count": len(swept),
        "scheduled_jobs": len(swept) * 2,  # 每场 session 2 个 host job
        "sessions": swept,
    }


@router.post("/rerun-pipeline/{user_id}")
async def rerun_pipeline(
    user_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    Debug 用:给某 user_id 重跑完整 pipeline(匹配 + 脱敏 + Agent 互聊 + 摘要)
    跳过已 match 过的 pair,所以幂等。
    """
    _require_admin(x_admin_secret)

    try:
        await run_full_pipeline_for_user(user_id)
        return {"ok": True, "user_id": user_id}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"pipeline 失败: {e}",
        )


@router.post("/backfill-embeddings")
async def backfill_embeddings(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    一次性回填:把 md_segments / summaries 里 embedding IS NULL 的行补上,
    让 RAG 检索能用上存量数据。

    幂等:已有 embedding 的行跳过。每行独立 commit,中途失败不丢前面进度。

    注意:HTTP 同步调用 — 当前 MVP 数据量小(<100 行)能在分钟级跑完。
    数据量上千后需要改成 BackgroundTask + 进度查询。
    """
    _require_admin(x_admin_secret)
    try:
        result = await backfill_all(verbose=False)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"backfill 失败: {e}",
        )


# ========================================
# 冷启动 seed · 远程触发(给 Claude 用,免本地配 DATABASE_URL)
# ========================================


@router.post("/seed/insert")
async def seed_insert_users(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    把 src.seed.archetypes.MOCK_USERS 全部 upsert 进库(几秒,同步)。

    幂等:按 username 查重,已存在的 mock_xxx_x 用户跳过插入。
    返回结构化结果(total / newly_created / already_exists / users)。

    跟 cron 不同,这是一次性 ops 调用,所以同步返回结果方便 caller 一眼看完。
    """
    _require_admin(x_admin_secret)
    try:
        result = await insert_all_mock_users()
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"seed insert 失败: {type(e).__name__}: {e}",
        )


@router.post("/seed/run-pipeline")
async def seed_run_pipeline(
    background_tasks: BackgroundTasks,
    user_limit: Optional[int] = None,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    用 BackgroundTask 异步跑 mock 用户的全链路 pipeline(match → desensitize →
    agent_chat → summary)。立即返 202 + job 概况,实际跑 30-90 分钟。

    并发保护:如果已有 pipeline 在跑(进程级状态),返 409。

    user_limit 可选 — 跑前 N 个 mock 用户(默认全部 20)。8 人 × top_k=5 大约
    产 30-40 对 pair(match service 内部 dedupe)。

    幂等:run_full_pipeline_for_user 内部 _existing_match_partners 去重已 match 过的对。
    """
    _require_admin(x_admin_secret)

    if is_pipeline_running():
        existing = get_pipeline_job_state()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"pipeline 已在跑(processed={existing['processed_user_count']}/"
                f"{existing['target_user_count']}),GET /seed/status 看进度"
            ),
        )

    background_tasks.add_task(
        run_pipeline_for_all_mock_users, user_limit=user_limit
    )
    return {
        "ok": True,
        "accepted": True,
        "user_limit": user_limit,
        "hint": "GET /api/admin/seed/status 看进度,可能需要 30-90 分钟",
    }


@router.get("/seed/status")
async def seed_pipeline_status(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    返回 pipeline job 当前状态(进程级 in-memory state):
      status: idle | running | done | failed
      processed_user_count / target_user_count / current_user_id
      started_at / finished_at
      errors: [{user_id, error}]

    Railway 重启会清空,但 pipeline 本身幂等可重跑。
    """
    _require_admin(x_admin_secret)
    return get_pipeline_job_state()


@router.post("/seed/redo-summaries")
async def seed_redo_summaries(
    background_tasks: BackgroundTasks,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    Prompt 校准后:只用当前 SUMMARY_SYSTEM_TEMPLATE 在**同一批已有 mock chat**
    上重新生成 summary,不重跑 agent_chat。用于直接对比新旧 prompt 效果。

    行为:
      - 找所有涉及 mock 用户的 AgentChat(status=done_natural)
      - 删除这些 chat 关联的旧 Summary
      - 用当前 prompt 重新跑 run_summary_for_chat
      - AgentChat / AgentChatMessage 保留不动(真实历史)

    立即返 202 + job 概况。轮询 GET /seed/redo-status 看进度。
    并发保护:已在跑返 409。
    """
    _require_admin(x_admin_secret)

    if is_redo_summaries_running():
        existing = get_redo_summaries_job_state()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"redo-summaries 已在跑(processed={existing['processed_chat_count']}/"
                f"{existing['target_chat_count']}),GET /seed/redo-status 看进度"
            ),
        )

    background_tasks.add_task(redo_summaries_for_mock_pool)
    return {
        "ok": True,
        "accepted": True,
        "hint": "GET /api/admin/seed/redo-status 看进度;~15-25 分钟,看 chat 数",
    }


@router.get("/seed/redo-status")
async def seed_redo_status(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """返回 redo-summaries job 的进程级 state(跟 /seed/status 独立)"""
    _require_admin(x_admin_secret)
    return get_redo_summaries_job_state()


@router.get("/seed/verify")
async def seed_verify(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    只读校验 mock pool:
      pool:user 数 + archetype / gender / age 分布
      agent_chats:总数 + status / end_reason 分布
      summaries:总数 + verdict 分布(对照 AGENTS.md §3.5 target 30/50/20%)
      health_warnings:数量异常 / verdict 偏离 target ±10% 的提示
      ok:health_warnings 为空 = 通过

    不触发任何写入,可随时调。
    """
    _require_admin(x_admin_secret)
    try:
        return await verify_all()
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"verify 失败: {type(e).__name__}: {e}",
        )
