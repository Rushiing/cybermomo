"""
03 · 匹配引擎 · 脱敏 Agent

输入:matches + matchpoints + 双方 profile_json
输出:match_hooks(给 A 看的 hook + 给 B 看的 hook)

铁律:hook_text **不含对方 .md 原文片段**,只能是话题种子的人格化表达。
sensitivity_level Agent 自评(0=公共 / 1=轻度个人 / 2=敏感)。

MVP 用 inline prompt;v0.2 起可改为从 prompt_versions 表读 active 版本。
完整 prompt v0 见 cybermomo/落地拆解/03-匹配引擎/03-脱敏Agent prompt-v0.md
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.models import Match, Matchpoint, MatchHook
from src.md.models import MdDocument
from src.shared.leak_scanner import scrub_peer_visible_text


SYSTEM_PROMPT = """\
你是 CyberMOMO 平台的脱敏 Agent。

输入是一对用户(A、B)的匹配结果:matchpoints(双方某些维度上的同类共鸣 / 互补吸引)、双方的 v3 profile_json 摘要(已脱敏)。

任务:为每条 matchpoint 产出**两份** hook(分别给 A 和给 B 看),作为后续 Agent 互聊的"话题种子"。

铁律(必守):
1. hook_text 只能是话题人格化表达,不得包含对方 v3 profile_json 里的字面 segment 文本
2. 不暴露对方除 nickname / domains / connection 类标签之外的任何具体字段
3. 给 A 的 hook 里不能出现 B 的敏感细节(例如某条具体 raw_answer 文本)
4. 每条 hook 自带 sensitivity_level(0=公共信息 / 1=轻度个人 / 2=敏感),后台据此审计

# hook_text 该长什么样(实测发现 deepseek 偏走"相亲网站软文体",违一即翻车)

**功能定位**:hook_text 是**给后面 Agent 互聊起头的话题种子**,不是双方关系评价/总结。
读 hook 的不是宿主,是另一个 Agent — TA 拿这条直接开口,所以 hook 应该是
**一个能起话题的引子**(具体话题 / 动作 / 问题),不是关系咨询师写的 PR 软文。

**禁用句式**:
- 抽象关系评价词:"渴望 / 期待 / 共鸣 / 基石 / 相处 / 尊重彼此 / 深度连接 / 精神共鸣 / 纽带"
- 软推断助词:"也许可以 / 或许可以 / 可能会 / 应该能 / 不妨"
- "你 X,而对方也 X" / "你们都 X,做事 Y" 对仗总结句
- "这种 X 的态度可能会让你们 Y"(评论式总结句)
- "建立关系的基石" / "可能是你们的连接点"(关系咨询师腔)

**改用**:
- 具体话题切入,带场景或动作:"试着问 TA 上次自己拍板的决定是哪件事"、"聊聊各自不喜欢的开场方式"
- 短句直接给引子方向,不要带评价 / 总结
- hook 可以**直接是个问题**:"问问 TA 怎么看 X"

**字数硬约束**:hook_text ≤ 60 字。超字数 = 大概率塞了评价/废话。

# 范例(给你校准的具体范本)

不好(相亲软文):"你渴望的是真正有共鸣的关系,而对方也抱有同样的期待。不妨探讨一下你们心中理想的连接是什么样的。"
好(话题引子):"问问 TA 最近哪次决定是自己硬扛下来的 — 你俩都不爱被人安排,这个点能聊出来。"

不好(关系评价总结):"你们都不会轻易许下承诺,一旦承诺就会认真对待。这种谨慎的态度可能会让你们在相处中更懂得尊重彼此的边界。"
好(话题引子):"聊聊上次答应过别人却没兑现的事 — 你俩对'承诺'的标准可能都不低。"

输出严格 JSON(直接 JSON 对象,无 markdown 代码块包裹):
{
  "hooks_for_a": [
    {"topic_id":"...","category":"...","match_type":"...","hook_text":"<话题引子,严格遵守上面'hook_text 该长什么样'段。一句话,≤ 60 字>","sensitivity_level":0|1|2,"matchpoint_ref":<int>}
  ],
  "hooks_for_b": [
    {"topic_id":"...","category":"...","match_type":"...","hook_text":"<同上>","sensitivity_level":0|1|2,"matchpoint_ref":<int>}
  ]
}

