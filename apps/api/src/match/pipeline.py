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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.match import service as match_service
from src.match.desensitize import run_desensitize_for_match
from src.match.models import Match, MatchHook, Matchpoint
from src.shared.db import SessionLocal
from src.summary.engine import run_summary_for_chat
from src.summary.models import Summary


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
# 幂等:每步前先查是否已有产物,有就跳过。

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
        "skipped_running": 0,
        "errors": [],
    }

    # 1) 拉该 user 所有 match
    async with SessionLocal() as db:
        matches = (await db.execute(
            select(Match).where(
                or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
            )
        )).scalars().all()
        match_ids = [m.id for m in matches]
    report["matches"] = len(match_ids)
    if not match_ids:
        return report

    for match_id in match_ids:
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

        # --- Stage B: 有 hook、无 done chat、无 running chat → 补 agent_chat ---
        try:
            async with SessionLocal() as db:
                hook_n = (await db.execute(
                    select(func.count()).select_from(MatchHook)
                    .where(MatchHook.match_id == match_id)
                )).scalar_one()
                chats = (await db.execute(
                    select(AgentChat).where(AgentChat.match_id == match_id)
                )).scalars().all()
                has_done = any("done" in (c.status or "") for c in chats)
                has_running = any(c.status == "running" for c in chats)
                if hook_n > 0 and not has_done and not has_running:
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
                elif has_running:
                    report["skipped_running"] += 1
        except Exception as e:
            report["errors"].append({"stage": "agent_chat", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

        # --- Stage C: done chat 无 summary → 补 summary ---
        try:
            async with SessionLocal() as db:
                done_chats = (await db.execute(
                    select(AgentChat).where(
                        AgentChat.match_id == match_id,
                        AgentChat.status.in_(["done_natural", "done_terminated"]),
                    )
                )).scalars().all()
                for chat in done_chats:
                    sum_n = (await db.execute(
                        select(func.count()).select_from(Summary)
                        .where(Summary.agent_chat_id == chat.id)
                    )).scalar_one()
                    if sum_n == 0:
                        await run_summary_for_chat(db, chat=chat)
                        report["summary_run"] += 1
        except Exception as e:
            report["errors"].append({"stage": "summary", "match_id": match_id,
                                     "error": f"{type(e).__name__}: {e}"})

    print(f"[pipeline-resume] user={user_id}: {report}")
    return report


async def find_users_with_incomplete_pipeline() -> list[int]:
    """
    只读:找"有 match 但有 match 缺 summary"的 user_id 列表(诊断 + repair-all 用)。
    判定:某 match 双方应各有 summary;只要该 match 关联的 done chat 有 0 summary,
    或 match 有 hook 却没 done chat,就算未完成。简化版:扫所有 match,任一未达
    "有 done chat 且该 chat 有 summary",其涉及的两个 user 都标未完成。
    """
    incomplete_users: set[int] = set()
    async with SessionLocal() as db:
        matches = (await db.execute(select(Match))).scalars().all()
        for m in matches:
            mp_n = (await db.execute(
                select(func.count()).select_from(Matchpoint)
                .where(Matchpoint.match_id == m.id)
            )).scalar_one()
            if mp_n == 0:
                continue  # 没 matchpoint 的 match 本就不产 hook/chat/summary,跳过
            # 有 done chat 且其有 summary?
            done_chats = (await db.execute(
                select(AgentChat.id).where(
                    AgentChat.match_id == m.id,
                    AgentChat.status.in_(["done_natural", "done_terminated"]),
                )
            )).scalars().all()
            complete = False
            if done_chats:
                sum_n = (await db.execute(
                    select(func.count()).select_from(Summary)
                    .where(Summary.agent_chat_id.in_(done_chats))
                )).scalar_one()
                complete = sum_n > 0
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
