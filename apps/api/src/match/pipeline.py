"""
匹配 → 脱敏 → Agent 互聊 → 摘要 · 完整链路 orchestrator

入口:run_full_pipeline_for_user(user_id) — 给一个用户跑整条链路。
触发时机:用户首次创建 active .md(POST /api/md 后端 BackgroundTask)。

每步用独立的 LLM 调用,失败不影响主流程(写日志,允许后续手动重试)。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.match import service as match_service
from src.match.desensitize import run_desensitize_for_match
from src.match.models import Match
from src.shared.db import SessionLocal
from src.summary.engine import run_summary_for_chat


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
            from src.agent_chat.models import AgentChat
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
