"""
Admin API · 给外部 cron 调用,需要 X-Admin-Secret 头

- POST /api/admin/observation-sweep   24h 沉默自动结束 + 观察报告
- POST /api/admin/rerun-pipeline      给某 user_id 重跑完整 pipeline(debug)

Railway Cron Jobs 配置示例(observation sweep · 每小时):
   curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" \
        https://cybermomo-production.up.railway.app/api/admin/observation-sweep
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.human_chat.models import ChatSession
from src.human_chat.observation import run_observation_for_session
from src.match.pipeline import run_full_pipeline_for_user
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


@router.post("/observation-sweep")
async def observation_sweep(
    x_admin_secret: Annotated[Optional[str], Header(alias="X-Admin-Secret")] = None,
    db: AsyncSession = Depends(get_session),
):
    """
    扫描 active 但 last_message_at > 24h 之前的 chat_sessions,
    标 ended_quit + 给双方各跑一份观察报告。

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

        # 异步跑双方观察报告(用独立 session 避免事务冲突)
        for host_uid in [session.user_a_id, session.user_b_id]:
            try:
                async with SessionLocal() as bg_db:
                    fresh_session = (await bg_db.execute(
                        select(ChatSession).where(ChatSession.id == session.id)
                    )).scalar_one_or_none()
                    if fresh_session:
                        await run_observation_for_session(
                            bg_db, session=fresh_session, host_user_id=host_uid
                        )
            except Exception as e:
                print(f"[sweep] observation failed session={session.id} host={host_uid}: {e}")

        swept.append({
            "session_id": session.id,
            "user_a_id": session.user_a_id,
            "user_b_id": session.user_b_id,
            "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
        })

    return {
        "cutoff": cutoff.isoformat(),
        "swept_count": len(swept),
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
