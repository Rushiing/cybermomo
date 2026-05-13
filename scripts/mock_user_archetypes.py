"""
冷启动 mock 用户档案池 · 8 骨架 × 2-3 variant = 20 人

每个 archetype 是一对(demographic, base profile),variants 只改:
  - nickname
  - domains 的子细分(整体调性不动)
  - dialogue / boundary 数值小幅偏移(±15)

被 scripts/cold_start_seed.py 消费。也可以单独跑:
    python3 scripts/mock_user_archetypes.py   # 打印 20 人摘要

骨架表(跟 plan binary-prancing-candle.md 对齐):
  A 沉静观察者     25-30 / female  / INFJ — 慢热高披露 · 阅读+心理
  B 高能社交       25-30 / male    / ENFP — 主动追问 · 科技+音乐
  C 思想型独行     30-35 / male    / INTP — 冷面但深度 · 哲学+研究
  D 直率女将       35-40 / female  / ESTJ — 高效不绕弯 · 商业+健身
  E 边界感强       30-35 / non_binary / ISFP — 温和但难深聊 · 艺术+独处
  F 玩家青年       18-25 / male    / ESTP — 高能 + 即兴 · 游戏+夜生活
  G 中年沉淀       40+   / female  / ISFJ — 慢节奏 + 关怀 · 家庭+读书
  H 文艺学生       18-25 / female  / ENFJ — 共情型 · 写作+音乐

总 20 人:A×3, B×3, C×3, D×3, E×2, F×2, G×2, H×2
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ========================================
# Profile builder(参照 scripts/seed_demo_users.py)
# ========================================

_DEFAULT_QIDS = [
    "E1", "E3", "O3", "CMM1", "CMM2", "CMM3", "AU2", "AV3", "AX2", "AU1",
    "CON4", "CON2", "ES3", "ES2", "O4", "D1", "D2",
]


def _ra(idx: int) -> dict:
    return {"option_index": idx, "option_text": ""}


def _profile(
    *,
    domains_interested: list[str],
    domains_avoided: list[str],
    dialogue: dict,
    boundary: dict,
    reliability: dict,
    conflict: dict,
    exploration: dict,
    agency: dict,
    warmth: dict,
    support: dict,
    connection: dict,
    portrait_title: str,
    portrait_body: list[str],
    portrait_tags: list[str],
    raw_answer_idx: int = 2,
) -> dict:
    """构造一份完整的 ProfileV3 dict(可通过 /api/md schema 校验)"""
    return {
        "meta": {
            "version": "agent-social-portrait-17q-strong-combo",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "domains": {"interested": domains_interested, "avoided": domains_avoided},
        "raw_answers": {qid: _ra(raw_answer_idx) for qid in _DEFAULT_QIDS},
        "dialogue": dialogue,
        "relationship_warmth": {
            "warmth_initiation": warmth,
            "support_style": support,
            "connection_value": connection,
        },
        "boundary_and_closeness": boundary,
        "reliability": reliability,
        "conflict_repair": conflict,
        "exploration": exploration,
        "agency": agency,
        "portrait": {
            "title": portrait_title,
            "main_type": portrait_title.replace("你像是一个「", "").replace("」", ""),
            "title_reason": "mock seed · 合成档案",
            "core_tension": portrait_body[0] if portrait_body else "",
            "tags": portrait_tags,
            "body": portrait_body,
            "debug": {"strongest_features": [], "picked_combos": [], "title_reason": "mock"},
        },
    }


# ========================================
# warmth/support/connection 复用片段
# ========================================

_WARMTH = {
    "low": {"label": "低介入关心", "code": "low_intervention", "option_index": 1, "score": 0},
    "reserved": {"label": "留意但克制", "code": "attentive_reserved", "option_index": 2, "score": 33},
    "gentle": {"label": "轻触式关心", "code": "gentle_check_in", "option_index": 3, "score": 67},
    "high": {"label": "持续在场关心", "code": "high_presence", "option_index": 4, "score": 100},
}
_SUPPORT = {
    "problem": {"label": "问题理解型", "code": "problem_mapping", "option_index": 1},
    "need": {"label": "需求确认型", "code": "need_checking", "option_index": 2},
    "emotion": {"label": "情绪回应型", "code": "emotion_validating", "option_index": 3},
}
_CONNECTION = {
    "collab": {"label": "协作连接", "code": "collaborative_connection", "option_index": 1},
    "resonance": {"label": "共鸣连接", "code": "resonance_connection", "option_index": 2},
    "understand": {"label": "理解连接", "code": "mutual_understanding_connection", "option_index": 3},
}


def _shift(d: dict, delta: int) -> dict:
    """把 dict 里每个 numeric 值 +delta,clamp 到 [0,100]"""
    return {k: max(0, min(100, v + delta)) if isinstance(v, int) else v for k, v in d.items()}


# ========================================
# 20 个 mock 用户(8 骨架 × variant)
# ========================================

MOCK_USERS: list[dict[str, Any]] = []


# ---------- A 沉静观察者(female, INFJ, 25-30)× 3 ----------
_A_BASE = dict(
    age_band="25-30", gender="female", mbti="INFJ", archetype="A 沉静观察者",
    dialogue={"social_energy": 25, "sharing_drive": 78, "disagreement_exploration": 82},
    boundary={
        "interruption_sensitivity": 76, "arranged_decision_discomfort": 72,
        "closeness_density_pressure": 68, "coldness_sensitivity": 70,
    },
    reliability={"commitment_caution": 82, "notice_expectation": 80},
    conflict={"misunderstanding_regulation": 68, "emotional_recovery_speed": 35},
    exploration={"novelty_seeking": 55},
    agency={"task_initiation": 38, "decision_assertiveness": 60},
    warmth=_WARMTH["reserved"], support=_SUPPORT["problem"], connection=_CONNECTION["resonance"],
    portrait_title="你像是一个「不对所有人打开,但遇到同频会突然变亮的人」",
    portrait_body=[
        "你的社交入口不宽,但思考入口很深 — 聊点真东西你会忽然变得很想分享。",
        "你需要稳定回应感,但密度上来又会想后撤,要的是有呼吸感的靠近。",
    ],
    portrait_tags=["低频社交", "高分享欲", "观点探索", "共鸣连接"],
)
MOCK_USERS += [
    {**_A_BASE, "username": "mock_senyu_a1", "nickname": "森屿",
     "domains_interested": ["心理与人类观察", "文学写作", "AI与科技"],
     "domains_avoided": ["体育赛事", "时政公共议题"]},
    {**_A_BASE, "username": "mock_anjing_a2", "nickname": "安静",
     "domains_interested": ["心理与人类观察", "影视综艺", "教育学习"],
     "domains_avoided": ["游戏", "二次元动漫"]},
    {**_A_BASE, "username": "mock_mubai_a3", "nickname": "暮白",
     "domains_interested": ["文学写作", "历史社科", "设计审美"],
     "domains_avoided": ["体育赛事", "神秘学与命理"],
     "dialogue": _shift(_A_BASE["dialogue"], -5),
     "boundary": _shift(_A_BASE["boundary"], 5)},
]


# ---------- B 高能社交(male, ENFP, 25-30)× 3 ----------
_B_BASE = dict(
    age_band="25-30", gender="male", mbti="ENFP", archetype="B 高能社交",
    dialogue={"social_energy": 85, "sharing_drive": 82, "disagreement_exploration": 70},
    boundary={
        "interruption_sensitivity": 35, "arranged_decision_discomfort": 40,
        "closeness_density_pressure": 30, "coldness_sensitivity": 45,
    },
    reliability={"commitment_caution": 50, "notice_expectation": 55},
    conflict={"misunderstanding_regulation": 65, "emotional_recovery_speed": 75},
    exploration={"novelty_seeking": 88},
    agency={"task_initiation": 78, "decision_assertiveness": 68},
    warmth=_WARMTH["high"], support=_SUPPORT["need"], connection=_CONNECTION["collab"],
    portrait_title="你像是一个「能把陌生人也聊成熟人的人」",
    portrait_body=[
        "你的社交入口很宽,带话题、带能量,默认假设大家都愿意被你拉进来。",
        "你能接住别人但也容易过度供给 — 偶尔需要意识到对方在踩刹车。",
    ],
    portrait_tags=["高能量", "主动追问", "新体验趋近", "协作连接"],
)
MOCK_USERS += [
    {**_B_BASE, "username": "mock_yujizhe_b1", "nickname": "鱼骥者",
     "domains_interested": ["AI与科技", "音乐演出", "影视综艺", "游戏"],
     "domains_avoided": ["神秘学与命理"]},
    {**_B_BASE, "username": "mock_xiaozhou_b2", "nickname": "小舟",
     "domains_interested": ["AI与科技", "商业财经", "旅行城市"],
     "domains_avoided": ["神秘学与命理", "二次元动漫"],
     "dialogue": _shift(_B_BASE["dialogue"], -10)},
    {**_B_BASE, "username": "mock_lvlu_b3", "nickname": "绿陆",
     "domains_interested": ["音乐演出", "时尚形象", "二次元动漫"],
     "domains_avoided": ["时政公共议题"],
     "agency": _shift(_B_BASE["agency"], -10)},
]


# ---------- C 思想型独行(male, INTP, 30-35)× 3 ----------
_C_BASE = dict(
    age_band="30-35", gender="male", mbti="INTP", archetype="C 思想型独行",
    dialogue={"social_energy": 30, "sharing_drive": 50, "disagreement_exploration": 90},
    boundary={
        "interruption_sensitivity": 80, "arranged_decision_discomfort": 75,
        "closeness_density_pressure": 78, "coldness_sensitivity": 25,
    },
    reliability={"commitment_caution": 75, "notice_expectation": 60},
    conflict={"misunderstanding_regulation": 50, "emotional_recovery_speed": 40},
    exploration={"novelty_seeking": 50},
    agency={"task_initiation": 30, "decision_assertiveness": 80},
    warmth=_WARMTH["low"], support=_SUPPORT["problem"], connection=_CONNECTION["resonance"],
    portrait_title="你像是一个「不爱热闹但讨厌粗糙观点的人」",
    portrait_body=[
        "你不爱寒暄但愿意为有意思的论点投入很长时间。",
        "对方说不清就会失去耐心 — 你想要的是被精确理解的瞬间。",
    ],
    portrait_tags=["低社交能量", "深度探索", "观点优先", "低关怀展示"],
)
MOCK_USERS += [
    {**_C_BASE, "username": "mock_lengyan_c1", "nickname": "冷岩",
     "domains_interested": ["AI与科技", "历史社科", "心理与人类观察"],
     "domains_avoided": ["时尚形象", "音乐演出"]},
    {**_C_BASE, "username": "mock_qiyu_c2", "nickname": "栖渔",
     "domains_interested": ["商业财经", "教育学习", "历史社科"],
     "domains_avoided": ["二次元动漫", "时尚形象"],
     "dialogue": _shift(_C_BASE["dialogue"], 5),
     "boundary": _shift(_C_BASE["boundary"], -10)},
    {**_C_BASE, "username": "mock_xunfang_c3", "nickname": "寻方",
     "domains_interested": ["AI与科技", "时政公共议题", "心理与人类观察"],
     "domains_avoided": ["神秘学与命理", "游戏"]},
]


# ---------- D 直率女将(female, ESTJ, 35-40)× 3 ----------
_D_BASE = dict(
    age_band="35-40", gender="female", mbti="ESTJ", archetype="D 直率女将",
    dialogue={"social_energy": 65, "sharing_drive": 40, "disagreement_exploration": 75},
    boundary={
        "interruption_sensitivity": 30, "arranged_decision_discomfort": 25,
        "closeness_density_pressure": 35, "coldness_sensitivity": 30,
    },
    reliability={"commitment_caution": 55, "notice_expectation": 70},
    conflict={"misunderstanding_regulation": 70, "emotional_recovery_speed": 75},
    exploration={"novelty_seeking": 45},
    agency={"task_initiation": 88, "decision_assertiveness": 90},
    warmth=_WARMTH["low"], support=_SUPPORT["problem"], connection=_CONNECTION["collab"],
    portrait_title="你像是一个「不爱绕弯,事比关系先解决的人」",
    portrait_body=[
        "你判断快,落地干净,讨厌反复确认情绪还不办事的人。",
        "你的关心方式偏'我把事帮你搞定' — 不会刻意经营柔软感。",
    ],
    portrait_tags=["高推进", "判断有立场", "效率优先", "低情绪供给"],
)
MOCK_USERS += [
    {**_D_BASE, "username": "mock_huotie_d1", "nickname": "火铁",
     "domains_interested": ["商业财经", "健身运动", "教育学习"],
     "domains_avoided": ["神秘学与命理", "二次元动漫"]},
    {**_D_BASE, "username": "mock_lizhi_d2", "nickname": "立之",
     "domains_interested": ["商业财经", "时政公共议题", "旅行城市"],
     "domains_avoided": ["游戏", "二次元动漫"],
     "dialogue": _shift(_D_BASE["dialogue"], -10)},
    {**_D_BASE, "username": "mock_kuanjie_d3", "nickname": "宽姐",
     "domains_interested": ["健身运动", "家居美食", "商业财经"],
     "domains_avoided": ["神秘学与命理"],
     "agency": _shift(_D_BASE["agency"], -10)},
]


# ---------- E 边界感强(non_binary, ISFP, 30-35)× 2 ----------
_E_BASE = dict(
    age_band="30-35", gender="non_binary", mbti="ISFP", archetype="E 边界感强",
    dialogue={"social_energy": 35, "sharing_drive": 45, "disagreement_exploration": 35},
    boundary={
        "interruption_sensitivity": 90, "arranged_decision_discomfort": 85,
        "closeness_density_pressure": 88, "coldness_sensitivity": 65,
    },
    reliability={"commitment_caution": 80, "notice_expectation": 78},
    conflict={"misunderstanding_regulation": 60, "emotional_recovery_speed": 25},
    exploration={"novelty_seeking": 40},
    agency={"task_initiation": 35, "decision_assertiveness": 55},
    warmth=_WARMTH["gentle"], support=_SUPPORT["emotion"], connection=_CONNECTION["understand"],
    portrait_title="你像是一个「温和但需要被尊重边界的人」",
    portrait_body=[
        "你愿意靠近,但密度感很敏感 — 被催被推被默认参与会立刻退一步。",
        "你的善意是慢慢长出来的,不是一上来就给。",
    ],
    portrait_tags=["边界强", "慢热", "理解连接", "感受优先"],
)
MOCK_USERS += [
    {**_E_BASE, "username": "mock_anwei_e1", "nickname": "岸薇",
     "domains_interested": ["设计审美", "音乐演出", "生活方式"],
     "domains_avoided": ["体育赛事", "时政公共议题"]},
    {**_E_BASE, "username": "mock_lvqu_e2", "nickname": "绿曲",
     "domains_interested": ["设计审美", "文学写作", "影视综艺"],
     "domains_avoided": ["商业财经", "时政公共议题"],
     "dialogue": _shift(_E_BASE["dialogue"], 5)},
]


# ---------- F 玩家青年(male, ESTP, 18-25)× 2 ----------
_F_BASE = dict(
    age_band="18-25", gender="male", mbti="ESTP", archetype="F 玩家青年",
    dialogue={"social_energy": 90, "sharing_drive": 60, "disagreement_exploration": 50},
    boundary={
        "interruption_sensitivity": 20, "arranged_decision_discomfort": 25,
        "closeness_density_pressure": 30, "coldness_sensitivity": 30,
    },
    reliability={"commitment_caution": 35, "notice_expectation": 45},
    conflict={"misunderstanding_regulation": 50, "emotional_recovery_speed": 85},
    exploration={"novelty_seeking": 92},
    agency={"task_initiation": 75, "decision_assertiveness": 65},
    warmth=_WARMTH["high"], support=_SUPPORT["need"], connection=_CONNECTION["collab"],
    portrait_title="你像是一个「永远在线,玩起来就停不下来的人」",
    portrait_body=[
        "你节奏快、好奇心强,默认假设跟你玩就该上头。",
        "深一点的话题愿意聊但不会拖,聊不动就跳。",
    ],
    portrait_tags=["高能", "即兴", "新体验探索", "话题轻"],
)
MOCK_USERS += [
    {**_F_BASE, "username": "mock_xiaohu_f1", "nickname": "小虎",
     "domains_interested": ["游戏", "音乐演出", "健身运动", "二次元动漫"],
     "domains_avoided": ["时政公共议题"]},
    {**_F_BASE, "username": "mock_chongchong_f2", "nickname": "冲冲",
     "domains_interested": ["游戏", "影视综艺", "旅行城市"],
     "domains_avoided": ["历史社科", "时政公共议题"],
     "dialogue": _shift(_F_BASE["dialogue"], -5)},
]


# ---------- G 中年沉淀(female, ISFJ, 40+)× 2 ----------
_G_BASE = dict(
    age_band="40+", gender="female", mbti="ISFJ", archetype="G 中年沉淀",
    dialogue={"social_energy": 40, "sharing_drive": 55, "disagreement_exploration": 30},
    boundary={
        "interruption_sensitivity": 55, "arranged_decision_discomfort": 50,
        "closeness_density_pressure": 45, "coldness_sensitivity": 55,
    },
    reliability={"commitment_caution": 88, "notice_expectation": 85},
    conflict={"misunderstanding_regulation": 80, "emotional_recovery_speed": 55},
    exploration={"novelty_seeking": 30},
    agency={"task_initiation": 60, "decision_assertiveness": 55},
    warmth=_WARMTH["high"], support=_SUPPORT["emotion"], connection=_CONNECTION["understand"],
    portrait_title="你像是一个「慢节奏的依靠型陪伴者」",
    portrait_body=[
        "你的关心是稳定的、不张扬的,愿意把别人放在心里很久。",
        "节奏快、即兴的关系你不太适应,你要的是能慢慢积累的那种。",
    ],
    portrait_tags=["可靠", "持续关怀", "慢节奏", "理解连接"],
)
MOCK_USERS += [
    {**_G_BASE, "username": "mock_qiyue_g1", "nickname": "七月",
     "domains_interested": ["家居美食", "教育学习", "文学写作"],
     "domains_avoided": ["游戏", "二次元动漫"]},
    {**_G_BASE, "username": "mock_chengyu_g2", "nickname": "成屿",
     "domains_interested": ["生活方式", "情感关系", "影视综艺"],
     "domains_avoided": ["游戏", "二次元动漫"],
     "dialogue": _shift(_G_BASE["dialogue"], 5)},
]


# ---------- H 文艺学生(female, ENFJ, 18-25)× 2 ----------
_H_BASE = dict(
    age_band="18-25", gender="female", mbti="ENFJ", archetype="H 文艺学生",
    dialogue={"social_energy": 70, "sharing_drive": 85, "disagreement_exploration": 60},
    boundary={
        "interruption_sensitivity": 45, "arranged_decision_discomfort": 50,
        "closeness_density_pressure": 50, "coldness_sensitivity": 75,
    },
    reliability={"commitment_caution": 70, "notice_expectation": 78},
    conflict={"misunderstanding_regulation": 75, "emotional_recovery_speed": 60},
    exploration={"novelty_seeking": 70},
    agency={"task_initiation": 65, "decision_assertiveness": 58},
    warmth=_WARMTH["high"], support=_SUPPORT["emotion"], connection=_CONNECTION["resonance"],
    portrait_title="你像是一个「会被对方情绪带动也愿意主动给情绪的人」",
    portrait_body=[
        "你共情快、表达快,容易跟对方进入'我们都懂'的状态。",
        "但你也容易因为被忽视而消耗 — 想要被记住、被回应。",
    ],
    portrait_tags=["共情型", "高分享欲", "情绪敏感", "共鸣连接"],
)
MOCK_USERS += [
    {**_H_BASE, "username": "mock_xiyuan_h1", "nickname": "夕原",
     "domains_interested": ["文学写作", "音乐演出", "影视综艺"],
     "domains_avoided": ["体育赛事", "商业财经"]},
    {**_H_BASE, "username": "mock_lulu_h2", "nickname": "露露",
     "domains_interested": ["音乐演出", "时尚形象", "情感关系"],
     "domains_avoided": ["时政公共议题", "商业财经"],
     "dialogue": _shift(_H_BASE["dialogue"], -10)},
]


# ========================================
# 校验 + 导出
# ========================================

assert len(MOCK_USERS) == 20, f"expected 20 mock users, got {len(MOCK_USERS)}"
_usernames = [u["username"] for u in MOCK_USERS]
assert len(set(_usernames)) == 20, "duplicate username detected"
for u in MOCK_USERS:
    assert u["username"].startswith("mock_"), f"username must start with mock_: {u['username']}"
    for required in ("nickname", "age_band", "gender", "mbti",
                     "domains_interested", "domains_avoided",
                     "dialogue", "boundary", "reliability", "conflict",
                     "exploration", "agency", "warmth", "support", "connection",
                     "portrait_title", "portrait_body", "portrait_tags"):
        assert required in u, f"{u['username']} missing {required}"


def build_profile_for(user_spec: dict) -> dict:
    """从 MOCK_USERS 里的一个 dict 构造完整 ProfileV3"""
    return _profile(
        domains_interested=user_spec["domains_interested"],
        domains_avoided=user_spec["domains_avoided"],
        dialogue=user_spec["dialogue"],
        boundary=user_spec["boundary"],
        reliability=user_spec["reliability"],
        conflict=user_spec["conflict"],
        exploration=user_spec["exploration"],
        agency=user_spec["agency"],
        warmth=user_spec["warmth"],
        support=user_spec["support"],
        connection=user_spec["connection"],
        portrait_title=user_spec["portrait_title"],
        portrait_body=user_spec["portrait_body"],
        portrait_tags=user_spec["portrait_tags"],
    )


if __name__ == "__main__":
    # 跑这个文件:打印 20 人摘要 + 校验 profile 能构造
    print(f"mock users: {len(MOCK_USERS)}\n")
    archetype_count: dict[str, int] = {}
    for u in MOCK_USERS:
        archetype_count[u["archetype"]] = archetype_count.get(u["archetype"], 0) + 1
        print(f"  {u['username']:<24} {u['nickname']:<6} "
              f"{u['age_band']:<6} {u['gender']:<14} {u['mbti']:<5} "
              f"· {u['archetype']}")
    print("\narchetype 分布:")
    for k, v in archetype_count.items():
        print(f"  {k}: {v}")

    # 抽一个构造 profile 试试
    print("\n第一人完整 profile (head):")
    import json
    p = build_profile_for(MOCK_USERS[0])
    print(json.dumps({
        "domains": p["domains"],
        "dialogue": p["dialogue"],
        "portrait_title": p["portrait"]["title"],
    }, ensure_ascii=False, indent=2))
