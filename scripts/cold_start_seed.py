#!/usr/bin/env python3
"""
冷启动种子脚本 · 把 mock_user_archetypes 里的 20 人灌进 DB,然后串行触发
match → desensitize → agent_chat → summary 的全链路。

用法(本地连 Railway DB):
    cd apps/api
    DATABASE_URL=postgresql+asyncpg://... \
    PYTHONPATH=. \
    python3 ../../scripts/cold_start_seed.py

可选环境变量:
    DRY_RUN=1           — 只打印不写库
    SKIP_PIPELINE=1     — 只插用户,不跑 agent_chat
    PIPELINE_USER_LIMIT=8  — 跑 pipeline 的用户数上限(默认全部 20)
                            8 人 × top_k=5 ≈ 30-40 pair(plan 目标)

幂等:
    脚本启动时按 username 查重,已存在的 mock user 跳过插入,直接进 pipeline 阶段。
    run_full_pipeline_for_user 内部又会 dedupe 已 match 过的 pair,所以重跑安全。

前置:
    必须先跑通 Task 3 的密码注册 migration(20260513_add_password_auth) — 否则
    users 表没有 username / password_hash / is_system_mock 列。

执行预期:
    20 人插库 ~10s,pipeline 全跑约 15-30 分钟(主要在 LLM 调用)。
    期间 DashScope quota 要监控(单场 agent_chat ~8 轮 + 双方 summary,
    单 pair 约 30 个 LLM call)。
"""
from __future__ import annotations

import asyncio
import argparse
import os
import sys
import time
from pathlib import Path

# 允许从仓库根目录直接跑,自动把 apps/api 加进 sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
# 同时让 scripts/ 可以 import mock_user_archetypes
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import func, or_, select  # noqa: E402

from src.agent_chat.models import AgentChat  # noqa: E402
from src.auth.models import User, UserProfile  # noqa: E402
from src.auth.password import hash_password  # noqa: E402
from src.match.models import Match  # noqa: E402
from src.match.pipeline import run_full_pipeline_for_user  # noqa: E402
from src.md.models import MdDocument  # noqa: E402
from src.shared.db import SessionLocal, engine  # noqa: E402
from src.summary.models import Summary  # noqa: E402

from mock_user_archetypes import MOCK_USERS, build_profile_for  # noqa: E402


DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
SKIP_PIPELINE = os.environ.get("SKIP_PIPELINE", "0") == "1"
PIPELINE_USER_LIMIT = int(os.environ.get("PIPELINE_USER_LIMIT", str(len(MOCK_USERS))))
DEFAULT_PASSWORD = os.environ.get("MOCK_PASSWORD", "mock_seed_2026")
ARCHETYPE_LETTERS = ("A", "B", "C", "D", "E", "F", "G", "H")
TARGET_VERDICT_RATIOS = {
    "来电": 0.30,
    "有点意思再观察": 0.50,
    "不合": 0.20,
}
VERDICT_TOLERANCE = 0.10


def _pct(n: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(n / total * 100):.0f}%"


def _format_kv_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"{k}={v}" for k, v in counts.items())


# ========================================
# 插入用户(idempotent)
# ========================================

