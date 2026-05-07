"""
01 · 用户注册 · API 输入输出 schema
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserProfilePayload(BaseModel):
    """user_profiles 可写字段"""
    nickname: str = Field(min_length=1, max_length=20)
    age_band: Optional[Literal["18-25", "25-30", "30-35", "35-40", "40+"]] = None
    gender: Optional[Literal["male", "female", "non_binary", "prefer_not_to_say"]] = None
    mbti: Optional[str] = Field(default=None, max_length=8)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class UpsertProfileRequest(BaseModel):
    profile: UserProfilePayload


class UserMeResponse(BaseModel):
    """GET /api/auth/me 响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    google_name: Optional[str] = None
    is_adult_confirmed: bool
    onboarded_at: Optional[datetime] = None
    created_at: datetime
    profile: Optional[UserProfilePayload] = None
