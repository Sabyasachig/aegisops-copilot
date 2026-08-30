from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import LLMProvider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIOPS_", env_file=".env", extra="ignore")

    app_name: str = "AegisOps Copilot API"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 4001
    log_format: Literal["auto", "console", "json"] = "auto"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    llm_provider: LLMProvider = "groq"
    llm_model: str = "llama-3.1-8b-instant"
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    langsmith_api_key: str | None = None
    langsmith_project: str = "aegisops-copilot"
    langsmith_tracing: bool = True
    database_url: str = "postgresql+asyncpg://aegisops:aegisops@localhost:5432/aegisops"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    # JWT settings
    jwt_secret_key: str = "dev-secret-change-in-production-aegisops-copilot-jwt-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    # Initial admin credentials (override via env in production)
    initial_admin_username: str = "admin"
    initial_admin_password: str = "changeme"
    # Webhook HMAC secret — set to enable signature verification on all webhook endpoints
    webhook_secret: str | None = None
    # Rate limiting — slowapi / limits format: "<count>/<period>"
    # period examples: second, minute, hour, day
    rate_limit_storage_uri: str = "redis://localhost:6379/3"
    rate_limit_execute_ip: str = "10/minute"    # per client IP on the execute endpoint
    rate_limit_execute_user: str = "20/minute"  # per authenticated user on the execute endpoint


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
