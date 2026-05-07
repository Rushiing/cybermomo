"""
03 · 匹配引擎 · 算法核心

输入:两个用户的 v3 profile_json
输出:overall_score(0..1) + 一组 matchpoints

混合方案(算法骨架 v0):
1. **维度数学距离**(主):14 个 0-100 维度 + 3 个 tag 维度
2. **领域 overlap**(辅):interested overlap + cross interested-avoided 惩罚
3. **wildcard**:由上层调度器决定,本模块只算 score / matchpoints

不依赖 LLM,纯计算。MVP 跑得动也可解释。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

# ========================================
# 维度抽取
# ========================================

# 14 个数字维度的 (path, key, weight)
DIMENSIONS: list[tuple[list[str], str, float]] = [
    (["dialogue", "social_energy"], "social_energy", 1.0),
    (["dialogue", "sharing_drive"], "sharing_drive", 1.0),
    (["dialogue", "disagreement_exploration"], "disagreement_exploration", 1.0),
    (["boundary_and_closeness", "interruption_sensitivity"], "interruption_sensitivity", 1.2),
    (["boundary_and_closeness", "arranged_decision_discomfort"], "arranged_decision_discomfort", 1.0),
    (["boundary_and_closeness", "closeness_density_pressure"], "closeness_density_pressure", 1.2),
    (["boundary_and_closeness", "coldness_sensitivity"], "coldness_sensitivity", 1.0),
    (["reliability", "commitment_caution"], "commitment_caution", 0.8),
    (["reliability", "notice_expectation"], "notice_expectation", 0.8),
    (["conflict_repair", "misunderstanding_regulation"], "misunderstanding_regulation", 1.0),
    (["conflict_repair", "emotional_recovery_speed"], "emotional_recovery_speed", 0.8),
    (["exploration", "novelty_seeking"], "novelty_seeking", 0.8),
    (["agency", "task_initiation"], "task_initiation", 0.8),
    (["agency", "decision_assertiveness"], "decision_assertiveness", 0.8),
]

# 3 个 tag 维度的 (path, code_field, weight, score_field)
TAG_DIMENSIONS: list[tuple[list[str], str, float]] = [
    (["relationship_warmth", "warmth_initiation"], "warmth_initiation", 1.0),
    (["relationship_warmth", "support_style"], "support_style", 1.0),
    (["relationship_warmth", "connection_value"], "connection_value", 1.4),  # 用户最珍惜的连接型,权重高
]


def _get_path(d: dict, path: list[str]) -> Any:
    cur: Any = d
    for k in path:
        if cur is None or not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _safe_dim(profile: dict, path: list[str], default: float = 50.0) -> float:
    """从 profile 取一个 0-100 维度;None 时回中点 50。"""
    v = _get_path(profile, path)
    if v is None:
        return default
    return float(v)


# ========================================
# 主算法
# ========================================

@dataclass
class MatchpointDraft:
    """matchpoint 的 schema-shaped 草稿(尚未入库)"""
    category: str  # 兴趣 / 价值观 / 生活方式 / 性格 / 经历 / 其他
    match_type: str  # 同类共鸣 / 互补吸引
    similarity: float  # 0..1
    weight: float  # 0..1
    a_source_segments: list[str]  # 引用的 v3 path,如 ["dialogue.social_energy"]
    b_source_segments: list[str]
    explain: str  # 内部说明,不入库,用于 hook 文案 / 日志


@dataclass
class MatchScore:
    """单对 (A, B) 的匹配产物"""
    overall_score: float  # 0..1
    matchpoints: list[MatchpointDraft] = field(default_factory=list)


# 维度→人类可读名(用于 explain)
_DIM_LABELS = {
    "social_energy": "社交能量",
    "sharing_drive": "分享欲",
    "disagreement_exploration": "观点探索",
    "interruption_sensitivity": "节奏敏感",
    "arranged_decision_discomfort": "自主感",
    "closeness_density_pressure": "亲密压力",
    "coldness_sensitivity": "关系温差敏感",
    "commitment_caution": "承诺谨慎",
    "notice_expectation": "重视提前说明",
    "misunderstanding_regulation": "误解时调节",
    "emotional_recovery_speed": "情绪恢复速度",
    "novelty_seeking": "新体验趋近",
    "task_initiation": "推进局面",
    "decision_assertiveness": "判断坚持",
}

_TAG_LABEL_TO_HUMAN = {
    "low_intervention": "低介入关心", "attentive_reserved": "留意但克制",
    "gentle_check_in": "轻触式关心", "active_warmth": "明确陪伴型",
    "problem_mapping": "问题理解型", "need_checking": "需求确认型",
    "emotional_holding": "情绪承接型",
    "collaborative_connection": "协作连接", "resonance_connection": "共鸣连接",
    "mutual_understanding_connection": "理解连接", "companionship_connection": "陪伴连接",
}


def compute_match(a_profile: dict, b_profile: dict) -> MatchScore:
    """
    给定两份 v3 profile_json,产出 overall_score + matchpoints。

    打分思路:
    - 14 维数字:每维计算 |a-b|/100,转 sim = 1 - dist
    - 3 tag 维:同 code = sim 1.0,跨 code = 0.3-0.6 取决于配对(连接型尤其重要)
    - 领域 overlap 加分,跨惩罚减分
    - 求加权和

    matchpoints 抽取:
    - 数字维度高度相似(sim ≥ 0.85,差 ≤ 15) → 同类共鸣
    - 数字维度互补对(差 ≥ 50,且对位)→ 互补吸引(只挑特定 pair)
    - tag 同 code → 同类共鸣
    - 共同 interested 领域 → 同类共鸣(category=兴趣)
    """
    matchpoints: list[MatchpointDraft] = []
    dim_sim_total = 0.0
    weight_total = 0.0

    # 数字维度
    for path, key, weight in DIMENSIONS:
        a_v = _safe_dim(a_profile, path)
        b_v = _safe_dim(b_profile, path)
        diff = abs(a_v - b_v)
        sim = 1.0 - (diff / 100.0)
        dim_sim_total += sim * weight
        weight_total += weight

        # 同类共鸣 matchpoint:差≤15 且 |中点偏离|≥15(俩人都在某极端附近)
        if diff <= 15 and abs(a_v - 50) >= 15:
            polarity = "高" if a_v > 60 else "低" if a_v < 40 else "中"
            matchpoints.append(MatchpointDraft(
                category="性格",
                match_type="同类共鸣",
                similarity=round(sim, 4),
                weight=round(min(1.0, weight * 0.5 + abs(a_v - 50) / 100), 4),
                a_source_segments=[".".join(path)],
                b_source_segments=[".".join(path)],
                explain=f"{_DIM_LABELS[key]} · 都偏{polarity}({a_v:.0f} / {b_v:.0f})",
            ))

    # 互补吸引 matchpoints(只在特定可成对的维度上挑)
    # task_initiation 互补 + decision_assertiveness 互补:一个推进、一个跟随,组队稳
    a_ti = _safe_dim(a_profile, ["agency", "task_initiation"])
    b_ti = _safe_dim(b_profile, ["agency", "task_initiation"])
    if abs(a_ti - b_ti) >= 50:
        matchpoints.append(MatchpointDraft(
            category="性格",
            match_type="互补吸引",
            similarity=0.5,  # 不是相似而是互补
            weight=0.5,
            a_source_segments=["agency.task_initiation"],
            b_source_segments=["agency.task_initiation"],
            explain="一个会推进局面、一个不抢主导,搭起来不会僵",
        ))

    # tag 维度
    tag_sim_total = 0.0
    tag_weight_total = 0.0
    for path, key, weight in TAG_DIMENSIONS:
        a_tag = _get_path(a_profile, path) or {}
        b_tag = _get_path(b_profile, path) or {}
        a_code = a_tag.get("code")
        b_code = b_tag.get("code")
        if not a_code or not b_code:
            continue
        if a_code == b_code:
            sim = 1.0
            tag_sim_total += sim * weight
            tag_weight_total += weight
            label = _TAG_LABEL_TO_HUMAN.get(a_code, a_code)
            matchpoints.append(MatchpointDraft(
                category="价值观" if "connection" in a_code else "生活方式",
                match_type="同类共鸣",
                similarity=1.0,
                weight=round(weight * 0.5, 4),
                a_source_segments=[".".join(path) + ".code"],
                b_source_segments=[".".join(path) + ".code"],
                explain=f"{label} · 同类",
            ))
        else:
            # 跨 code 给个中间分(具体配对将来可调)
            sim = 0.4
            tag_sim_total += sim * weight
            tag_weight_total += weight

    # 领域 overlap
    a_int = set(_get_path(a_profile, ["domains", "interested"]) or [])
    b_int = set(_get_path(b_profile, ["domains", "interested"]) or [])
    a_avd = set(_get_path(a_profile, ["domains", "avoided"]) or [])
    b_avd = set(_get_path(b_profile, ["domains", "avoided"]) or [])

    common_int = a_int & b_int
    cross_penalty_count = len(a_int & b_avd) + len(b_int & a_avd)

    domain_score = 0.0
    if common_int:
        # 共同兴趣:max 0.3 加分(每个 +0.05,封顶 6 个)
        domain_score += min(0.3, len(common_int) * 0.05)
        for d in list(common_int)[:5]:  # 最多 5 个 matchpoint
            matchpoints.append(MatchpointDraft(
                category="兴趣",
                match_type="同类共鸣",
                similarity=1.0,
                weight=0.4,
                a_source_segments=[f"domains.interested[{d}]"],
                b_source_segments=[f"domains.interested[{d}]"],
                explain=f"都对 {d} 感兴趣",
            ))
    # 跨兴趣 / 跨厌恶:每个 -0.06,封顶 -0.3
    domain_score -= min(0.3, cross_penalty_count * 0.06)

    # 总分
    dim_score = (dim_sim_total / weight_total) if weight_total else 0.5
    tag_score = (tag_sim_total / tag_weight_total) if tag_weight_total else 0.5
    # 加权:维度 60%、tag 30%、领域 10%
    overall = dim_score * 0.6 + tag_score * 0.3 + 0.5 * 0.1
    overall += domain_score * 0.10  # domain_score 范围 [-0.3, 0.3] → [±0.03] 调整
    overall = max(0.0, min(1.0, overall))

    return MatchScore(overall_score=round(overall, 4), matchpoints=matchpoints)


# ========================================
# 候选挑选 + wildcard 注入
# ========================================

@dataclass
class CandidateResult:
    user_b_id: int
    score: MatchScore
    is_wildcard: bool


def select_candidates(
    user_a_id: int,
    user_a_profile: dict,
    candidate_pool: list[tuple[int, dict]],  # [(user_b_id, b_profile), ...]
    *,
    top_k: int = 5,
    wildcard_ratio: float = 0.10,
    min_overall_score: float = 0.4,
    soft_blocked: Optional[set[int]] = None,
    rand: Optional[random.Random] = None,
) -> list[CandidateResult]:
    """
    在候选池里跑匹配,挑 top_k。10% 概率注入一个 wildcard(score < min 但有 matchpoints)。

    soft_blocked:user_a 的软拉黑名单,这些 id 全过滤(包括 wildcard)。
    """
    rand = rand or random.Random()
    blocked = soft_blocked or set()

    scored: list[tuple[int, MatchScore]] = []
    for b_id, b_profile in candidate_pool:
        if b_id == user_a_id or b_id in blocked:
            continue
        scored.append((b_id, compute_match(user_a_profile, b_profile)))

    # 排序
    scored.sort(key=lambda x: -x[1].overall_score)

    main_pool = [s for s in scored if s[1].overall_score >= min_overall_score]
    main = [
        CandidateResult(user_b_id=b_id, score=score, is_wildcard=False)
        for b_id, score in main_pool[:top_k]
    ]

    # wildcard:从分数低区间但有 matchpoint 的池子里挑
    if rand.random() < wildcard_ratio:
        chosen_ids = {c.user_b_id for c in main}
        wild_pool = [
            (b_id, score) for b_id, score in scored
            if b_id not in chosen_ids
            and score.overall_score < min_overall_score
            and len(score.matchpoints) >= 1
        ]
        if wild_pool:
            b_id, score = rand.choice(wild_pool)
            main.append(CandidateResult(user_b_id=b_id, score=score, is_wildcard=True))

    return main
