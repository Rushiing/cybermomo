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
    email: Optional[str] = None  # 现在可空(密码注册可选填)
    username: Optional[str] = None  # 密码用户的登录 id
    google_name: Optional[str] = None
    is_adult_confirmed: bool
    onboarded_at: Optional[datetime] = None
    created_at: datetime
    profile: Optional[UserProfilePayload] = None


class RegisterRequest(BaseModel):
    """POST /api/auth/register · 用户名 + 密码注册(邮箱选填,不验证)"""
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=100)
    email: Optional[str] = Field(default=None, max_length=200)
    nickname: Optional[str] = Field(default=None, min_length=1, max_length=20)


class LoginRequest(BaseModel):
    """POST /api/auth/login"""
    username: str = Field(min_length=3, max_length=20)
    password: str = Field(min_length=1, max_length=100)
