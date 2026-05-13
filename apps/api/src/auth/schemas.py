"""
01 · 用户注册 · API 输入输出 schema
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# avatar_url 接受两种形态:
#   1. 普通 http(s) 链接(Google 头像 / 外部 CDN)— 短
#   2. data:image/... base64 内嵌(用户本地上传 + 客户端压缩后)— 长
# 200KB 上限对 256×256 JPEG quality=0.85 留足空间(实际 ~50-80KB)
_AVATAR_MAX_LEN = 200_000


class UserProfilePayload(BaseModel):
    """user_profiles 可写字段"""
    nickname: str = Field(min_length=1, max_length=20)
    age_band: Optional[Literal["18-25", "25-30", "30-35", "35-40", "40+"]] = None
    gender: Optional[Literal["male", "female", "non_binary", "prefer_not_to_say"]] = None
    mbti: Optional[str] = Field(default=None, max_length=8)
    avatar_url: Optional[str] = Field(default=None, max_length=_AVATAR_MAX_LEN)

    @field_validator("avatar_url")
    @classmethod
    def _validate_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        # 必须是 http(s) 链接或 data:image/ 内嵌
        if v.startswith(("http://", "https://")):
            return v
        if v.startswith("data:image/"):
            # 粗校验 data URL 格式:data:image/<type>;base64,<payload>
            head, _, payload = v.partition(",")
            if ";base64" not in head or not payload:
                raise ValueError("data URL 格式不对,必须是 data:image/...;base64,<payload>")
            return v
        raise ValueError("avatar_url 必须是 http(s) 链接或 data:image/... base64 内嵌")


class UpsertProfileRequest(BaseModel):
    profile: UserProfilePayload


class UserMeResponse(BaseModel):
    """GET /api/auth/me 响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: Optional[str] = None  # 现在可空(密码注册可选填)
    username: Optional[str] = None  # 密码用户的登录 id
    google_name: Optional[str] = None
    google_avatar_url: Optional[str] = None  # OAuth 拿到的头像 URL,前端"用 Google 头像"按钮源
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