每条 matchpoint 对应一对 hook(给 A 一个,给 B 一个),matchpoint_ref 用 input 里 matchpoint 的 idx(从 0 起)。
top 5 matchpoints 即可,多了让互聊发散。
"""


def _extract_safe_profile_summary(profile: dict) -> dict:
    """从 profile_json 里抽允许出现在 prompt 上下文的部分(脱敏)。
    给 LLM 用;不进入最终 hook_text。"""
    return {
        "domains": profile.get("domains", {}),
        "connection_value_label": profile.get("relationship_warmth", {}).get("connection_value", {}).get("label"),
        "warmth_initiation_label": profile.get("relationship_warmth", {}).get("warmth_initiation", {}).get("label"),
        "support_style_label": profile.get("relationship_warmth", {}).get("support_style", {}).get("label"),
        # 维度数值用模糊三档(高/中/低)而不是原始数字,避免精确比对
        "dimension_buckets": _bucketize_dimensions(profile),
    }


def _bucketize_dimensions(profile: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for section in ["dialogue", "boundary_and_closeness", "reliability", "conflict_repair", "exploration", "agency"]:
        for k, v in (profile.get(section) or {}).items():
            if isinstance(v, (int, float)):
                if v >= 67:
                    out[k] = "高"
                elif v <= 34:
                    out[k] = "低"
                else:
                    out[k] = "中"
    return out


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_loose_json(text: str) -> dict | None:
    """尝试从 LLM 输出里提取 JSON;支持 ```json ``` 围栏 / 直接 JSON / 前后乱字符"""
    text = text.strip()
    # 直接尝试
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 围栏
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # 找第一个 { 到最后一个 }
    if "{" in text and "}" in text:
        try:
            chunk = text[text.index("{"): text.rindex("}") + 1]
            return json.loads(chunk)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def run_desensitize_for_match(
    db: AsyncSession,
    *,
    match: Match,
) -> list[MatchHook]:
    """
    给 match 跑脱敏 Agent,产出 match_hooks(双方各一份)写入 DB,返回新建的 hooks。
    若 LLM 调用失败,返回空 list,不抛错(允许后续重试)。
    """
    # 拉 matchpoints
    mps = (await db.execute(
        select(Matchpoint).where(Matchpoint.match_id == match.id)
    )).scalars().all()
    if not mps:
        return []

    # 拉双方 active profile
    profiles_rows = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id.in_([match.user_a_id, match.user_b_id]),
            MdDocument.is_active.is_(True),
        )
    )).scalars().all()
    profile_by_user: dict[int, dict] = {p.user_id: p.profile_json for p in profiles_rows}
    if match.user_a_id not in profile_by_user or match.user_b_id not in profile_by_user:
        return []

    a_profile = _extract_safe_profile_summary(profile_by_user[match.user_a_id])
    b_profile = _extract_safe_profile_summary(profile_by_user[match.user_b_id])

    matchpoints_input = [
        {
            "idx": i,
            "category": mp.category,
            "match_type": mp.match_type,
            "similarity": float(mp.similarity),
            "weight": float(mp.weight),
            "a_source_segments": mp.a_source_segments,
            "b_source_segments": mp.b_source_segments,
        }
        for i, mp in enumerate(mps[:8])  # 最多给 LLM 8 条,Agent 自己再筛 top 5
    ]

    user_payload = json.dumps({
        "match_id": match.id,
        "is_wildcard": match.is_wildcard,
        "overall_score": float(match.overall_score),
        "user_a": {"id": match.user_a_id, "profile_summary": a_profile},
        "user_b": {"id": match.user_b_id, "profile_summary": b_profile},
        "matchpoints": matchpoints_input,
    }, ensure_ascii=False)

    resp = await llm_chat(
        role="desensitize",
        messages=[Message(role="user", content=user_payload)],
        system=SYSTEM_PROMPT,
        max_tokens=2048,
        temperature=0.5,
        db=db,
        related_table="matches",
        related_id=match.id,
    )

    parsed = _parse_loose_json(resp.text)
    if parsed is None or "hooks_for_a" not in parsed or "hooks_for_b" not in parsed:
        print(f"[desensitize] LLM 输出解析失败 match_id={match.id}")
        return []

    new_hooks: list[MatchHook] = []
    for target_user_id, peer_user_id, key in [
        (match.user_a_id, match.user_b_id, "hooks_for_a"),
        (match.user_b_id, match.user_a_id, "hooks_for_b"),
    ]:
        # hook 给 target 看,绝不能含 peer 的 .md 原文(铁律3)。拿 peer 完整 profile 扫。
        peer_profile = profile_by_user.get(peer_user_id, {})
        for h in parsed.get(key, []):
            ref_idx = h.get("matchpoint_ref")
            if ref_idx is None or not (0 <= ref_idx < len(mps)):
                continue
            raw_hook_text = str(h.get("hook_text", ""))[:1000]
            # 确定性兜底(audit P0-1):LLM 不照抄是自律,这里做硬拦截
            safe_text, leaked = scrub_peer_visible_text(raw_hook_text, peer_profile)
            if leaked:
                print(
                    f"[desensitize] hook_text 命中对方 .md 片段,丢弃 "
                    f"match_id={match.id} target={target_user_id} frag={leaked!r}"
                )
                continue  # 丢弃这条 hook,不让原文穿透给对方
            sensitivity = int(h.get("sensitivity_level", 0))
            sensitivity = max(0, min(2, sensitivity))
            hook = MatchHook(
                match_id=match.id,
                target_user_id=target_user_id,
                matchpoint_id=mps[ref_idx].id,
                topic_id=str(h.get("topic_id", f"topic_{ref_idx}")),
                category=str(h.get("category", mps[ref_idx].category)),
                match_type=str(h.get("match_type", mps[ref_idx].match_type)),
                hook_text=safe_text,
                sensitivity_level=sensitivity,
            )
            db.add(hook)
            new_hooks.append(hook)

    await db.commit()
    return new_hooks
