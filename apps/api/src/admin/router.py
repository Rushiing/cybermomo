"""
Admin API · 给外部 cron / 一次性 ops 调用,需要 X-Admin-Secret 头

- POST /api/admin/observation-sweep        24h 沉默自动结束 + 观察报告
- POST /api/admin/rerun-pipeline/{uid}     给某 user_id 重跑完整 pipeline(debug)
- POST /api/admin/backfill-embeddings      回填存量 md_segments / summaries 的 embedding(幂等)
- POST /api/admin/seed/insert              冷启动 · 插 20 mock 用户(同步,几秒)
- POST /api/admin/seed/run-pipeline        冷启动 · BackgroundTask 跑 mock pipeline
- GET  /api/admin/seed/status              冷启动 · 看 pipeline 进度
- GET  /api/admin/seed/verify              冷启动 · 只读校验 mock pool 数据
- GET  /api/admin/pipeline/incomplete      只读 · 列"有 match 没简报"的 user
- POST /api/admin/pipeline/repair          按 stage 补跑单 user 半成品 pipeline
- POST /api/admin/pipeline/repair-all      后台批量补跑所有未完成 user
- POST /api/admin/agent-chat/run-user/{uid} 定向跑一场新 Agent 互聊样本
- POST /api/admin/summary/redo-user/{uid}  定向重刷某 host 的 summary 卡片

Railway Cron Jobs 配置示例(observation sweep · 每小时):
   curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" \
        https://cybermomo-production.up.railway.app/api/admin/observation-sweep
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.agent_self.backfill import backfill_all
from src.agent_self.revisit import seed_revisit_after_silent_sweep
from src.auth.models import User
from src.human_chat.models import ChatSession
from src.human_chat.observation import run_observation_for_session
from src.match.models import Match, MatchHook
from src.match.pipeline import (
    find_users_with_incomplete_pipeline,
    resume_incomplete_pipeline_for_user,
    run_full_pipeline_for_user,
)
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
from src.summary.engine import run_summary_for_chat
from src.summary.models import Summary

router = APIRouter()

# repair-all 进程级并发护栏(codex review P1-3):BackgroundTask 在同一进程/event loop 里跑,
# 用一个 module flag 防止两次 repair-all 同时扫+补(否则同一 user 被两个后台任务重复补跑,
# 虽然 pipeline 内部有 pg advisory lock 兜底,但白跑一遍 LLM 浪费配额)。
_REPAIR_ALL_RUNNING = False
_SUMMARY_REDO_USER_RUNNING = False
_SUMMARY_REDO_USER_STATE: dict = {
    "status": "idle",
    "user_id": None,
    "username": None,
    "target_chat_count": 0,
    "processed_chat_count": 0,
    "started_at": None,
    "finished_at": None,
    "results": [],
    "errors": [],
}
_AGENT_CHAT_SAMPLE_RUNNING = False
_AGENT_CHAT_SAMPLE_STATE: dict = {
    "status": "idle",
    "user_id": None,
    "match_id": None,
    "stage": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "errors": [],
}


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


def _reset_summary_redo_state(*, user_id: int, username: str | None, target_count: int) -> None:
    _SUMMARY_REDO_USER_STATE.update({
        "status": "running",
        "user_id": user_id,
        "username": username,
        "target_chat_count": target_count,
        "processed_chat_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "results": [],
        "errors": [],
    })


def _reset_agent_chat_sample_state(*, user_id: int, match_id: int | None) -> None:
    _AGENT_CHAT_SAMPLE_STATE.update({
        "status": "running",
        "user_id": user_id,
        "match_id": match_id,
        "stage": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "errors": [],
    })


async def _bg_run_agent_chat_user_sample(
    *,
    user_id: int,
    match_id: int | None,
    max_turns: int,
    avoid_previous: bool,
    force_clear_running: bool,
    direction_hint: str | None,
    direction_target_user_id: int | None,
) -> None:
    global _AGENT_CHAT_SAMPLE_RUNNING
    try:
        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None:
                raise ValueError("user not found")

            if match_id is not None:
                match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
                if match is None:
                    raise ValueError("match not found")
                if user_id not in {match.user_a_id, match.user_b_id}:
                    raise ValueError("user 不属于该 match")
            else:
                match = (await db.execute(
                    select(Match)
                    .where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
                    .where(
                        select(func.count())
                        .select_from(MatchHook)
                        .where(MatchHook.match_id == Match.id)
                        .scalar_subquery() > 0
                    )
                    .order_by(Match.overall_score.desc(), Match.id.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if match is None:
                    raise ValueError("没有找到带 hooks 的 match")

            _AGENT_CHAT_SAMPLE_STATE["match_id"] = match.id
            running_chats = (await db.execute(
                select(AgentChat)
                .where(AgentChat.match_id == match.id, AgentChat.status == "running")
            )).scalars().all()
            if running_chats and not force_clear_running:
                running_ids = [chat.id for chat in running_chats]
                raise RuntimeError(f"match {match.id} 已有 running agent_chat={running_ids}")
            if running_chats and force_clear_running:
                now = datetime.now(timezone.utc)
                for stale in running_chats:
                    stale.status = "done_terminated"
                    stale.end_reason = "manual_interrupted"
                    stale.ended_at = now
                await db.commit()

            avoid_topic_refs: list[str] = []
            if avoid_previous:
                rows = (await db.execute(
                    select(AgentChatMessage.topic_ref)
                    .join(AgentChat, AgentChat.id == AgentChatMessage.agent_chat_id)
                    .where(AgentChat.match_id == match.id)
                )).scalars().all()
                avoid_topic_refs = list(dict.fromkeys(str(r) for r in rows if r))

            _AGENT_CHAT_SAMPLE_STATE["stage"] = "agent_chat"
            chat = await run_agent_chat(
                db,
                match=match,
                max_turns=max_turns,
                avoid_topic_refs=avoid_topic_refs,
                direction_hint=direction_hint,
                direction_target_user_id=direction_target_user_id,
            )
            match.status = "agent_chat_done" if "done" in (chat.status or "") else "agent_chat_running"
            await db.commit()

            _AGENT_CHAT_SAMPLE_STATE["stage"] = "summary"
            summaries = await run_summary_for_chat(db, chat=chat)
            messages = (await db.execute(
                select(AgentChatMessage)
                .where(AgentChatMessage.agent_chat_id == chat.id)
                .order_by(AgentChatMessage.turn)
            )).scalars().all()
            host_summary = next((s for s in summaries if s.host_user_id == user_id), None)
            _AGENT_CHAT_SAMPLE_STATE["result"] = {
                "user_id": user_id,
                "match_id": match.id,
                "peer_user_id": match.user_b_id if match.user_a_id == user_id else match.user_a_id,
                "agent_chat": {
                    "id": chat.id,
                    "status": chat.status,
                    "end_reason": chat.end_reason,
                    "turns": len(messages),
                },
                "host_summary": None if host_summary is None else {
                    "id": host_summary.id,
                    "verdict": host_summary.verdict,
                    "recommended_action": host_summary.recommended_action,
                    "highlights": host_summary.highlights,
                    "risks": host_summary.risks,
                    "evidence_chunks": host_summary.evidence_chunks,
                },
                "messages": [
                    {
                        "turn": msg.turn,
                        "speaker_user_id": msg.speaker_user_id,
                        "intent": msg.intent,
                        "topic_ref": msg.topic_ref,
                        "utterance": msg.utterance,
                    }
                    for msg in messages
                ],
            }
            _AGENT_CHAT_SAMPLE_STATE["status"] = "done"
    except Exception as e:
        _AGENT_CHAT_SAMPLE_STATE["status"] = "failed"
        _AGENT_CHAT_SAMPLE_STATE["errors"].append(f"{type(e).__name__}: {e}")
    finally:
        _AGENT_CHAT_SAMPLE_STATE["stage"] = None
        _AGENT_CHAT_SAMPLE_STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
        _AGENT_CHAT_SAMPLE_RUNNING = False


async def _summary_redo_candidates(user_id: int, limit: int) -> list[int]:
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(Summary.agent_chat_id)
            .join(AgentChat, AgentChat.id == Summary.agent_chat_id)
            .where(
                Summary.host_user_id == user_id,
                Summary.summary_type == "agent_chat",
                Summary.agent_chat_id.is_not(None),
                select(func.count())
                .select_from(AgentChatMessage)
                .where(AgentChatMessage.agent_chat_id == Summary.agent_chat_id)
                .scalar_subquery() > 0,
            )
            .order_by(Summary.created_at.desc())
            .limit(limit)
        )).scalars().all()
    return list(dict.fromkeys(rows))


async def _bg_redo_summaries_for_user(user_id: int, limit: int) -> None:
    global _SUMMARY_REDO_USER_RUNNING
    try:
        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            username = user.username if user else None
        chat_ids = await _summary_redo_candidates(user_id, limit)
        _reset_summary_redo_state(user_id=user_id, username=username, target_count=len(chat_ids))

        for chat_id in chat_ids:
            try:
                async with SessionLocal() as db:
                    chat = (await db.execute(
                        select(AgentChat).where(AgentChat.id == chat_id)
                    )).scalar_one_or_none()
                    if chat is None:
                        raise ValueError("agent_chat missing")
                    await db.execute(delete(Summary).where(
                        Summary.agent_chat_id == chat_id,
                        Summary.host_user_id == user_id,
                        Summary.summary_type == "agent_chat",
                    ))
                    await db.commit()
                    new_summaries = await run_summary_for_chat(db, chat=chat)
                    mine = [s for s in new_summaries if s.host_user_id == user_id]
                    if not mine:
                        raise RuntimeError("summary was not recreated")
                    created = mine[0]
                    _SUMMARY_REDO_USER_STATE["results"].append({
                        "chat_id": chat_id,
                        "summary_id": created.id,
                        "verdict": created.verdict,
                        "recommended_action": created.recommended_action,
                    })
            except Exception as e:
                _SUMMARY_REDO_USER_STATE["errors"].append({
                    "chat_id": chat_id,
                    "error": f"{type(e).__name__}: {e}",
                })
            finally:
                _SUMMARY_REDO_USER_STATE["processed_chat_count"] += 1

        _SUMMARY_REDO_USER_STATE["status"] = (
            "failed" if _SUMMARY_REDO_USER_STATE["errors"] else "done"
        )
        _SUMMARY_REDO_USER_STATE["finished_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        _SUMMARY_REDO_USER_RUNNING = False


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


@router.post("/agent-chat/run-user/{user_id}")
async def agent_chat_run_user_sample(
    user_id: int,
    background_tasks: BackgroundTasks,
    match_id: Optional[int] = None,
    max_turns: int = 10,
    avoid_previous: bool = False,
    force_clear_running: bool = False,
    direction_hint: Optional[str] = None,
    direction_target_user_id: Optional[int] = None,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    定向给某 user 跑一场新的 Agent 互聊样本,并生成 summary。

    用途是 prompt/effect 调试:不新建 match,只复用已有 match + hooks。
    """
    global _AGENT_CHAT_SAMPLE_RUNNING
    _require_admin(x_admin_secret)
    if _AGENT_CHAT_SAMPLE_RUNNING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "agent-chat sample 已在运行中",
                "state": _AGENT_CHAT_SAMPLE_STATE,
            },
        )
    if max_turns < 4 or max_turns > 14:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="max_turns 必须在 4..14")
    target_user_id = direction_target_user_id
    if direction_hint and target_user_id is None:
        target_user_id = user_id

    _AGENT_CHAT_SAMPLE_RUNNING = True
    _reset_agent_chat_sample_state(user_id=user_id, match_id=match_id)
    background_tasks.add_task(
        _bg_run_agent_chat_user_sample,
        user_id=user_id,
        match_id=match_id,
        max_turns=max_turns,
        avoid_previous=avoid_previous,
        force_clear_running=force_clear_running,
        direction_hint=direction_hint,
        direction_target_user_id=target_user_id,
    )
    return {
        "ok": True,
        "accepted": True,
        "user_id": user_id,
        "match_id": match_id,
        "hint": "GET /api/admin/agent-chat/run-user/status 看进度和结果",
    }


