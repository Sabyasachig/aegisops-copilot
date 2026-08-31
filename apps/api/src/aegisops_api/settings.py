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
    # SSE stream tuning
    sse_keepalive_seconds: int = 15
    sse_stream_poll_seconds: int = 1
    # OpenTelemetry tracing
    tracing_enabled: bool = False
    otel_service_name: str = "aegisops-api"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"
    otel_excluded_urls: str = "/api/health,/metrics"
    # Circuit breaker for LLM providers
    llm_circuit_failure_threshold: int = 3
    llm_circuit_recovery_seconds: int = 30
    llm_circuit_retry_attempts: int = 2
    # Human-in-the-loop approval gate
    approval_timeout_seconds: int = 300
    llm_fallback_chain: list[str] = Field(
        default_factory=lambda: ["groq", "openai", "anthropic"]
    )
    # Tool integrations — all optional; tools fall back to dry-run when unset
    k8s_enabled: bool = False
    datadog_api_key: str | None = None
    datadog_app_key: str | None = None
    datadog_site: str = "datadoghq.com"
    slack_webhook_url: str | None = None
    slack_default_channel: str = "#incidents"
    jira_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str | None = None
    # Agent memory / RAG (pgvector)
    memory_enabled: bool = False
    memory_embedding_model: str = "text-embedding-3-small"
    memory_embedding_dim: int = 1536
    memory_top_k: int = 3
    # Runbook knowledge base — if set, .md files in this dir are ingested on startup
    runbook_dir: str | None = None
    # Confidence scoring — runs with LLM confidence below threshold escalate to human
    confidence_threshold: float = 0.6


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
