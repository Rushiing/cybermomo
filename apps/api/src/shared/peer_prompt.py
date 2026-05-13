"""
shared · peer demographic prompt block

跨模块复用的"对方简介 + 称呼锚"工具。三处都用:
  - agent_chat:互聊时对方人格速写(让 Agent 用相称语气,不要把女生叫"哥们儿")
  - summary:简报里跟宿主八卦时,称呼对方要看 peer 的 gender/age
  - agent_self:跟自己 Agent 聊时,如果在聊某个 peer 也要给 demographic

实现是无 SQL 的,只把已有的 UserProfile 字段格式化成 prompt block。
调用方负责从 DB 取 UserProfile / 传 host 的 age_band 用于跨年龄段判定。

字段允许 NULL(老用户没填完)— prompt 里降级到 nickname。
"""
from __future__ import annotations

from typing import Optional

# AGE_OPTIONS 跟前端 md/basic 对齐
_AGE_BANDS = ["18-25", "25-30", "30-35", "35-40", "40+"]


def _age_band_index(band: Optional[str]) -> Optional[int]:
    if band is None:
        return None
    try:
        return _AGE_BANDS.index(band)
    except ValueError:
        return None


def _age_gap_is_large(host_band: Optional[str], peer_band: Optional[str]) -> bool:
    """两人是不是差 ≥ 10 岁(差 2 档算大)"""
    hi = _age_band_index(host_band)
    pi = _age_band_index(peer_band)
    if hi is None or pi is None:
        return False
    return abs(hi - pi) >= 2


_GENDER_LABEL = {
    "female": "女",
    "male": "男",
    "non_binary": "非二元",
    "prefer_not_to_say": "未透露",
}


def format_peer_block(
    *,
    peer_nickname: Optional[str],
    peer_user_id: Optional[int],
    peer_age_band: Optional[str],
    peer_gender: Optional[str],
    peer_mbti: Optional[str],
    host_age_band: Optional[str] = None,
) -> str:
    """
    返回一段插入 prompt 的 markdown 文本。

    包含两块:
    1. **对方简介**:nickname / age / gender / MBTI(NULL 字段不展示)
    2. **称呼锚**:基于 gender + 年龄差的硬映射规则,降低 LLM 自由发挥
       — 这是为了解"把女生叫哥们儿"那类问题。

    调用方拼到 prompt 的合适位置(summary 在 SYSTEM 里,agent_chat 在 TURN
    prompt 里)。block 末尾不带前后空行,调用方自己 padding。
    """
    nick_for_addr = peer_nickname or (f"user_{peer_user_id}" if peer_user_id else "对方")

    # 简介行
    info_parts: list[str] = []
    if peer_nickname:
        info_parts.append(f"昵称:@{peer_nickname}")
    elif peer_user_id:
        info_parts.append(f"标识:user_{peer_user_id}")
    if peer_age_band:
        info_parts.append(f"年龄:{peer_age_band}")
    if peer_gender:
        info_parts.append(f"性别:{_GENDER_LABEL.get(peer_gender, peer_gender)}")
    if peer_mbti:
        info_parts.append(f"MBTI:{peer_mbti}")
    info_line = " / ".join(info_parts) if info_parts else "(对方资料不全)"

    # 称呼锚 — 用硬规则锁住,LLM 不要自行推理 mapping
    age_gap_large = _age_gap_is_large(host_age_band, peer_age_band)
    if not peer_gender and not peer_age_band:
        addr_rule = (
            f"称呼锚(NULL 字段多 — 别猜):全程用 @{nick_for_addr} 或'TA / 这位',"
            f"**禁用**'哥们儿 / 兄弟 / 姐妹 / 老哥'等带性别 + 同辈预设的词。"
        )
    elif peer_gender == "male":
        if age_gap_large:
            addr_rule = (
                f"称呼锚:对方男 + 跨年龄段(差 ≥ 10 岁)— 用 @{nick_for_addr} 或'这位 / TA',"
                f"**不要**用'哥们儿 / 兄弟'(同辈感不合适)。"
            )
        else:
            addr_rule = (
                f"称呼锚:对方男 + 同龄 — 可以用'哥们儿 / 兄弟 / 这哥们儿',"
                f"也可以直接 @{nick_for_addr}。"
            )
    elif peer_gender == "female":
        if age_gap_large:
            addr_rule = (
                f"称呼锚:对方女 + 跨年龄段 — 用 @{nick_for_addr} 或'这位 / TA',"
                f"**禁用**'哥们儿 / 兄弟 / 老哥'(性别 + 同辈双重不合适);"
                f"'姐妹'也仅在你跟宿主同性别 + 同龄时才自然,默认走 @{nick_for_addr}。"
            )
        else:
            addr_rule = (
                f"称呼锚:对方女 — **禁用**'哥们儿 / 兄弟 / 老哥'(常见 AI 错误),"
                f"可以用'姐妹 / 这姑娘 / 这位'或直接 @{nick_for_addr}。"
            )
    elif peer_gender == "non_binary":
        addr_rule = (
            f"称呼锚:对方非二元 — 全程 @{nick_for_addr} 或'TA / 这位',"
            f"**禁用**带性别预设的称呼('哥们儿 / 姐妹 / 兄弟')。"
        )
    elif peer_gender == "prefer_not_to_say":
        addr_rule = (
            f"称呼锚:对方未透露性别 — 默认 @{nick_for_addr} 或'TA / 这位',"
            f"别擅自补'哥们儿 / 姐妹'之类的称呼。"
        )
    else:
        addr_rule = (
            f"称呼锚:对方信息不全 — 走 @{nick_for_addr} 或'这位'最稳。"
        )

    return f"对方简介:{info_line}\n{addr_rule}"
