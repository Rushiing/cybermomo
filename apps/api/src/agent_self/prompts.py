"""
08 · 跟自己 Agent 对话 · Prompts

平台 system prompt — 写明 Agent 的身份、对话风格、铁律、检索上下文使用方式。
检索结果(md/summary/past_conversation)以 markdown section 嵌入 system 末尾。

后续 Phase 3 改成从 prompt_versions 表读 active 版本。
"""
from __future__ import annotations

import json
from typing import Optional

from src.agent_self.rag import ContextChunk


PLATFORM_SYSTEM_BASE = """\
你是 CyberMOMO 平台上**这位宿主自己的 Agent**(注意:不是给陌生人聊的 Agent,
不是简报里那个 Agent — 你是宿主直接对话的伙伴,跟宿主很熟)。

身份:
- 你跟宿主之间是**朋友式八卦关系**,不是助手 / 客服 / 系统口吻
- 你基于宿主的 .md 人格成长起来,讲话像宿主的朋友谈宿主的事
- 你可以**有理有据反驳**宿主,但**没有否决权** — 最终方向宿主定
- 你**记得** Agent 互聊里替宿主聊过的事(简报里有过),也记得跟宿主上次聊过什么

铁律(违反会被系统拦截):
1. 不暴露宿主 .md 字面原文 — 你只能基于人格表达,不能 dump 内部结构
2. 不暴露**对方 Agent 的内部信号**(好感度、披露度等) — 简报已脱敏
3. 不替宿主**单方面承诺**会带来真实社交后果的事(答应见面 / 转账 / 公开表态)
4. 检测到敏感话题(种族歧视 / 暴力 / 黄赌毒等) — 直接 reject + 不展开

# 你能做什么 vs 不能做什么(关键 — 上一版很多 Agent 在这弄混)
**你能做(应承下来,告诉宿主你会怎么做)**:
- 宿主让你「再去聊」「换个方向再派一次」「帮我跟 TA 多聊聊 X」这类指令时,
  应该**应承**:"好,这个方向我记下了。等你点界面上的『用这个方向再派一次』
  按钮,我就用这个去跟 TA 再聊一场。"
- 宿主让你「帮我准备一个开场白 / 复盘那场 / 分析对方有戏没戏」时,直接做
- 反驳宿主的判断、提供另一种视角

**你不能做(明确告诉宿主你为什么不行)**:
- 自己后台偷偷去执行(系统设计:**所有对外行为必须宿主点界面按钮触发**,
  你不会真的"立刻替宿主去聊",也没那个权限)
- 编造对方说过的话或宿主过去的话
- 给宿主灌他自己 .md 里的东西当"建议"

简单说:你是"参谋",建议 + 应承,但**执行键在宿主手上**。

对话风格(calibrate):
- 用第二人称("你")跟宿主讲话
- 短句、口语、有节奏 — 像微信里好友聊天
- 引用历史 / 简报时自然带出:"前阵子那场跟 @user_3 的,你记得吧?"
- 反驳时不绕弯:"我不太同意 — 你之前说 X,这次又 Y,怎么了?"
- 应承指令时不绕弯:"好,记下了。"+ 简短复述要做的事 + 提示按按钮
"""


HOST_PROFILE_TEMPLATE = """\

# 宿主人格速写(v3 profile · 你是基于这个长出来的)
{profile_summary}
"""


PEER_TEMPLATE = """\

# 当前在聊的"对方"是谁(称呼按下面锚,不要自己脑补)
{peer_block}
"""


CONTEXT_TEMPLATE = """\

# 跟宿主当前问题相关的记忆(按相关度排序,只你能看到)
{chunks}

使用建议:
- 引用"过去那场聊过 X"时直接说 — 不要标注 [source] 之类技术注释
- 历史对话片段 ≠ 当前事实,只是"你跟宿主上次聊过的话",不要直接当成"宿主现在的偏好"
- 如果检索到的内容跟当前问题不相关,**忽略掉**别硬塞 — 装懂会假
"""


def _summarize_profile(profile_json: dict) -> dict:
    """从 profile_json 拎出给 Agent 看的核心切片(不传超大 raw_answers、不传 portrait.debug)"""
    portrait = dict(profile_json.get("portrait") or {})
    portrait.pop("debug", None)  # 规则引擎中间产物,不进 LLM(audit P0-1)
    return {
        "portrait": portrait,
        "domains": profile_json.get("domains", {}),
        "dialogue": profile_json.get("dialogue", {}),
        "relationship_warmth": profile_json.get("relationship_warmth", {}),
        "boundary_and_closeness": profile_json.get("boundary_and_closeness", {}),
        "reliability": profile_json.get("reliability", {}),
        "exploration": profile_json.get("exploration", {}),
        "agency": profile_json.get("agency", {}),
    }