async def upsert_user(spec: dict) -> tuple[int, bool]:
    """
    根据 username 查重:存在则返回 (user_id, False=already_exists);
    否则插 user + profile + md_document,返回 (user_id, True=newly_created)
    """
    async with SessionLocal() as db:
        existing = (await db.execute(
            select(User).where(User.username == spec["username"])
        )).scalar_one_or_none()
        if existing is not None:
            return existing.id, False

        if DRY_RUN:
            print(f"  [DRY_RUN] would insert {spec['username']} ({spec['nickname']})")
            return -1, True

        # 1) users 行(密码路径,google_sub=NULL,is_system_mock=True)
        user = User(
            username=spec["username"],
            password_hash=hash_password(DEFAULT_PASSWORD),
            email=None,
            google_sub=None,
            is_adult_confirmed=True,
            is_system_mock=True,
            onboarded_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        user_id = user.id

        # 2) user_profiles 行
        profile = UserProfile(
            user_id=user_id,
            nickname=spec["nickname"],
            age_band=spec["age_band"],
            gender=spec["gender"],
            mbti=spec["mbti"],
        )
        db.add(profile)

        # 3) md_documents 行(is_active=True)
        full_profile = build_profile_for(spec)
        md = MdDocument(
            user_id=user_id,
            version=1,
            profile_json=full_profile,
            profile_version=full_profile["meta"]["version"],
            portrait_body="\n\n".join(full_profile["portrait"]["body"]),
            domains_interested=full_profile["domains"]["interested"],
            domains_avoided=full_profile["domains"]["avoided"],
            raw_answers=full_profile["raw_answers"],
            is_active=True,
        )
        db.add(md)

        await db.commit()
        return user_id, True


# ========================================
# 触发 pipeline
# ========================================

async def run_pipeline_for(user_id: int) -> None:
    if DRY_RUN:
        print(f"  [DRY_RUN] would run_full_pipeline_for_user({user_id})")
        return
    t0 = time.time()
    try:
        await run_full_pipeline_for_user(user_id)
    except Exception as e:
        print(f"  ✗ pipeline failed user_id={user_id}: {type(e).__name__}: {e}")
        return
    print(f"  ✓ pipeline done user_id={user_id} · {time.time() - t0:.1f}s")


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


def _mock_user_ids_select():
    return select(User.id).where(User.is_system_mock.is_(True))


def _mock_chat_filter():
    mock_user_ids = _mock_user_ids_select()
    return or_(
        Match.user_a_id.in_(mock_user_ids),
        Match.user_b_id.in_(mock_user_ids),
    )


async def verify_mock_pool() -> dict[str, int]:
    print("=== Mock Pool Verification ===")

    mock_count = await _count_rows(
        select(func.count()).select_from(User).where(User.is_system_mock.is_(True))
    )
    print(f"Mock users (is_system_mock=true): {mock_count}")

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
    print(f"  by archetype: {_format_kv_counts(archetype_counts)}")

    gender_counts = await _group_counts(
        select(UserProfile.gender, func.count())
        .join(User, UserProfile.user_id == User.id)
        .where(User.is_system_mock.is_(True))
        .group_by(UserProfile.gender)
        .order_by(UserProfile.gender)
    )
    print(f"  by gender: {_format_kv_counts(gender_counts)}")

    age_counts = await _group_counts(
        select(UserProfile.age_band, func.count())
        .join(User, UserProfile.user_id == User.id)
        .where(User.is_system_mock.is_(True))
        .group_by(UserProfile.age_band)
        .order_by(UserProfile.age_band)
    )
    print(f"  by age_band: {_format_kv_counts(age_counts)}")

    return {"mock_count": mock_count, **{f"archetype_{k}": v for k, v in archetype_counts.items()}}


async def verify_agent_chats() -> dict[str, int]:
    print("\n=== Agent Chats ===")

    base = (
        select(func.count())
        .select_from(AgentChat)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
    )
    total = await _count_rows(base)
    print(f"Total chats involving mock users: {total}")

    status_counts = await _group_counts(
        select(AgentChat.status, func.count())
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
        .group_by(AgentChat.status)
        .order_by(AgentChat.status)
    )
    for status, count in status_counts.items():
        suffix = "  ← 异常,提示用户检查" if status == "running" and count else ""
        print(f"  {status}: {count} ({_pct(count, total)}){suffix}")

    end_reason_counts = await _group_counts(
        select(AgentChat.end_reason, func.count())
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter(), AgentChat.end_reason.is_not(None))
        .group_by(AgentChat.end_reason)
        .order_by(func.count().desc(), AgentChat.end_reason)
    )
    print(f"  end_reason 分布: {_format_kv_counts(end_reason_counts)}")

    return {"total_chats": total, **{f"status_{k}": v for k, v in status_counts.items()}}


async def verify_summaries() -> dict[str, int]:
    print("\n=== Summaries ===")

    total = await _count_rows(
        select(func.count())
        .select_from(Summary)
        .join(AgentChat, Summary.agent_chat_id == AgentChat.id)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
    )
    print(f"Total summaries involving mock users: {total}")

    verdict_counts = await _group_counts(
        select(Summary.verdict, func.count())
        .join(AgentChat, Summary.agent_chat_id == AgentChat.id)
        .join(Match, AgentChat.match_id == Match.id)
        .where(_mock_chat_filter())
        .group_by(Summary.verdict)
        .order_by(Summary.verdict)
    )
    for verdict in ("来电", "有点意思再观察", "不合"):
        count = verdict_counts.get(verdict, 0)
        target = TARGET_VERDICT_RATIOS[verdict]
        print(f"  verdict {verdict}: {count} ({_pct(count, total)})  ← target ~{target * 100:.0f}%")
    for verdict, count in verdict_counts.items():
        if verdict not in TARGET_VERDICT_RATIOS:
            print(f"  verdict {verdict}: {count} ({_pct(count, total)})  ← 未知 verdict")

    return {"total_summaries": total, **{f"verdict_{k}": v for k, v in verdict_counts.items()}}


