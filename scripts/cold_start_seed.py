#!/usr/bin/env python3
"""
冷启动种子脚本 · 本地 CLI 兼容入口

核心逻辑已搬到 `apps/api/src/seed/operations.py`,本脚本只是 thin wrapper —
让本地能用 DATABASE_URL 直接连 Railway DB 跑,而不必走 admin HTTP endpoint。

用法:
    cd apps/api
    DATABASE_URL=postgresql+asyncpg://... PYTHONPATH=. \
        python3 ../../scripts/cold_start_seed.py
    python3 ../../scripts/cold_start_seed.py --verify

可选环境变量:
    DRY_RUN=1            — 只打印计划不写库(不实际跑 insert / pipeline)
    SKIP_PIPELINE=1      — 只插用户不跑 LLM
    PIPELINE_USER_LIMIT  — 跑前 N 个 mock 用户(默认 20)
    MOCK_PASSWORD        — mock 用户的密码占位

如果你不想本地配 DATABASE_URL,用 admin HTTP endpoint 远程触发:
    POST /api/admin/seed/insert
    POST /api/admin/seed/run-pipeline
    GET  /api/admin/seed/status
    GET  /api/admin/seed/verify
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# 允许从仓库根目录直接跑,自动把 apps/api 加进 sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from src.seed.archetypes import MOCK_USERS  # noqa: E402
from src.seed.operations import (  # noqa: E402
    DEFAULT_MOCK_PASSWORD,
    TARGET_VERDICT_RATIOS,
    insert_all_mock_users,
    upsert_one_mock_user,
    verify_all,
)
from src.match.pipeline import run_full_pipeline_for_user  # noqa: E402
from src.shared.db import engine  # noqa: E402


DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
SKIP_PIPELINE = os.environ.get("SKIP_PIPELINE", "0") == "1"
PIPELINE_USER_LIMIT = int(os.environ.get("PIPELINE_USER_LIMIT", str(len(MOCK_USERS))))
PASSWORD = os.environ.get("MOCK_PASSWORD", DEFAULT_MOCK_PASSWORD)


# ========================================
# Verification 输出(对终端友好的格式)
# ========================================

def _pct(n: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(n / total * 100):.0f}%"


def _format_kv_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "(none)"
    return ", ".join(f"{k}={v}" for k, v in counts.items())


def _print_verification(result: dict) -> None:
    pool = result["pool"]
    chats = result["agent_chats"]
    summaries = result["summaries"]

    print("=== Mock Pool Verification ===")
    print(f"Mock users (is_system_mock=true): {pool['mock_count']}")
    print(f"  by archetype: {_format_kv_counts(pool['by_archetype'])}")
    print(f"  by gender: {_format_kv_counts(pool['by_gender'])}")
    print(f"  by age_band: {_format_kv_counts(pool['by_age_band'])}")

    print("\n=== Agent Chats ===")
    print(f"Total chats involving mock users: {chats['total']}")
    for s, c in chats["by_status"].items():
        suffix = "  ← 异常,提示用户检查" if s == "running" and c else ""
        print(f"  {s}: {c} ({_pct(c, chats['total'])}){suffix}")
    print(f"  end_reason 分布: {_format_kv_counts(chats['by_end_reason'])}")

    print("\n=== Summaries ===")
    print(f"Total summaries involving mock users: {summaries['total']}")
    for entry in summaries["distribution"]:
        target = TARGET_VERDICT_RATIOS[entry["verdict"]]
        print(
            f"  verdict {entry['verdict']}: {entry['count']} "
            f"({_pct(entry['count'], summaries['total'])})  ← target ~{target*100:.0f}%"
        )
    for verdict, count in summaries["extra_verdicts"].items():
        print(f"  verdict {verdict}: {count} ({_pct(count, summaries['total'])})  ← 未知 verdict")

    print("\n=== Health ===")
    if result["ok"]:
        print("✓ all checks passed")
    else:
        for w in result["health_warnings"]:
            print(f"⚠ {w}")


# ========================================
# Insert + pipeline(本地串行,不走 BackgroundTask)
# ========================================

async def _insert_phase() -> list[tuple[int, str, bool]]:
    print("\n[1/2] 插入 mock 用户 + profile + md_document …")
    created: list[tuple[int, str, bool]] = []
    for spec in MOCK_USERS:
        if DRY_RUN:
            print(f"  [DRY_RUN] would insert {spec['username']} ({spec['nickname']})")
            created.append((-1, spec["username"], True))
            continue
        uid, was_new = await upsert_one_mock_user(spec, password=PASSWORD)
        flag = "+ new" if was_new else "= exists"
        print(f"  {flag:<10} user_id={uid:<6} {spec['username']:<24} {spec['nickname']}")
        created.append((uid, spec["username"], was_new))
    new_count = sum(1 for _, _, w in created if w)
    print(f"\n小结:新建 {new_count} · 已存在 {len(created) - new_count}")
    return created


async def _pipeline_phase(user_ids: list[int]) -> None:
    print(f"\n[2/2] 串行跑 match → agent_chat → summary (前 {len(user_ids)} 人)…")
    print("(每人 ~30s-3min;Ctrl-C 中断不影响已写入数据)")
    for i, uid in enumerate(user_ids, 1):
        print(f"\n[{i}/{len(user_ids)}] user_id={uid}")
        if DRY_RUN:
            print(f"  [DRY_RUN] would run_full_pipeline_for_user({uid})")
            continue
        t0 = time.time()
        try:
            await run_full_pipeline_for_user(uid)
        except Exception as e:
            print(f"  ✗ pipeline failed user_id={uid}: {type(e).__name__}: {e}")
            continue
        print(f"  ✓ pipeline done user_id={uid} · {time.time() - t0:.1f}s")


# ========================================
# main
# ========================================

async def main() -> int:
    print("=" * 60)
    print(f"CyberMOMO 冷启动 seed · 共 {len(MOCK_USERS)} 个 mock 用户")
    print(f"  DRY_RUN={DRY_RUN}  SKIP_PIPELINE={SKIP_PIPELINE}  "
          f"PIPELINE_USER_LIMIT={PIPELINE_USER_LIMIT}")
    print("=" * 60)

    created = await _insert_phase()

    if SKIP_PIPELINE:
        print("\nSKIP_PIPELINE=1,不跑 pipeline,完成。")
        return 0

    targets = [uid for uid, _, _ in created if uid > 0][:PIPELINE_USER_LIMIT]
    await _pipeline_phase(targets)

    print("\n" + "=" * 60)
    print("✓ 冷启动 seed 完成。可跑 `--verify` 看分布。")
    print("=" * 60)
    return 0


async def verify_main() -> int:
    result = await verify_all()
    _print_verification(result)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed CyberMOMO cold-start mock users or verify seeded data.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只读检查 mock pool / agent_chat / summary verdict 分布,不执行 seed。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        rc = asyncio.run(verify_main() if args.verify else main())
    finally:
        try:
            asyncio.run(engine.dispose())
        except RuntimeError:
            pass
    sys.exit(rc)
