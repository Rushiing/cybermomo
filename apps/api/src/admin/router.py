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


# ========================================
# 临时:Voice audit · prompt "人机味儿" 审计样本(整段可删)
# ========================================


@router.get("/voice-audit-sample")
async def voice_audit_sample(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    一次性 read-only:7 类 LLM 出口近期样本,给 prompt 工程做"人机味儿"审计。
    返回大 JSON,字段:
      agent_chat_messages / summary_after_chat / prebriefing / observation /
      agent_self_assistant / chat_callouts / match_hooks
    用完想删,把整段(本注释 + 这个函数)cut 掉即可,顶部 imports 不动。
    """
    _require_admin(x_admin_secret)

    from sqlalchemy import desc
    from src.agent_chat.models import AgentChat, AgentChatMessage
    from src.agent_self.models import AgentConversationMessage
    from src.human_chat.models import ChatCallout
    from src.match.models import MatchHook
    from src.summary.models import Summary

    def _trunc(s, n=400):
        s = (s or "").strip()
        return s if len(s) <= n else s[:n] + "…"

    def _hl(items):
        return [
            (i.get("text") or "").strip()
            for i in (items or [])
            if isinstance(i, dict) and i.get("text")
        ]

    # 1. agent_chat 互聊全量(反"装"硬约束已校准 · 反向基线)
    chats = (
        await db.execute(
            select(AgentChat)
            .where(AgentChat.status.in_(["done_natural", "done_terminated"]))
            .order_by(desc(AgentChat.id))
            .limit(5)
        )
    ).scalars().all()
    chats_out = []
    for chat in chats:
        msgs = (
            await db.execute(
                select(AgentChatMessage)
                .where(AgentChatMessage.agent_chat_id == chat.id)
                .order_by(AgentChatMessage.turn)
            )
        ).scalars().all()
        chats_out.append({
            "chat_id": chat.id,
            "status": chat.status,
            "end_reason": chat.end_reason,
            "messages": [
                {
                    "turn": m.turn,
                    "speaker": m.speaker_user_id,
                    "intent": m.intent,
                    "warmth_delta": (m.private_signals or {}).get("warmth_delta"),
                    "disclosure": (m.private_signals or {}).get("disclosure_level"),
                    "utterance": _trunc(m.utterance, 400),
                }
                for m in msgs
            ],
        })

    async def _take_summaries(stype: str, n: int):
        rows = (
            await db.execute(
                select(Summary)
                .where(Summary.summary_type == stype)
                .order_by(desc(Summary.id))
                .limit(n)
            )
        ).scalars().all()
        return [
            {
                "id": s.id,
                "verdict": s.verdict,
                "host": s.host_user_id,
                "recommended_action": s.recommended_action,
                "highlights": [_trunc(t, 350) for t in _hl(s.highlights)],
                "risks": [_trunc(t, 350) for t in _hl(s.risks)],
            }
            for s in rows
        ]

    summary_rows = await _take_summaries("agent_chat", 10)
    prebriefing_rows = await _take_summaries("pre_briefing", 5)
    observation_rows = await _take_summaries("human_chat_observation", 5)

    agent_self_rows = (
        await db.execute(
            select(AgentConversationMessage)
            .where(AgentConversationMessage.role == "assistant")
            .order_by(desc(AgentConversationMessage.id))
            .limit(10)
        )
    ).scalars().all()

    callout_rows = (
        await db.execute(
            select(ChatCallout).order_by(desc(ChatCallout.id)).limit(5)
        )
    ).scalars().all()

    hook_rows = (
        await db.execute(
            select(MatchHook).order_by(desc(MatchHook.id)).limit(10)
        )
    ).scalars().all()

    return {
        "agent_chat_messages": chats_out,
        "summary_after_chat": summary_rows,
        "prebriefing": prebriefing_rows,
        "observation": observation_rows,
        "agent_self_assistant": [
            {
                "conversation_id": m.conversation_id,
                "turn": m.turn,
                "content": _trunc(m.content, 600),
            }
            for m in agent_self_rows
        ],
        "chat_callouts": [
            {
                "id": c.id,
                "session_id": c.session_id,
                "prompt": _trunc(c.callout_prompt, 200),
                "response": _trunc(c.callout_response, 600),
            }
            for c in callout_rows
        ],
        "match_hooks": [
            {
                "match_id": h.match_id,
                "target_user_id": h.target_user_id,
                "category": h.category,
                "match_type": h.match_type,
                "sensitivity_level": h.sensitivity_level,
                "hook_text": _trunc(h.hook_text, 400),
            }
            for h in hook_rows
        ],
    }


# ========================================
# 临时:Voice audit dry-run · 用当前 prompt 重跑某条 callout(整段可删)
# ========================================


@router.post("/voice-audit-rerun-callout")
async def voice_audit_rerun_callout(
    callout_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    用当前 CALLOUT_SYSTEM_TEMPLATE 重跑某条 callout 的 LLM 调用,**不写库**,
    返回 old_response + new_response 给 prompt 工程做 A/B 对比。

    用法:
      POST /api/admin/voice-audit-rerun-callout?callout_id=6
    """
    _require_admin(x_admin_secret)

    import json as _json
    from src.human_chat.callout import (
        CALLOUT_SYSTEM_TEMPLATE,
        USER_PAYLOAD_TEMPLATE,
    )
    from src.human_chat.models import ChatCallout, ChatMessage, ChatSession
    from src.llm.gateway import llm_chat
    from src.llm.types import Message
    from src.match.desensitize import _parse_loose_json
    from src.md.models import MdDocument

    callout = (
        await db.execute(
            select(ChatCallout).where(ChatCallout.id == callout_id)
        )
    ).scalar_one_or_none()
    if callout is None:
        raise HTTPException(404, detail=f"callout {callout_id} not found")

    session_row = (
        await db.execute(
            select(ChatSession).where(ChatSession.id == callout.session_id)
        )
    ).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(404, detail=f"session {callout.session_id} 已删")

    profile = (
        await db.execute(
            select(MdDocument).where(
                MdDocument.user_id == callout.host_user_id,
                MdDocument.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()

    messages = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_row.id)
            .order_by(ChatMessage.sent_at)
        )
    ).scalars().all()
    messages_data = [
        {
            "id": m.id,
            "sender": "host" if m.sender_user_id == callout.host_user_id else "peer",
            "type": m.content_type,
            "content": m.content if m.content_type == "text" else "[图片]",
            "sent_at": m.sent_at.isoformat(),
        }
        for m in messages
    ]

    prev_callouts = (
        await db.execute(
            select(ChatCallout)
            .where(
                ChatCallout.session_id == session_row.id,
                ChatCallout.host_user_id == callout.host_user_id,
                ChatCallout.id < callout.id,
            )
            .order_by(ChatCallout.created_at)
        )
    ).scalars().all()
    callouts_data = [
        {"prompt": c.callout_prompt, "response": c.callout_response}
        for c in prev_callouts
    ]

    system = CALLOUT_SYSTEM_TEMPLATE.format(
        host_md=_json.dumps(
            profile.profile_json if profile else {}, ensure_ascii=False
        ),
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        messages=_json.dumps(messages_data, ensure_ascii=False, indent=2),
        callouts=_json.dumps(callouts_data, ensure_ascii=False, indent=2),
        prompt=callout.callout_prompt,
        context_ids=callout.context_message_ids or [],
    )

    resp = await llm_chat(
        role="callout",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=1024,
        temperature=0.7,
        db=None,  # dry run · 不写 llm_call_log
    )

    parsed = _parse_loose_json(resp.text) or {}
    new_response = str(parsed.get("response_text", ""))
    new_emotional = parsed.get("emotional_read") or {}
    new_tone = new_emotional.get("tone") if isinstance(new_emotional, dict) else None

    return {
        "callout_id": callout_id,
        "host_user_id": callout.host_user_id,
        "session_id": callout.session_id,
        "callout_prompt": callout.callout_prompt,
        "old_response": callout.callout_response,
        "new_response": new_response,
        "new_tone": new_tone,
        "new_raw": parsed,
    }


# ========================================
# 临时:Voice audit dry-run · 用当前 prompt 重跑某 match 的 desensitize(整段可删)
# ========================================


@router.post("/voice-audit-rerun-desensitize")
async def voice_audit_rerun_desensitize(
    match_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    用当前 desensitize SYSTEM_PROMPT 重跑某 match_id 的 hook 生成,**不写库**,
    返回 old_hooks(DB 现存) + new_hooks(LLM 新输出)给 prompt 工程做 A/B。

    用法:
      POST /api/admin/voice-audit-rerun-desensitize?match_id=55
    """
    _require_admin(x_admin_secret)

    import json as _json
    from src.llm.gateway import llm_chat
    from src.llm.types import Message
    from src.match.desensitize import (
        SYSTEM_PROMPT as DESENSITIZE_SYSTEM,
        _extract_safe_profile_summary,
        _parse_loose_json,
    )
    from src.match.models import Match, MatchHook, Matchpoint
    from src.md.models import MdDocument

    match = (
        await db.execute(select(Match).where(Match.id == match_id))
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(404, detail=f"match {match_id} not found")

    mps = (
        await db.execute(
            select(Matchpoint).where(Matchpoint.match_id == match_id)
        )
    ).scalars().all()
    if not mps:
        raise HTTPException(404, detail=f"match {match_id} 无 matchpoints")

    profiles_rows = (
        await db.execute(
            select(MdDocument).where(
                MdDocument.user_id.in_([match.user_a_id, match.user_b_id]),
                MdDocument.is_active.is_(True),
            )
        )
    ).scalars().all()
    profile_by_user = {p.user_id: p.profile_json for p in profiles_rows}
    if (
        match.user_a_id not in profile_by_user
        or match.user_b_id not in profile_by_user
    ):
        raise HTTPException(409, detail="缺一方 active profile,跑不动")

    a_profile = _extract_safe_profile_summary(profile_by_user[match.user_a_id])
    b_profile = _extract_safe_profile_summary(profile_by_user[match.user_b_id])

    matchpoints_input = [
        {
            "idx": i,
            "category": mp.category,
            "match_type": mp.match_type,
            "similarity": float(mp.similarity),
            "weight": float(mp.weight),
            "a_source_segments": mp.a_source_segments,
            "b_source_segments": mp.b_source_segments,
        }
        for i, mp in enumerate(mps[:8])
    ]

    user_payload = _json.dumps(
        {
            "match_id": match.id,
            "is_wildcard": match.is_wildcard,
            "overall_score": float(match.overall_score),
            "user_a": {"id": match.user_a_id, "profile_summary": a_profile},
            "user_b": {"id": match.user_b_id, "profile_summary": b_profile},
            "matchpoints": matchpoints_input,
        },
        ensure_ascii=False,
    )

    resp = await llm_chat(
        role="desensitize",
        messages=[Message(role="user", content=user_payload)],
        system=DESENSITIZE_SYSTEM,
        max_tokens=2048,
        temperature=0.5,
        db=None,  # dry run · 不写 llm_call_log
    )

    parsed = _parse_loose_json(resp.text) or {}

    def _new_row(h: dict) -> dict:
        ht = h.get("hook_text") or ""
        return {
            "category": h.get("category"),
            "match_type": h.get("match_type"),
            "hook_text": ht,
            "sensitivity_level": h.get("sensitivity_level"),
            "char_count": len(ht),
        }

    new_hooks_a = [_new_row(h) for h in parsed.get("hooks_for_a", [])]
    new_hooks_b = [_new_row(h) for h in parsed.get("hooks_for_b", [])]

    old_hooks = (
        await db.execute(
            select(MatchHook).where(MatchHook.match_id == match_id)
        )
    ).scalars().all()

    def _old_row(h: MatchHook) -> dict:
        return {
            "category": h.category,
            "match_type": h.match_type,
            "hook_text": h.hook_text,
            "sensitivity_level": h.sensitivity_level,
            "char_count": len(h.hook_text or ""),
        }

    old_hooks_a = [_old_row(h) for h in old_hooks if h.target_user_id == match.user_a_id]
    old_hooks_b = [_old_row(h) for h in old_hooks if h.target_user_id == match.user_b_id]

    return {
        "match_id": match_id,
        "user_a_id": match.user_a_id,
        "user_b_id": match.user_b_id,
        "old_hooks": {"for_a": old_hooks_a, "for_b": old_hooks_b},
        "new_hooks": {"for_a": new_hooks_a, "for_b": new_hooks_b},
    }


# ========================================
# 临时:Voice audit dry-run · 用当前 prompt 重跑某 observation summary(整段可删)
# ========================================


@router.post("/voice-audit-rerun-observation")
async def voice_audit_rerun_observation(
    summary_id: int,
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    用当前 OBSERVATION_SYSTEM_TEMPLATE 重跑某 summary_id 的 observation,
    **不写库**,返回 old(DB 现存) + new(LLM 新输出) 给 prompt 工程做 A/B。

    summary 必须 summary_type='human_chat_observation'。

    用法:
      POST /api/admin/voice-audit-rerun-observation?summary_id=17
    """
    _require_admin(x_admin_secret)

    import json as _json
    from src.agent_chat.models import AgentChat
    from src.human_chat.models import ChatMessage, ChatSession
    from src.human_chat.observation import (
        OBSERVATION_SYSTEM_TEMPLATE,
        USER_PAYLOAD_TEMPLATE,
    )
    from src.llm.gateway import llm_chat
    from src.llm.types import Message
    from src.match.desensitize import _parse_loose_json
    from src.match.models import Match
    from src.md.models import MdDocument
    from src.summary.models import Summary

    summary = (
        await db.execute(select(Summary).where(Summary.id == summary_id))
    ).scalar_one_or_none()
    if summary is None:
        raise HTTPException(404, detail=f"summary {summary_id} not found")
    if summary.summary_type != "human_chat_observation":
        raise HTTPException(
            409,
            detail=f"summary {summary_id} 不是 observation(type={summary.summary_type})",
        )
    if summary.chat_session_id is None:
        raise HTTPException(409, detail=f"summary {summary_id} 缺 chat_session_id")

    session_row = (
        await db.execute(
            select(ChatSession).where(ChatSession.id == summary.chat_session_id)
        )
    ).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(404, detail="chat_session 已删")

    host_user_id = summary.host_user_id

    match = (
        await db.execute(select(Match).where(Match.id == session_row.match_id))
    ).scalar_one_or_none()
    if match is None:
        raise HTTPException(409, detail="match 缺")

    agent_chat = (
        await db.execute(
            select(AgentChat).where(AgentChat.match_id == match.id)
        )
    ).scalar_one_or_none()

    prev_summary = None
    if agent_chat is not None:
        prev_summary = (
            await db.execute(
                select(Summary).where(
                    Summary.agent_chat_id == agent_chat.id,
                    Summary.host_user_id == host_user_id,
                    Summary.summary_type == "agent_chat",
                )
            )
        ).scalar_one_or_none()

    messages = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_row.id)
            .order_by(ChatMessage.sent_at)
        )
    ).scalars().all()
    if not messages:
        raise HTTPException(409, detail="chat_session 无 messages")

    conversation = [
        {
            "id": m.id,
            "speaker": "host" if m.sender_user_id == host_user_id else "peer",
            "type": m.content_type,
            "content": m.content if m.content_type == "text" else "[图片]",
            "sent_at": m.sent_at.isoformat(),
        }
        for m in messages
    ]

    profile = (
        await db.execute(
            select(MdDocument).where(
                MdDocument.user_id == host_user_id,
                MdDocument.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()

    prev_agent_chat_data = "无之前 Agent 互聊"
    if prev_summary is not None:
        prev_agent_chat_data = _json.dumps(
            {
                "verdict": prev_summary.verdict,
                "highlights": prev_summary.highlights,
                "risks": prev_summary.risks,
                "recommended_action": prev_summary.recommended_action,
            },
            ensure_ascii=False,
        )

    system = OBSERVATION_SYSTEM_TEMPLATE.format(
        host_md=_json.dumps(
            profile.profile_json if profile else {}, ensure_ascii=False
        ),
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        host_user_id=host_user_id,
        prev_agent_chat=prev_agent_chat_data,
        end_reason=session_row.exit_action or "natural",
        conversation=_json.dumps(conversation, ensure_ascii=False, indent=2),
    )

    resp = await llm_chat(
        role="observation",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=2048,
        temperature=0.6,
        db=None,  # dry run
    )

    parsed = _parse_loose_json(resp.text) or {}

    return {
        "summary_id": summary_id,
        "host_user_id": host_user_id,
        "chat_session_id": summary.chat_session_id,
        "old": {
            "verdict": summary.verdict,
            "highlights": summary.highlights,
            "risks": summary.risks,
            "recommended_action": summary.recommended_action,
        },
        "new": {
            "verdict": parsed.get("verdict"),
            "highlights": parsed.get("highlights", []),
            "risks": parsed.get("risks", []),
            "recommended_action": parsed.get("recommended_action"),
            "compare_to_agent_chat": parsed.get("compare_to_agent_chat"),
        },
    }