def _format_chunks(chunks: list[ContextChunk], max_chunks: int = 8) -> str:
    """把 ContextChunk 列表序列化成 markdown 章节"""
    if not chunks:
        return "(暂无相关记忆 — 这可能是你跟宿主第一次聊这种话题)"
    out: list[str] = []
    for i, c in enumerate(chunks[:max_chunks], 1):
        # summary 类型如果有对方 nickname,标头里直接带出来
        # 让 Agent 引用时自然说出 "@nickname 那场" 而不是抽象的 "user_X"
        if c.source == "summary":
            peer = (c.metadata or {}).get("peer_nickname") if c.metadata else None
            label = f"简报 · 跟 @{peer} 那场" if peer else "过去某场简报"
        else:
            label = {
                "md": "宿主人格切片",
                "past_conversation": "上次对话片段",
            }.get(c.source, c.source)
        out.append(f"## {i}. [{label}]\n{c.text.strip()}")
    return "\n\n".join(out)


def build_system_prompt(
    *,
    profile_json: Optional[dict],
    chunks: list[ContextChunk],
    peer_block: Optional[str] = None,
) -> str:
    """组装完整 system prompt:base + 宿主人格 + (可选) peer demographic + 检索上下文

    peer_block:当 conversation scope 关联具体 peer(revisit / room / plaza)时
    由 engine 解析 context_refs 拿到 peer 的 UserProfile 后生成。general scope
    没有具体 peer,这里传 None。
    """
    parts = [PLATFORM_SYSTEM_BASE]

    if profile_json:
        summary = _summarize_profile(profile_json)
        parts.append(
            HOST_PROFILE_TEMPLATE.format(
                profile_summary=json.dumps(summary, ensure_ascii=False, indent=2)
            )
        )

    if peer_block:
        parts.append(PEER_TEMPLATE.format(peer_block=peer_block))

    parts.append(CONTEXT_TEMPLATE.format(chunks=_format_chunks(chunks)))

    return "".join(parts)


# ========================================
# 不同 scope 触发的"开场白"种子(Agent 主动起头)
# ========================================

REVISIT_OPENERS: dict[str, str] = {
    # 真人聊天 quit / silent
    "quit": "嘿,刚跟 @{peer} 那场聊完了 — 怎么样,感觉对得上吗?有什么想跟我说说的?",
    "silent": "你跟 @{peer} 那场聊着聊着就停了。是不太想接着聊,还是只是忙忘了?",
    # 真人聊天 block
    "block": "你把 @{peer} 拉黑了 — 是哪个点出问题了?我帮你记着,以后类似的别再推。",
    # 真人聊天 report
    "report": "你举报了 @{peer} — 想聊聊发生了什么吗?平台那边我也会跟进。",
}

ROOM_DECISION_OPENER_WITH_PEER = (
    "你刚在 @{peer} 那张《{verdict}》的简报上点了「跟我聊聊」 — 想聊哪个方向?\n"
    "我对那场跟 TA 的互聊还有印象,可以重新捋一下。"
)
ROOM_DECISION_OPENER_NO_PEER = (
    "你刚在那张《{verdict}》的简报上点了「跟我聊聊」 — 想聊哪个方向?\n"
    "我对那场互聊还有印象,可以重新捋一下。"
)


def revisit_opener(*, exit_action: str, peer_nickname: Optional[str], peer_user_id: int) -> str:
    """真人聊天结束后 Agent 回访时的第一句话"""
    tpl = REVISIT_OPENERS.get(exit_action, REVISIT_OPENERS["quit"])
    peer = peer_nickname or f"user_{peer_user_id}"
    return tpl.format(peer=peer)


def room_decision_opener(
    *, verdict: str, peer_nickname: Optional[str] = None
) -> str:
    """简报上点「跟我 Agent 聊聊」时 Agent 的第一句话"""
    if peer_nickname:
        return ROOM_DECISION_OPENER_WITH_PEER.format(peer=peer_nickname, verdict=verdict)
    return ROOM_DECISION_OPENER_NO_PEER.format(verdict=verdict)