@router.get("/agent-chat/run-user/status")
async def agent_chat_run_user_sample_status(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """返回定向 Agent 互聊样本的进程级状态"""
    _require_admin(x_admin_secret)
    return _AGENT_CHAT_SAMPLE_STATE


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


@router.post("/summary/redo-user/{user_id}")
async def summary_redo_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    limit: int = 12,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    定向重刷某个 host_user_id 能看到的 agent_chat summary。

    只删除并重建该 host 的 Summary,不动同场对方 host 的卡片。
    用于 prompt/verdict 校准后,挑测试账号验证旧对话在新规则下的判定。
    """
    global _SUMMARY_REDO_USER_RUNNING
    _require_admin(x_admin_secret)
    if _SUMMARY_REDO_USER_RUNNING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="summary redo-user 已在运行中,GET /summary/redo-user/status 看进度",
        )
    if limit < 1 or limit > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="limit 必须在 1..50")

    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user not found")
        username = user.username
    chat_ids = await _summary_redo_candidates(user_id, limit)
    _SUMMARY_REDO_USER_RUNNING = True
    _reset_summary_redo_state(user_id=user_id, username=username, target_count=len(chat_ids))
    background_tasks.add_task(_bg_redo_summaries_for_user, user_id, limit)
    return {
        "ok": True,
        "accepted": True,
        "user_id": user_id,
        "username": username,
        "target_chat_count": len(chat_ids),
        "limit": limit,
        "hint": "GET /api/admin/summary/redo-user/status 看进度",
    }


@router.get("/summary/redo-user/status")
async def summary_redo_user_status(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """返回定向重刷 user summary 的进程级状态"""
    _require_admin(x_admin_secret)
    return _SUMMARY_REDO_USER_STATE


@router.post("/summary/redo-chat/{chat_id}")
async def summary_redo_chat(
    chat_id: int,
    host_user_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    定向重刷某一场 agent_chat 对某个 host 的单张 summary。

    用于 redo-user 某张卡重建失败后的补偿,或人工点名复查一张卡。
    """
    _require_admin(x_admin_secret)
    async with SessionLocal() as db:
        chat = (await db.execute(
            select(AgentChat).where(AgentChat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent_chat not found")
        msg_count = (await db.execute(
            select(func.count()).select_from(AgentChatMessage)
            .where(AgentChatMessage.agent_chat_id == chat_id)
        )).scalar_one()
        if msg_count == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="agent_chat has no messages")
        await db.execute(delete(Summary).where(
            Summary.agent_chat_id == chat_id,
            Summary.host_user_id == host_user_id,
            Summary.summary_type == "agent_chat",
        ))
        await db.commit()
        new_summaries = await run_summary_for_chat(db, chat=chat)
        mine = [s for s in new_summaries if s.host_user_id == host_user_id]
        if not mine:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="summary was not recreated",
            )
        created = mine[0]
        return {
            "ok": True,
            "chat_id": chat_id,
            "summary_id": created.id,
            "host_user_id": host_user_id,
            "verdict": created.verdict,
            "recommended_action": created.recommended_action,
        }


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


# ========================================
# Pipeline 续跑修复(audit P0-4 / codex stab-P0-1)
# 部署中断/LLM失败导致"有 match 没简报"的用户,按 stage 补跑
# ========================================


@router.get("/pipeline/incomplete")
async def pipeline_incomplete(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    只读诊断:列出"有 match 但缺 summary"的 user_id(部署中断/LLM 失败的受害者)。
    可随时调,不触发任何写入。
    """
    _require_admin(x_admin_secret)
    try:
        uids = await find_users_with_incomplete_pipeline()
        return {"ok": True, "incomplete_user_count": len(uids), "user_ids": uids}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"扫描失败: {type(e).__name__}: {e}",
        )


@router.post("/pipeline/repair")
async def pipeline_repair_one(
    user_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    给单个 user 按 stage 补跑半成品 pipeline(同步,返回修复报告)。
    幂等:每步前查产物,有就跳过。单 user 慢则几十秒-几分钟(看缺多少 LLM 步)。
    """
    _require_admin(x_admin_secret)
    try:
        report = await resume_incomplete_pipeline_for_user(user_id)
        return {"ok": True, **report}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修复失败: {type(e).__name__}: {e}",
        )


async def _bg_repair_all() -> None:
    """BackgroundTask:扫所有未完成 user 串行补跑。

    进程级 flag(_REPAIR_ALL_RUNNING)由调用方 endpoint 在 add_task 前同步置 True
    (check-and-set 之间无 await,asyncio 单线程下原子),本函数只负责在结束时清掉。
    """
    global _REPAIR_ALL_RUNNING
    try:
        try:
            uids = await find_users_with_incomplete_pipeline()
        except Exception as e:
            print(f"[pipeline-repair-all] scan failed: {e}")
            return
        print(f"[pipeline-repair-all] {len(uids)} users to repair")
        for uid in uids:
            try:
                await resume_incomplete_pipeline_for_user(uid)
            except Exception as e:
                print(f"[pipeline-repair-all] user={uid} failed: {e}")
    finally:
        _REPAIR_ALL_RUNNING = False


@router.post("/pipeline/repair-all")
async def pipeline_repair_all(
    background_tasks: BackgroundTasks,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
):
    """
    扫所有"有 match 没简报"的 user,后台串行补跑。立即返 202 + 待修复数。
    用于内测中"一批用户后台链路半路丢"的批量恢复。进度看 api 日志
    [pipeline-resume] / [pipeline-repair-all]。
    """
    global _REPAIR_ALL_RUNNING
    _require_admin(x_admin_secret)
    if _REPAIR_ALL_RUNNING:
        # 已有一轮在跑,别叠;返 409 让调用方等它跑完再调
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="repair-all 已在运行中,等它跑完(看 api 日志 [pipeline-repair-all])再调",
        )
    # 占位:check 之后立刻置 True,中间无 await(asyncio 单线程原子),关掉并发叠跑窗口。
    # 由 _bg_repair_all 的 finally 负责清回 False。
    _REPAIR_ALL_RUNNING = True
    try:
        uids = await find_users_with_incomplete_pipeline()
    except Exception as e:
        _REPAIR_ALL_RUNNING = False  # 没排上后台任务,得把占位还回去
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"扫描失败: {type(e).__name__}: {e}",
        )
    background_tasks.add_task(_bg_repair_all)
    return {
        "ok": True,
        "accepted": True,
        "incomplete_user_count": len(uids),
        "user_ids": uids,
        "hint": "后台串行补跑,进度看 api 日志;完成后再调 /pipeline/incomplete 应返 0",
    }
