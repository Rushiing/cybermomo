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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.match import service as match_service
from src.match.desensitize import run_desensitize_for_match
from src.match.models import Match
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
# 再派一次:同 match 同 Agent 换话题
# ========================================

async def run_redispatch_for_summary(summary_id: int, requester_user_id: int) -> None:
    """
    用户在某条 summary 上点了"再派一次":
      1. 找到该 summary 关联的 agent_chat → match
      2. 把那场 agent_chat 标 're_dispatched'(只是标位 — 不删数据)
      3. 用 avoid_topic_refs(上一场聊过的 topic_ref 全集)启新一场 agent_chat
      4. 新 chat 跑完后生成新一对 summary

    注意:并发保护 — 如果同一 match 已经有 status='running' 的 chat,直接跳过,
    避免双方同时点"再派"撞车。
    """
    print(f"[redispatch] start summary_id={summary_id} requester={requester_user_id}")

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
            new_chat = await run_agent_chat(db, match=match, avoid_topic_refs=avoid_refs)
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
