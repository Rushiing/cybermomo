#!/usr/bin/env python3
"""
Backfill embeddings · 一次性脚本(幂等)

把已有的 md_segments / summaries 里 embedding=NULL 的行补上,让 RAG 检索可以工作。
新写入流程在 Phase 1.2 实装时会同步生成 embedding,这个脚本只补存量。

跑法(api 容器或本地):
    cd apps/api
    python scripts/backfill_embeddings.py

环境:
    DATABASE_URL / DASHSCOPE_API_KEY(走 src.shared.settings)

行为:
    - md_segments WHERE embedding IS NULL → embed content
    - summaries WHERE embedding IS NULL → embed "verdict | highlights | risks | recommended"
    - 串行调 llm_embed(避免 DashScope 限流),失败跳过 + 打印
    - 每条更新独立 commit,中途崩了不丢前面进度

退出码:0 = 全部成功;1 = 有失败但部分成功(看 stderr 计数)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 让 src/ 可 import(脚本从 apps/api/ 跑)
APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import select  # noqa: E402

from src.llm.gateway import llm_embed  # noqa: E402
from src.md.models import MdSegment  # noqa: E402
from src.shared.db import SessionLocal  # noqa: E402
from src.summary.models import Summary  # noqa: E402


def _summary_text(s: Summary) -> str:
    """组装 summary 的可索引文本(verdict + highlights + risks + recommended)"""
    parts: list[str] = [f"判断: {s.verdict}"]
    for h in (s.highlights or []):
        txt = h.get("text") if isinstance(h, dict) else None
        if txt:
            parts.append(f"看点: {txt}")
    for r in (s.risks or []):
        txt = r.get("text") if isinstance(r, dict) else None
        if txt:
            parts.append(f"留意: {txt}")
    if s.recommended_action:
        parts.append(f"建议: {s.recommended_action}")
    return "\n".join(parts)


async def backfill_md_segments() -> tuple[int, int]:
    """返回 (success, failed)"""
    success = 0
    failed = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(MdSegment).where(MdSegment.embedding.is_(None))
            )
        ).scalars().all()
        total = len(rows)
        print(f"[md_segments] {total} rows pending")
        for i, seg in enumerate(rows, 1):
            if not (seg.content or "").strip():
                print(f"  [{i}/{total}] segment {seg.id}: empty content, skip")
                continue
            try:
                resp = await llm_embed(
                    seg.content,
                    db=None,  # backfill 不写 llm_call_log,避免日志洪水
                    user_id=seg.user_id,
                    related_table="md_segments",
                    related_id=seg.id,
                )
                seg.embedding = resp.vector
                await db.commit()
                success += 1
                if i % 10 == 0 or i == total:
                    print(f"  [{i}/{total}] md_segments embedded")
            except Exception as e:
                failed += 1
                print(f"  [{i}/{total}] segment {seg.id} FAILED: {e}", file=sys.stderr)
                await db.rollback()
    return success, failed


async def backfill_summaries() -> tuple[int, int]:
    success = 0
    failed = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Summary).where(Summary.embedding.is_(None))
            )
        ).scalars().all()
        total = len(rows)
        print(f"[summaries] {total} rows pending")
        for i, s in enumerate(rows, 1):
            text = _summary_text(s)
            if not text.strip():
                print(f"  [{i}/{total}] summary {s.id}: empty text, skip")
                continue
            try:
                resp = await llm_embed(
                    text,
                    db=None,
                    user_id=s.host_user_id,
                    related_table="summaries",
                    related_id=s.id,
                )
                s.embedding = resp.vector
                await db.commit()
                success += 1
                if i % 10 == 0 or i == total:
                    print(f"  [{i}/{total}] summaries embedded")
            except Exception as e:
                failed += 1
                print(f"  [{i}/{total}] summary {s.id} FAILED: {e}", file=sys.stderr)
                await db.rollback()
    return success, failed


async def main() -> int:
    print("=== backfill embeddings ===")
    md_ok, md_fail = await backfill_md_segments()
    sm_ok, sm_fail = await backfill_summaries()
    print()
    print(f"md_segments: {md_ok} ok, {md_fail} failed")
    print(f"summaries:   {sm_ok} ok, {sm_fail} failed")
    return 0 if (md_fail + sm_fail) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
