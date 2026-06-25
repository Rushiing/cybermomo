"""
Pydantic Settings · 从环境变量读取配置
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库
    database_url: str = Field(
        default="postgresql+asyncpg://cybermomo:cybermomo_dev@localhost:5432/cybermomo"
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_pg_url(cls, v: str) -> str:
        """
        Railway Postgres 插件注入的格式是 postgres://...,SQLAlchemy + asyncpg 需要 postgresql+asyncpg://...
        统一兼容三种写法。
        """
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # CORS
    cors_origins: str = Field(default="http://localhost:3000")

    # Auth · Session
    jwt_secret: str = Field(default="dev-jwt-secret-not-for-prod-replace-me")
    # session cookie 名字 + 有效期(秒,默认 30 天)
    session_cookie_name: str = Field(default="cm_session")
    session_max_age: int = Field(default=30 * 24 * 3600)

    # X-Mock-User-Id 越权 fallback 的独立开关(audit P0-3)。
    # 默认 None → 跟随 is_dev(dev 开、prod 关);可显式设 false 即使在 dev 也强制关。
    # 不让 mock-auth 搭 is_dev 便车,多一道保险。
    enable_mock_auth: bool | None = Field(default=None)

    # Auth · Google OAuth
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    # OAuth 回调地址(完整 URL)— 跟 Google Console 配置一致
    # 例:https://cybermomo-production.up.railway.app/api/auth/google/callback
    google_oauth_redirect_uri: str = Field(default="")

    # 前端域名(callback 完跳回这里 /room)
    web_base_url: str = Field(default="http://localhost:3000")

    # LLM
    # 测试期:统一走 百炼(DashScope)OpenAI-compatible 端点
    # base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
    # 默认模型:deepseek-v4-flash(可被 LLM_MODEL 覆盖)
    dashscope_api_key: str = Field(default="")
    llm_model: str = Field(default="deepseek-v4-flash")

    # 兼容老变量(GLM_API_KEY 是 dashscope 的同一个 key,允许沿用)
    glm_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")  # 备用,测试期不需要
    zhipu_api_key: str = Field(default="")

    # Sentry
    sentry_dsn: str = Field(default="")

    # Admin(外部 cron 调用 sweep endpoint 时用)
    admin_secret: str = Field(default="")

    # 环境
    env: str = Field(default="dev")  # dev / staging / prod

    @property
    def cors_origins_list(self) -> List[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def mock_auth_enabled(self) -> bool:
        """X-Mock-User-Id fallback 是否启用。

        codex review 抓的 P0-b:非 dev **永远关**,不给任何 env 开关机会
        (即使误设 ENABLE_MOCK_AUTH=true 也不生效)。dev 下显式 enable_mock_auth
        优先,否则默认开(本地联调)。配合 Dockerfile 烤进 ENV=prod,部署镜像
        ENV 丢失时仍是 prod → 这里返 False → 无越权 fallback。
        """
        if not self.is_dev:
            return False
        if self.enable_mock_auth is not None:
            return self.enable_mock_auth
        return True

    @property
    def effective_dashscope_key(self) -> str:
        """优先 DASHSCOPE_API_KEY,fallback 到 GLM_API_KEY(同一 key 不同名)"""
        return self.dashscope_api_key or self.glm_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
