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

    # Auth
    jwt_secret: str = Field(default="dev-jwt-secret-not-for-prod-replace-me")
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")

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
    def effective_dashscope_key(self) -> str:
        """优先 DASHSCOPE_API_KEY,fallback 到 GLM_API_KEY(同一 key 不同名)"""
        return self.dashscope_api_key or self.glm_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
