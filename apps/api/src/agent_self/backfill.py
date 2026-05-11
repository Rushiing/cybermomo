"""
08 · RAG embedding 回填(脚本 + admin endpoint 共用)

幂等:只补 embedding IS NULL 的行,已有 embedding 不动。
- backfill_md_segments():md_segments
- backfill_summaries()  :summaries
- backfill_all()        :上面两个串行

每行独立 commit,中途任意失败不丢前面进度。失败 + 跳过 + 成功分别计数。
"""
from __future__ import annotations

from sqlalchemy import select

from src.llm.gateway import llm_embed
from src.md.models import MdSegment
from src.shared.db import SessionLocal
from src.summary.models import Summary


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


async def backfill_md_segments(*, verbose: bool = False) -> dict:
    """回填所有 embedding IS NULL 的 md_segments。

    Returns:
        {"total": int, "success": int, "failed": int, "skipped": int}
    """
    success = failed = skipped = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(MdSegment).where(MdSegment.embedding.is_(None))
            )
        ).scalars().all()
        total = len(rows)
        if verbose:
            print(f"[md_segments] {total} rows pending")
        for i, seg in enumerate(rows, 1):
            if not (seg.content or "").strip():
                skipped += 1
                continue
            try:
                resp = await llm_embed(
                    seg.content,
                    user_id=seg.user_id,
                    related_table="md_segments",
                    related_id=seg.id,
                )
                seg.embedding = resp.vector
                await db.commit()
                success += 1
                if verbose and (i % 10 == 0 or i == total):
                    print(f"  [{i}/{total}] md_segments embedded")
            except Exception as e:
                failed += 1
                if verbose:
                    print(f"  segment {seg.id} FAILED: {e}")
                await db.rollback()
    return {"total": total, "success": success, "failed": failed, "skipped": skipped}


async def backfill_summaries(*, verbose: bool = False) -> dict:
    """回填所有 embedding IS NULL 的 summaries。

    Returns:
        {"total": int, "success": int, "failed": int, "skipped": int}
    """
    success = failed = skipped = 0
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Summary).where(Summary.embedding.is_(None))
            )
        ).scalars().all()
        total = len(rows)
        if verbose:
            print(f"[summaries] {total} rows pending")
        for i, s in enumerate(rows, 1):
            text = _summary_text(s)
            if not text.strip():
                skipped += 1
                continue
            try:
                resp = await llm_embed(
                    text,
                    user_id=s.host_user_id,
                    related_table="summaries",
                    related_id=s.id,
                )
                s.embedding = resp.vector
                await db.commit()
                success += 1
                if verbose and (i % 10 == 0 or i == total):
                    print(f"  [{i}/{total}] summaries embedded")
            except Exception as e:
                failed += 1
                if verbose:
                    print(f"  summary {s.id} FAILED: {e}")
                await db.rollback()
    return {"total": total, "success": success, "failed": failed, "skipped": skipped}


async def backfill_all(*, verbose: bool = False) -> dict:
    """串行回填 md_segments + summaries"""
    md = await backfill_md_segments(verbose=verbose)
    sm = await backfill_summaries(verbose=verbose)
    return {"md_segments": md, "summaries": sm}
