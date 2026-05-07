"""
v3 profile JSON 的 Pydantic schema

完全镜像 `/Users/xihe/Desktop/人格画像问卷_v3.html` 里的 build() 函数产出。
后端只负责 schema 校验 + 入库,不重新计算(规则引擎跑在前端)。

输入:前端 POST 完整 profile_json(从 v3 HTML 跑出来的)
输出:同结构 + DB id / version / created_at
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ========================================
# v3 题库已知的领域(必须跟 v3 HTML 的 AREAS 数组一致)
# ========================================
ALLOWED_DOMAINS = {
    "AI与科技", "心理与人类观察", "商业财经", "设计审美", "时尚形象",
    "文学写作", "影视综艺", "音乐演出", "游戏", "二次元动漫",
    "健身运动", "体育赛事", "历史社科", "时政公共议题", "旅行城市",
    "生活方式", "家居美食", "教育学习", "情感关系", "神秘学与命理",
    "其他",
}


# ========================================
# 子结构
# ========================================

class ProfileMeta(BaseModel):
    version: str  # 例:"agent-social-portrait-17q-strong-combo"
    generated_at: str  # ISO8601


class ProfileDomains(BaseModel):
    interested: list[str]
    avoided: list[str]


class TaggedDimension(BaseModel):
    """tag 型维度(CMM1 / CMM2 / CMM3)"""
    label: str
    code: str
    option_index: int = Field(ge=1)
    score: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileDialogue(BaseModel):
    """对话维度(0-100,允许 None 表示未答)"""
    social_energy: Optional[int] = Field(default=None, ge=0, le=100)
    sharing_drive: Optional[int] = Field(default=None, ge=0, le=100)
    disagreement_exploration: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileRelationshipWarmth(BaseModel):
    warmth_initiation: TaggedDimension
    support_style: TaggedDimension
    connection_value: TaggedDimension


class ProfileBoundary(BaseModel):
    interruption_sensitivity: Optional[int] = Field(default=None, ge=0, le=100)
    arranged_decision_discomfort: Optional[int] = Field(default=None, ge=0, le=100)
    closeness_density_pressure: Optional[int] = Field(default=None, ge=0, le=100)
    coldness_sensitivity: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileReliability(BaseModel):
    commitment_caution: Optional[int] = Field(default=None, ge=0, le=100)
    notice_expectation: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileConflictRepair(BaseModel):
    misunderstanding_regulation: Optional[int] = Field(default=None, ge=0, le=100)
    emotional_recovery_speed: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileExploration(BaseModel):
    novelty_seeking: Optional[int] = Field(default=None, ge=0, le=100)


class ProfileAgency(BaseModel):
    task_initiation: Optional[int] = Field(default=None, ge=0, le=100)
    decision_assertiveness: Optional[int] = Field(default=None, ge=0, le=100)


class ProfilePortrait(BaseModel):
    """生成的人格画像 — 文段 + 标题 + 标签 + debug"""
    title: str
    main_type: str
    title_reason: str
    core_tension: str
    tags: list[str]
    body: list[str]
    debug: dict[str, Any] = Field(default_factory=dict)


class RawAnswer(BaseModel):
    option_index: Optional[int] = None
    option_text: Optional[str] = None


# ========================================
# 顶层 profile schema
# ========================================

class ProfileV3(BaseModel):
    """v3 完整 profile JSON · 入库前的校验形态"""
    model_config = ConfigDict(extra="forbid")

    meta: ProfileMeta
    domains: ProfileDomains
    raw_answers: dict[str, RawAnswer]
    dialogue: ProfileDialogue
    relationship_warmth: ProfileRelationshipWarmth
    boundary_and_closeness: ProfileBoundary
    reliability: ProfileReliability
    conflict_repair: ProfileConflictRepair
    exploration: ProfileExploration
    agency: ProfileAgency
    portrait: ProfilePortrait


# ========================================
# API request / response wrappers
# ========================================

class CreateMdRequest(BaseModel):
    """POST /api/md 请求体"""
    profile: ProfileV3
    # nickname / age_band / gender / mbti / avatar_url 走单独的 user_profile 流程
    # 这里只接收 profile 主体


class MdDocumentResponse(BaseModel):
    """GET / POST /api/md / /api/me/md 响应体"""
    id: int
    user_id: int
    version: int
    profile_version: str
    domains_interested: list[str]
    domains_avoided: list[str]
    portrait_title: str
    portrait_body: list[str]  # portrait.body 段落(简化展示)
    is_active: bool
    created_at: datetime
