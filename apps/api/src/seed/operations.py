"""
冷启动 seed 业务操作 · 给 HTTP endpoint + CLI 共用

设计原则:
- 函数不打印日志(用 logger),不退出进程 — 返回 dict 给调用方决定怎么呈现
- DB 用现有 SessionLocal,不新建 engine
- LLM pipeline 调用复用 src.match.pipeline.run_full_pipeline_for_user
- 全部幂等:按 username / is_system_mock 查重,重跑安全

mock 用户标记:`User.is_system_mock=True`,跟真人池在管理面板可分离统计。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, or_, select

from src.agent_chat.models import AgentChat
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.match.models import Match
from src.match.pipeline import run_full_pipeline_for_user
from src.md.models import MdDocument
from src.seed.archetypes import MOCK_USERS, build_profile_for
from src.shared.db import SessionLocal
from src.summary.engine import run_summary_for_chat
from src.summary.models import Summary


# ========================================
# Pipeline job state(进程级 in-memory · admin endpoint 用)
# ========================================
#
# Railway 重启会丢这个状态,但 pipeline 本身是幂等的,重跑会自动接着干没跑完的。
# MVP 阶段先不持久化 job state(够用),后续如果要 multi-replica 再 push 到 DB。

_PIPELINE_JOB: dict[str, Any] = {
    "status": "idle",  # idle | running | done | failed
    "started_at": None,
    "finished_at": None,
    "target_user_count": 0,
    "processed_user_count": 0,
    "current_user_id": None,
    "errors": [],  # list of {"user_id": int, "error": str}
}


def _reset_job_state(target_count: int) -> None:
    _PIPELINE_JOB.update(
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        target_user_count=target_count,
        processed_user_count=0,
        current_user_id=None,
        errors=[],
    )


def get_pipeline_job_state() -> dict[str, Any]:
    """返回当前 job 状态的浅拷贝(给 endpoint 序列化用)"""
    return dict(_PIPELINE_JOB)


def is_pipeline_running() -> bool:
    return _PIPELINE_JOB["status"] == "running"


# ========================================
# 插入用户(幂等 + 同步)
# ========================================

DEFAULT_MOCK_PASSWORD = "mock_seed_2026"


async def upsert_one_mock_user(
    spec: dict[str, Any], *, password: str = DEFAULT_MOCK_PASSWORD
) -> tuple[int, bool]:
    """
    按 username 查重:
    - 已存在 → (existing_user_id, False)
    - 新插 → (new_user_id, True),同时创建 UserProfile + MdDocument
    """
    async with SessionLocal() as db:
        existing = (await db.execute(
            select(User).where(User.username == spec["username"])
        )).scalar_one_or_none()
        if existing is not None:
            return existing.id, False

        user = User(
            username=spec["username"],
            password_hash=hash_password(password),
            email=None,
            google_sub=None,
            is_adult_confirmed=True,
            is_system_mock=True,
            onboarded_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        user_id = user.id

        db.add(UserProfile(
            user_id=user_id,
            nickname=spec["nickname"],
            age_band=spec["age_band"],
            gender=spec["gender"],
            mbti=spec["mbti"],
        ))

        full_profile = build_profile_for(spec)
        db.add(MdDocument(
            user_id=user_id,
            version=1,
            profile_json=full_profile,
            profile_version=full_profile["meta"]["version"],
            portrait_body="\n\n".join(full_profile["portrait"]["body"]),
            domains_interested=full_profile["domains"]["interested"],
            domains_avoided=full_profile["domains"]["avoided"],
            raw_answers=full_profile["raw_answers"],
            is_active=True,
        ))

        await db.commit()
        return user_id, True


async def insert_all_mock_users(
    *, password: str = DEFAULT_MOCK_PASSWORD
) -> dict[str, Any]:
    """
    把 MOCK_USERS 全部 upsert 进库,返回结构化结果:
      {
        "total": 20,
        "newly_created": int,
        "already_exists": int,
        "users": [{"user_id": int, "username": str, "nickname": str, "was_new": bool}],
      }
    """
    users: list[dict[str, Any]] = []
    new_count = 0
    for spec in MOCK_USERS:
        uid, was_new = await upsert_one_mock_user(spec, password=password)
        if was_new:
            new_count += 1
        users.append({
            "user_id": uid,
            "username": spec["username"],
            "nickname": spec["nickname"],
            "was_new": was_new,
        })
    return {
        "total": len(MOCK_USERS),
        "newly_created": new_count,
        "already_exists": len(MOCK_USERS) - new_count,
        "users": users,
    }


_CLEAN_NICKNAME_POOL = [
    "南序", "青岑", "知野", "林止", "澄川", "一禾", "若庭", "云屏", "松弦", "白栖",
    "岑夏", "临溪", "明砚", "北禾", "予安", "闻舟", "照晚", "宁川", "如栖", "山月",
    "川柏", "素笺", "予乔", "晴山", "时屿", "映河", "远白", "清岚", "念初", "微澜",
]


def _obvious_mock_nickname(nickname: str | None) -> bool:
    text = (nickname or "").strip()
    lowered = text.lower()
    return (
        "mock" in lowered
        or "test" in lowered
        or "测试" in text
        or lowered.startswith("user_")
    )


async def cleanup_obvious_mock_nicknames(*, dry_run: bool = True) -> dict[str, Any]:
    """把明显带 mock/test/测试/user_ 的展示昵称换成自然昵称。"""
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(User, UserProfile)
            .join(UserProfile, UserProfile.user_id == User.id)
            .order_by(User.id)
        )).all()

        existing_nicknames = {
            str(profile.nickname).strip()
            for _, profile in rows
            if profile.nickname and not _obvious_mock_nickname(profile.nickname)
        }
        pool_iter = iter([n for n in _CLEAN_NICKNAME_POOL if n not in existing_nicknames])
        changes: list[dict[str, Any]] = []

        for user, profile in rows:
            if not _obvious_mock_nickname(profile.nickname):
                continue
            try:
                new_nickname = next(pool_iter)
            except StopIteration:
                new_nickname = f"临山{len(changes) + 1}"
            changes.append({
                "user_id": user.id,
                "username": user.username,
                "is_system_mock": user.is_system_mock,
                "old_nickname": profile.nickname,
                "new_nickname": new_nickname,
            })
            if not dry_run:
                profile.nickname = new_nickname

        if not dry_run:
            await db.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "changed_count": len(changes),
        "changes": changes,
    }


# ========================================
# Pipeline 跑(异步 · BackgroundTask 调用)
# ========================================

async def _list_mock_user_ids(limit: Optional[int]) -> list[int]:
    async with SessionLocal() as db:
        stmt = (
            select(User.id)
            .where(User.is_system_mock.is_(True))
            .order_by(User.id)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def run_pipeline_for_all_mock_users(
    *, user_limit: Optional[int] = None
) -> None:
    """
    串行跑 pipeline。**这个函数被 BackgroundTask 调用,不抛 — 错误进 _PIPELINE_JOB.errors**。

    完成或失败后会更新 _PIPELINE_JOB.status。重复调用前应检查 is_pipeline_running()。
    """
    try:
        target_ids = await _list_mock_user_ids(user_limit)
    except Exception as e:
        _PIPELINE_JOB.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            errors=[{"user_id": None, "error": f"list_mock_users: {type(e).__name__}: {e}"}],
        )
        return

    _reset_job_state(len(target_ids))

    for uid in target_ids:
        _PIPELINE_JOB["current_user_id"] = uid
        try:
            await run_full_pipeline_for_user(uid)
        except Exception as e:
            _PIPELINE_JOB["errors"].append({
                "user_id": uid,
                "error": f"{type(e).__name__}: {e}",
            })
            # 单 user 失败不阻塞,继续下一个
        finally:
            _PIPELINE_JOB["processed_user_count"] += 1
            _PIPELINE_JOB["current_user_id"] = None

    _PIPELINE_JOB.update(
        status="done" if not _PIPELINE_JOB["errors"] else "failed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


# ========================================
# Redo summaries(prompt 校准后只重跑 summary,不重跑 agent_chat)
# ========================================
#
# 用途:调 SUMMARY_SYSTEM_TEMPLATE 后,在同一批 mock 对话 utterance 上重新评估
# verdict,直接对比新旧 prompt 效果(不用重跑 30 分钟的 agent_chat)。
#
# 行为:
#   1. 找出所有涉及 mock 用户的 AgentChat(status=done_natural)
#   2. 删除这些 chat 关联的旧 Summary
#   3. 用当前 SUMMARY_SYSTEM_TEMPLATE 重新生成 summary
#
# 不动 AgentChat / AgentChatMessage — 这些是真实发生过的对话历史,保留不变。

_REDO_SUMMARIES_JOB: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "target_chat_count": 0,
    "processed_chat_count": 0,
    "current_chat_id": None,
    "summaries_created": 0,
    "errors": [],
}


def _reset_redo_state(target_count: int) -> None:
    _REDO_SUMMARIES_JOB.update(
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        target_chat_count=target_count,
        processed_chat_count=0,
        current_chat_id=None,
        summaries_created=0,
        errors=[],
    )


def get_redo_summaries_job_state() -> dict[str, Any]:
    return dict(_REDO_SUMMARIES_JOB)


def is_redo_summaries_running() -> bool:
    return _REDO_SUMMARIES_JOB["status"] == "running"


async def redo_summaries_for_mock_pool() -> None:
    """重跑所有 mock 涉及 chat 的 summary。BackgroundTask 调用,不抛。"""
    try:
        async with SessionLocal() as db:
            stmt = (
                select(AgentChat.id)
                .join(Match, AgentChat.match_id == Match.id)
                .where(_mock_chat_filter(), AgentChat.status == "done_natural")
                .order_by(AgentChat.id)
            )
            chat_ids = list((await db.execute(stmt)).scalars().all())
    except Exception as e:
        _REDO_SUMMARIES_JOB.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            errors=[{"chat_id": None, "error": f"list_chats: {type(e).__name__}: {e}"}],
        )
        return

    _reset_redo_state(len(chat_ids))

    for chat_id in chat_ids:
        _REDO_SUMMARIES_JOB["current_chat_id"] = chat_id
        try:
            async with SessionLocal() as db:
                # 1) 删旧 summary(only mock-pool 的,不动真人数据)
                await db.execute(
                    delete(Summary).where(Summary.agent_chat_id == chat_id)
                )
                await db.commit()

                # 2) 拉 chat
                chat = (await db.execute(
                    select(AgentChat).where(AgentChat.id == chat_id)
                )).scalar_one_or_none()
                if chat is None:
                    continue

                # 3) 用当前 prompt 重跑 summary
                new_summaries = await run_summary_for_chat(db, chat=chat)
                _REDO_SUMMARIES_JOB["summaries_created"] += len(new_summaries)
        except Exception as e:
            _REDO_SUMMARIES_JOB["errors"].append({
                "chat_id": chat_id,
                "error": f"{type(e).__name__}: {e}",
            })
        finally:
            _REDO_SUMMARIES_JOB["processed_chat_count"] += 1
            _REDO_SUMMARIES_JOB["current_chat_id"] = None

    _REDO_SUMMARIES_JOB.update(
        status="done" if not _REDO_SUMMARIES_JOB["errors"] else "failed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


# ========================================
# Verification(只读)
# ========================================

async def _count_rows(stmt) -> int:
    async with SessionLocal() as db:
        return int((await db.execute(stmt)).scalar_one() or 0)


async def _group_counts(stmt) -> dict[str, int]:
    async with SessionLocal() as db:
        rows = (await db.execute(stmt)).all()
    return {str(k): int(v or 0) for k, v in rows}


def _mock_chat_filter():
    """Match.user_a 或 user_b 是 mock 用户"""
    mock_ids = select(User.id).where(User.is_system_mock.is_(True))
    return or_(
        Match.user_a_id.in_(mock_ids),
        Match.user_b_id.in_(mock_ids),
    )


ARCHETYPE_LETTERS = ("A", "B", "C", "D", "E", "F", "G", "H")
TARGET_VERDICT_RATIOS = {
    "来电": 0.30,
    "有点意思再观察": 0.50,
    "不合": 0.20,
}
VERDICT_TOLERANCE = 0.10


async def verify_mock_pool() -> dict[str, Any]:
    """返回 mock pool 摘要 · 用户数 + archetype 分布 + gender / age 分布"""
    mock_count = await _count_rows(
        select(func.count()).select_from(User).where(User.is_system_mock.is_(True))
    )

    archetype_counts: dict[str, int] = {}
    for letter in ARCHETYPE_LETTERS:
        count = await _count_rows(
            select(func.count())
            .select_from(User)
            .where(
                User.is_system_mock.is_(True),
                User.username.like(f"mock\\_%\\_{letter.lower()}%", escape="\\"),
            )
        )
        archetype_counts[letter] = count

    gender_counts = await _group_counts(
        select(UserProfile.gender, func.count())
        .join(User, UserProfile.user_id == User.id)
        .where(User.is_system_mock.is_(True))
        .group_by(UserProfile.gender)
        .order_by(UserProfile.gender)
    )

    age_counts = await _group_counts(
        select(UserProfile.age_band, func.count())
        .join(User, UserProfile.user_id == User.id)
        .where(User.is_system_mock.is_(True))
        .group_by(UserProfile.age_band)
        .order_by(UserProfile.age_band)
    )

    return {
        "mock_count": mock_count,
        "by_archetype": archetype_counts,
        "by_gender": gender_counts,
        "by_age_band": age_counts,
    }


async def verify_agent_chats() -> dict[str, Any]:
    """返回 agent_chat 涉及 mock 用户的总数 + status + end_reason 分布"""
    total = await _count_rows(
        select(func.count())
        .select_from(AgentChat)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
    )

    status_counts = await _group_counts(
        select(AgentChat.status, func.count())
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
        .group_by(AgentChat.status)
        .order_by(AgentChat.status)
    )

    end_reason_counts = await _group_counts(
        select(AgentChat.end_reason, func.count())
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter(), AgentChat.end_reason.is_not(None))
        .group_by(AgentChat.end_reason)
        .order_by(func.count().desc(), AgentChat.end_reason)
    )

    return {
        "total": total,
        "by_status": status_counts,
        "by_end_reason": end_reason_counts,
    }


async def verify_summaries() -> dict[str, Any]:
    """返回 summary 涉及 mock 用户的总数 + verdict 分布 + 偏离 target 多少"""
    total = await _count_rows(
        select(func.count())
        .select_from(Summary)
        .join(AgentChat, Summary.agent_chat_id == AgentChat.id)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
    )

    verdict_counts = await _group_counts(
        select(Summary.verdict, func.count())
        .join(AgentChat, Summary.agent_chat_id == AgentChat.id)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
        .group_by(Summary.verdict)
        .order_by(Summary.verdict)
    )

    distribution = []
    for verdict, target in TARGET_VERDICT_RATIOS.items():
        count = verdict_counts.get(verdict, 0)
        actual = count / total if total else 0.0
        distribution.append({
            "verdict": verdict,
            "count": count,
            "actual_ratio": round(actual, 3),
            "target_ratio": target,
            "within_tolerance": abs(actual - target) <= VERDICT_TOLERANCE,
        })

    # 三档以外的 verdict(数据异常)
    extra = {
        v: c for v, c in verdict_counts.items()
        if v not in TARGET_VERDICT_RATIOS
    }

    return {
        "total": total,
        "distribution": distribution,
        "extra_verdicts": extra,
    }


async def verify_all() -> dict[str, Any]:
    """一次跑完三项校验,聚合返回 + 给 health 总结"""
    pool, chats, summaries = await asyncio.gather(
        verify_mock_pool(),
        verify_agent_chats(),
        verify_summaries(),
    )

    health_warnings: list[str] = []
    if pool["mock_count"] != len(MOCK_USERS):
        health_warnings.append(
            f"mock_count mismatch: expected {len(MOCK_USERS)}, got {pool['mock_count']}"
        )
    running_chats = chats["by_status"].get("running", 0)
    if running_chats > 0:
        health_warnings.append(f"{running_chats} chats still running (可能上次中断了)")
    for entry in summaries["distribution"]:
        if not entry["within_tolerance"]:
            health_warnings.append(
                f"verdict {entry['verdict']} outside tolerance: "
                f"{entry['actual_ratio']:.0%} vs target {entry['target_ratio']:.0%}"
            )

    return {
        "pool": pool,
        "agent_chats": chats,
        "summaries": summaries,
        "health_warnings": health_warnings,
        "ok": len(health_warnings) == 0,
    }
