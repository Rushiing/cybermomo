"""
Pydantic Settings · 从环境变量读取配置
"""
from functools import lru_cache
from typing import List

from pydantic import Field
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

    # CORS
    cors_origins: str = Field(default="http://localhost:3000")

    # Auth
    jwt_secret: str = Field(default="dev-jwt-secret-not-for-prod-replace-me")
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")

    # LLM
    glm_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    zhipu_api_key: str = Field(default="")

    # Sentry
    sentry_dsn: str = Field(default="")

    # 环境
    env: str = Field(default="dev")  # dev / staging / prod

    @property
    def cors_origins_list(self) -> List[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
