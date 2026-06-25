"""
匹配 → 脱敏 → Agent 互聊 → 摘要 · 完整链路 orchestrator

入口:
- run_full_pipeline_for_user(user_id) — 给一个用户跑整条链路(首次)。
- run_redispatch_for_summary(summary_id, requester_user_id) — 用户在简报上选"再派一次",
  同 match 同 Agent,换话题再聊一场,生成新简报。

触发时机:
- 完整链路:用户首次创建 active .md(POST /api/md 后端 BackgroundTask)。
- 再派:summary 决策 POST /api/summary/{id}/decision (decision='re_dispatch')。

每步用独立的 LLM 调用,失败不影响主流程(写日志,允许后续手动重试)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.match import service as match_service
from src.match.desensitize import run_desensitize_for_match
from src.match.models import Match, MatchHook, Matchpoint
from src.shared.db import SessionLocal
from src.summary.engine import run_summary_for_chat
from src.summary.models import Summary

# stale running chat 判定:running 但 started_at 早于这个阈值 = 部署/crash 留下的僵尸。
# 一场互聊正常 1-3 分钟,15 分钟足够覆盖最慢的正常场。
_STALE_RUNNING = timedelta(minutes=15)
# advisory lock 命名空间(防 resume 并发重复建 chat,codex P0-3)
_RESUME_LOCK_NS = 0x6342  # 'cb'


async def run_full_pipeline_for_user(user_id: int) -> None:
    """
    完整链路。每个 LLM 步骤用独立 session 隔离失败。
    跑完后:数据库里有
      - 新 matches + matchpoints
      - match_hooks(每对 match top 5 hooks × 2)
      - agent_chats + agent_chat_messages(最多 12 轮 / 对)
      - summaries(每场互聊 × 2 host)
    """
    print(f"[pipeline] start for user_id={user_id}")

    # Step 1: 匹配
    new_matches: list[Match] = []
    async with SessionLocal() as db:
        try:
            new_matches = await match_service.run_matching_for_user(db, user_id=user_id)
        except Exception as e:
            print(f"[pipeline] matching failed: {e}")
            return
    print(f"[pipeline] new matches: {len(new_matches)}")
    if not new_matches:
        return

    match_ids = [m.id for m in new_matches]

    # Step 2: 脱敏 → match_hooks(逐个跑)
    for match_id in match_ids:
        async with SessionLocal() as db:
            match = (await db.execute(
                select(Match).where(Match.id == match_id)
            )).scalar_one_or_none()
            if match is None:
                continue
            try:
                await run_desensitize_for_match(db, match=match)
            except Exception as e:
                print(f"[pipeline] desensitize failed match_id={match_id}: {e}")

    # Step 3: Agent 互聊
    chat_ids: list[int] = []
    for match_id in match_ids:
        async with SessionLocal() as db:
            match = (await db.execute(
                select(Match).where(Match.id == match_id)
            )).scalar_one_or_none()
            if match is None:
                continue
            try:
                chat = await run_agent_chat(db, match=match)
                chat_ids.append(chat.id)
                # 同步标 match status
                match.status = "agent_chat_done" if "done" in (chat.status or "") else "agent_chat_running"
                await db.commit()
            except Exception as e:
                print(f"[pipeline] agent_chat failed match_id={match_id}: {e}")

    # Step 4: 摘要(每场互聊 → 双方各一份 summary)
    for chat_id in chat_ids:
        async with SessionLocal() as db:
            chat = (await db.execute(
                select(AgentChat).where(AgentChat.id == chat_id)
            )).scalar_one_or_none()
            if chat is None:
                continue
            try:
                await run_summary_for_chat(db, chat=chat)
            except Exception as e:
                print(f"[pipeline] summary failed chat_id={chat_id}: {e}")

    print(f"[pipeline] done for user_id={user_id}: {len(new_matches)} matches, {len(chat_ids)} chats")


# ========================================
# 续跑半成品 pipeline(audit P0-4 / codex stab-P0-1)
# ========================================
#
# 问题:run_full_pipeline_for_user 以 run_matching 起步,只建"新 match";部署中断/
# LLM 失败后,已建 match 但缺 hook/chat/summary 的用户,重跑会被 _existing_match_partners
# 过滤成 new_matches=[] → 直接 return,"重跑接着干"不成立。
#
# 本函数按 **stage** 补:扫该 user 全部 match,缺哪步补哪步,不依赖"新 match"。
# 幂等:每步前查产物;summary 按 host 幂等;running zombie 有 stale 判定;
# 并发用 pg advisory lock 防重复建 chat(codex 终审 P0-1/2/3 已处理)。


def _is_stale_running(chat: AgentChat, now: datetime) -> bool:
    """running 但 started_at 早于阈值 = 部署/crash 留下的僵尸(codex P0-2)"""
    if chat.status != "running":
        return False
    started = chat.started_at
    if started is None:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return started < now - _STALE_RUNNING


async def _chat_msg_count(db: AsyncSession, chat_id: int) -> int:
    return (await db.execute(
        select(func.count()).select_from(AgentChatMessage)
        .where(AgentChatMessage.agent_chat_id == chat_id)
    )).scalar_one()


async def _summary_hosts(db: AsyncSession, chat_id: int) -> set[int]:
    return set((await db.execute(
        select(Summary.host_user_id).where(Summary.agent_chat_id == chat_id)
    )).scalars().all())


async def resume_incomplete_pipeline_for_user(user_id: int) -> dict:
    """
    扫某 user 的所有 match,补齐缺失的 desensitize / agent_chat / summary。
    返回报告 dict。不抛(单步失败记 error 继续)。
    """
    report: dict = {
        "user_id": user_id,
        "matches": 0,
        "desensitize_run": 0,
        "agent_chat_run": 0,
        "summary_run": 0,
        "stale_terminated": 0,
        "skipped_running": 0,
        "errors": [],
    }
    now = datetime.now(timezone.utc)

    async with SessionLocal() as db:
        matches = (await db.execute(
            select(Match).where(
                or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
            )
        )).scalars().all()
        match_ids = [(m.id, m.user_a_id, m.user_b_id) for m in matches]
    report["matches"] = len(match_ids)
    if not match_ids:
        return report

    for match_id, ua, ub in match_ids:
        # --- Stage 0: stale running zombie → 标 done_terminated(codex P0-2)---
        # 部署/crash 把 chat 留在 running,resume 否则会永远跳过它。stale 的标掉,
        # 下面 Stage B 才能(若它没真聊过)重开一场。
        try:
            async with SessionLocal() as db:
                stale = (await db.execute(
                    select(AgentChat).where(
                        AgentChat.match_id == match_id,
                        AgentChat.status == "running",
                    )
                )).scalars().all()
                for c in stale:
                    if _is_stale_running(c, now):
                        c.status = "done_terminated"
                        c.end_reason = "stale_abandoned"
                        c.ended_at = now
                        report["stale_terminated"] += 1
                await db.commit()
        except Exception as e:
            report["errors"].append({"stage": "stale", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

        # --- Stage A: 缺 hook 且有 matchpoint → 补 desensitize ---
        try:
            async with SessionLocal() as db:
                hook_n = (await db.execute(
                    select(func.count()).select_from(MatchHook)
                    .where(MatchHook.match_id == match_id)
                )).scalar_one()
                mp_n = (await db.execute(
                    select(func.count()).select_from(Matchpoint)
                    .where(Matchpoint.match_id == match_id)
                )).scalar_one()
                if hook_n == 0 and mp_n > 0:
                    match = (await db.execute(
                        select(Match).where(Match.id == match_id)
                    )).scalar_one_or_none()
                    if match is not None:
                        await run_desensitize_for_match(db, match=match)
                        report["desensitize_run"] += 1
        except Exception as e:
            report["errors"].append({"stage": "desensitize", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

        # --- Stage B: 有 hook、无"真 done chat"、无活跃 running → 补 agent_chat ---
        # "真 done chat" = done 且有 ≥1 条消息(stale 标掉的空僵尸不算,要重开)。
        # advisory lock 防并发(两个 repair / repair vs 正常 pipeline)重复建 chat(P0-3)。
        try:
            async with SessionLocal() as db:
                # session 级 advisory lock(跨内部 commit 持有,直到本 session 结束)
                await db.execute(text("SELECT pg_advisory_lock(:ns, :k)")
                                 .bindparams(ns=_RESUME_LOCK_NS, k=match_id))
                try:
                    hook_n = (await db.execute(
                        select(func.count()).select_from(MatchHook)
                        .where(MatchHook.match_id == match_id)
                    )).scalar_one()
                    chats = (await db.execute(
                        select(AgentChat).where(AgentChat.match_id == match_id)
                    )).scalars().all()
                    has_active_running = any(
                        c.status == "running" and not _is_stale_running(c, now)
                        for c in chats
                    )
                    has_real_done = False
                    for c in chats:
                        if "done" in (c.status or "") and c.end_reason != "stale_abandoned":
                            if await _chat_msg_count(db, c.id) > 0:
                                has_real_done = True
                                break
                    if hook_n > 0 and not has_real_done and not has_active_running:
                        match = (await db.execute(
                            select(Match).where(Match.id == match_id)
                        )).scalar_one_or_none()
                        if match is not None:
                            chat = await run_agent_chat(db, match=match)
                            match.status = ("agent_chat_done"
                                            if "done" in (chat.status or "")
                                            else "agent_chat_running")
                            await db.commit()
                            report["agent_chat_run"] += 1
                    elif has_active_running:
                        report["skipped_running"] += 1
                finally:
                    await db.execute(text("SELECT pg_advisory_unlock(:ns, :k)")
                                     .bindparams(ns=_RESUME_LOCK_NS, k=match_id))
        except Exception as e:
            report["errors"].append({"stage": "agent_chat", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

        # --- Stage C: 真 done chat 缺某侧 host summary → 补(per-host,codex P0-1)---
        try:
            async with SessionLocal() as db:
                done_chats = (await db.execute(
                    select(AgentChat).where(
                        AgentChat.match_id == match_id,
                        AgentChat.status.in_(["done_natural", "done_terminated"]),
                    )
                )).scalars().all()
                for chat in done_chats:
                    if await _chat_msg_count(db, chat.id) == 0:
                        continue  # 空僵尸不产简报
                    have = await _summary_hosts(db, chat.id)
                    if {ua, ub} - have:  # 有 host 缺简报
                        # run_summary_for_chat 已 per-host 幂等,只补缺的一侧
                        await run_summary_for_chat(db, chat=chat)
                        report["summary_run"] += 1
        except Exception as e:
            report["errors"].append({"stage": "summary", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

    print(f"[pipeline-resume] user={user_id}: {report}")
    return report


async def find_users_with_incomplete_pipeline() -> list[int]:
    """
    只读:找"有 match 但缺简报"的 user_id 列表(诊断 + repair-all 用)。

    一个 match 算"完整"当且仅当:有一场 done chat、它有 ≥1 条消息、且双方 host
    都有 summary(codex P0-1:单侧 summary 不算完整)。否则两个 user 都标未完成。
    没 matchpoint 的 match 本就不产物,跳过。
    """
    incomplete_users: set[int] = set()
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        matches = (await db.execute(select(Match))).scalars().all()
        for m in matches:
            mp_n = (await db.execute(
                select(func.count()).select_from(Matchpoint)
                .where(Matchpoint.match_id == m.id)
            )).scalar_one()
            if mp_n == 0:
                continue
            done_chats = (await db.execute(
                select(AgentChat).where(
                    AgentChat.match_id == m.id,
                    AgentChat.status.in_(["done_natural", "done_terminated"]),
                )
            )).scalars().all()
            complete = False
            for c in done_chats:
                if c.end_reason == "stale_abandoned":
                    continue
                if await _chat_msg_count(db, c.id) == 0:
                    continue
                have = await _summary_hosts(db, c.id)
                if not ({m.user_a_id, m.user_b_id} - have):  # 双方都有简报
                    complete = True
                    break
            if not complete:
                incomplete_users.add(m.user_a_id)
                incomplete_users.add(m.user_b_id)
    return sorted(incomplete_users)


# ========================================
# 再派一次:同 match 同 Agent 换话题
# ========================================

async def run_redispatch_for_summary(
    summary_id: int,
    requester_user_id: int,
    direction_hint: str | None = None,
) -> None:
    """
    用户在某条 summary 上点了"再派一次":
      1. 找到该 summary 关联的 agent_chat → match
      2. 把那场 agent_chat 标 're_dispatched'(只是标位 — 不删数据)
      3. 用 avoid_topic_refs(上一场聊过的 topic_ref 全集)启新一场 agent_chat
      4. 新 chat 跑完后生成新一对 summary

    direction_hint:宿主在「跟我 Agent 聊聊」对话里沉淀的方向(短文本),
    会注入 host 这一侧 Agent 的 system prompt — "本次互聊请尤其往这个方向探"。

    注意:并发保护 — 如果同一 match 已经有 status='running' 的 chat,直接跳过,
    避免双方同时点"再派"撞车。
    """
    print(
        f"[redispatch] start summary_id={summary_id} requester={requester_user_id} "
        f"direction={'<set>' if direction_hint else 'none'}"
    )

    # Step 1: 拉 summary + chat + match,采集 avoid_topic_refs
    avoid_refs: list[str] = []
    match_id: int | None = None
    old_chat_id: int | None = None

    async with SessionLocal() as db:
        summary = (await db.execute(
            select(Summary).where(Summary.id == summary_id)
        )).scalar_one_or_none()
        if summary is None or summary.agent_chat_id is None:
            print(f"[redispatch] summary or agent_chat missing, abort")
            return

        old_chat = (await db.execute(
            select(AgentChat).where(AgentChat.id == summary.agent_chat_id)
        )).scalar_one_or_none()
        if old_chat is None:
            print(f"[redispatch] old chat missing, abort")
            return

        match_id = old_chat.match_id
        old_chat_id = old_chat.id

        # 并发保护:同 match 还有 running 的 chat?
        running = (await db.execute(
            select(AgentChat).where(
                AgentChat.match_id == match_id,
                AgentChat.status == "running",
            )
        )).scalars().all()
        if running:
            print(f"[redispatch] match {match_id} already has running chat — skip")
            return

        # 收集旧 chat 出现的 topic_ref(去重)
        old_msgs = (await db.execute(
            select(AgentChatMessage).where(AgentChatMessage.agent_chat_id == old_chat_id)
        )).scalars().all()
        avoid_refs = list({m.topic_ref for m in old_msgs if m.topic_ref})

        # 标旧 chat 为 re_dispatched(归档但不删)
        if old_chat.status not in ("running",):
            old_chat.status = "re_dispatched"
            await db.commit()

    if match_id is None:
        return

    # Step 2: 跑新 agent_chat
    new_chat_id: int | None = None
    async with SessionLocal() as db:
        match = (await db.execute(
            select(Match).where(Match.id == match_id)
        )).scalar_one_or_none()
        if match is None:
            print(f"[redispatch] match {match_id} disappeared, abort")
            return
        try:
            new_chat = await run_agent_chat(
                db,
                match=match,
                avoid_topic_refs=avoid_refs,
                direction_hint=direction_hint,
                direction_target_user_id=requester_user_id,
            )
            new_chat_id = new_chat.id
            match.status = "agent_chat_done" if "done" in (new_chat.status or "") else "agent_chat_running"
            await db.commit()
        except Exception as e:
            print(f"[redispatch] agent_chat failed match_id={match_id}: {e}")
            return

    if new_chat_id is None:
        return

    # Step 3: 生成新 summary
    async with SessionLocal() as db:
        chat = (await db.execute(
            select(AgentChat).where(AgentChat.id == new_chat_id)
        )).scalar_one_or_none()
        if chat is None:
            return
        try:
            await run_summary_for_chat(db, chat=chat)
        except Exception as e:
            print(f"[redispatch] summary failed chat_id={new_chat_id}: {e}")

    print(f"[redispatch] done summary_id={summary_id} → new chat_id={new_chat_id}")