def print_health(pool: dict[str, int], chats: dict[str, int], summaries: dict[str, int]) -> None:
    print("\n=== Health ===")

    expected_mock_count = len(MOCK_USERS)
    if pool["mock_count"] == expected_mock_count:
        print(f"✓ Mock count matches archetypes ({expected_mock_count})")
    else:
        print(f"⚠ Mock count mismatch: expected {expected_mock_count}, got {pool['mock_count']}")

    running = chats.get("status_running", 0)
    if running:
        print(f"⚠ {running} chats still running (重跑过没?)")
    else:
        print("✓ No running agent chats")

    total_summaries = summaries.get("total_summaries", 0)
    verdict_ok = True
    if total_summaries <= 0:
        verdict_ok = False
    for verdict, target in TARGET_VERDICT_RATIOS.items():
        actual = summaries.get(f"verdict_{verdict}", 0) / total_summaries if total_summaries else 0
        if abs(actual - target) > VERDICT_TOLERANCE:
            verdict_ok = False
            print(
                f"⚠ Verdict {verdict} outside tolerance: "
                f"{actual * 100:.0f}% vs target {target * 100:.0f}%"
            )
    if verdict_ok:
        print("✓ Verdict distribution within tolerance(±10%)")


async def verify() -> int:
    pool = await verify_mock_pool()
    chats = await verify_agent_chats()
    summaries = await verify_summaries()
    print_health(pool, chats, summaries)
    return 0


# ========================================
# main
# ========================================

async def main() -> int:
    print("=" * 60)
    print(f"CyberMOMO 冷启动 seed · 共 {len(MOCK_USERS)} 个 mock 用户")
    print(f"  DRY_RUN={DRY_RUN}  SKIP_PIPELINE={SKIP_PIPELINE}  "
          f"PIPELINE_USER_LIMIT={PIPELINE_USER_LIMIT}")
    print("=" * 60)

    # Phase 1: 插用户
    print("\n[1/2] 插入 mock 用户 + profile + md_document …")
    created: list[tuple[int, str, bool]] = []  # (user_id, username, was_new)
    for spec in MOCK_USERS:
        uid, was_new = await upsert_user(spec)
        flag = "+ new" if was_new else "= exists"
        print(f"  {flag:<10} user_id={uid:<6} {spec['username']:<24} {spec['nickname']}")
        created.append((uid, spec["username"], was_new))

    new_count = sum(1 for _, _, w in created if w)
    skip_count = len(created) - new_count
    print(f"\n小结:新建 {new_count} · 已存在 {skip_count}")

    if SKIP_PIPELINE:
        print("\nSKIP_PIPELINE=1,不跑 pipeline,完成。")
        return 0

    # Phase 2: 跑 pipeline(串行,避免 LLM 并发把 DashScope quota 打爆)
    print(f"\n[2/2] 串行跑 match → agent_chat → summary "
          f"(前 {PIPELINE_USER_LIMIT} 人)…")
    print("(每人 ~30s-3min,取决于匹配出多少 pair。Ctrl-C 中断不影响已写入数据)")

    targets = [uid for uid, _, _ in created if uid > 0][:PIPELINE_USER_LIMIT]
    for i, uid in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] user_id={uid}")
        await run_pipeline_for(uid)

    print("\n" + "=" * 60)
    print("✓ 冷启动 seed 完成。")
    print("\n下一步:")
    print("  · 跑真人 onboard,看 /room 能不能匹到 mock_xxx")
    print("  · SQL 查:")
    print("    select count(*) from users where is_system_mock;")
    print("    select count(*) from agent_chats;")
    print("    select count(*) from summaries;")
    print("=" * 60)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed CyberMOMO cold-start mock users or verify seeded data.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只读检查 mock pool、agent_chat 和 summary verdict 分布,不执行 seed。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        rc = asyncio.run(verify() if args.verify else main())
    finally:
        # 关 async engine,避免 'unclosed connector' warning
        try:
            asyncio.run(engine.dispose())
        except RuntimeError:
            pass
    sys.exit(rc)
