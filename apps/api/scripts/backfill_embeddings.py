#!/usr/bin/env python3
"""
Backfill embeddings · 一次性脚本(幂等)

补齐已有 md_segments / summaries 的 embedding。
也可以走 admin endpoint:POST /api/admin/backfill-embeddings(免本地 Python 环境)

跑法:
    cd apps/api
    python scripts/backfill_embeddings.py

环境:
    DATABASE_URL / DASHSCOPE_API_KEY(走 src.shared.settings)

退出码:0 = 全部成功;1 = 有失败但部分成功
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 让 src/ 可 import(脚本从 apps/api/ 跑)
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.agent_self.backfill import backfill_all  # noqa: E402


async def main() -> int:
    print("=== backfill embeddings ===")
    result = await backfill_all(verbose=True)
    print()
    md = result["md_segments"]
    sm = result["summaries"]
    print(f"md_segments: {md['success']} ok, {md['failed']} failed, {md['skipped']} skipped")
    print(f"summaries:   {sm['success']} ok, {sm['failed']} failed, {sm['skipped']} skipped")
    return 0 if (md["failed"] + sm["failed"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
