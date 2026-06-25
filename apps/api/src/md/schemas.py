"""
v3 profile JSON 的 Pydantic schema

完全镜像 `/Users/xihe/Desktop/人格画像问卷_v3.html` 里的 build() 函数产出。
后端只负责 schema 校验 + 入库,不重新计算(规则引擎跑在前端)。

输入:前端 POST 完整 profile_json(从 v3 HTML 跑出来的)
输出:同结构 + DB id / version / created_at
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    """
    兴趣 / 回避领域。**必须是 ALLOWED_DOMAINS 闭集**(audit P0-1a):
    domains 会进 desensitize prompt 并影响匹配,客户端塞自由文本 = 注入 / .md 外泄面。
    """
    interested: list[str] = Field(max_length=21)
    avoided: list[str] = Field(max_length=21)

    @field_validator("interested", "avoided")
    @classmethod
    def _only_allowed_domains(cls, v: list[str]) -> list[str]:
        bad = [d for d in v if d not in ALLOWED_DOMAINS]
        if bad:
            raise ValueError(f"非法领域(不在 ALLOWED_DOMAINS):{bad}")
        return v


class TaggedDimension(BaseModel):
    """tag 型维度(CMM1 / CMM2 / CMM3)"""
    # label/code 会进 desensitize 的 "safe summary" prompt,加长度上限防注入(audit P0-1a/P1-11)
    label: str = Field(max_length=40)
    code: str = Field(max_length=64)
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
    """生成的人格画像 — 文段 + 标题 + 标签 + debug

    自由文本字段全部加长度/数量上限(audit P0-1a/P1-11):portrait 会进 agent_chat
    speaker prompt,无上限时可被塞进 .md 原文 / 联系方式 / prompt 注入。
    debug 是规则引擎中间产物,不进 LLM(_summarize 会剥),也限制大小防 DB 膨胀。
    """
    title: str = Field(max_length=100)
    main_type: str = Field(max_length=100)
    title_reason: str = Field(max_length=600)
    core_tension: str = Field(max_length=600)
    tags: list[str] = Field(default_factory=list, max_length=16)
    body: list[str] = Field(default_factory=list, max_length=12)
    debug: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def _cap_tag_len(cls, v: list[str]) -> list[str]:
        for t in v:
            if len(t) > 40:
                raise ValueError("单个 tag 过长(>40)")
        return v

    @field_validator("body")
    @classmethod
    def _cap_body_len(cls, v: list[str]) -> list[str]:
        for p in v:
            if len(p) > 800:
                raise ValueError("单段 portrait body 过长(>800)")
        return v


class RawAnswer(BaseModel):
    option_index: Optional[int] = None
    # 问卷选项文本,加上限防塞 payload(audit P1-11)
    option_text: Optional[str] = Field(default=None, max_length=500)


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
