"""
Aegis — Core Configuration and Settings Management

Loads and validates environment configuration using Pydantic Settings.
Adheres strictly to the .env.example contract and externalizes all secrets.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """System-wide application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment & Logging
    environment: str = Field(
        default="development", description="Environment mode: development | staging | production"
    )
    log_level: str = Field(default="INFO", description="Logging verbosity level")

    # Security
    secret_key: str = Field(
        default="replace-with-a-secure-random-secret-key-at-least-32-chars",
        description="Application secret key for auth tokens and crypto",
    )
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated CORS allowed origins",
    )

    # API Server
    api_host: str = Field(default="0.0.0.0", description="FastAPI host binding")
    api_port: int = Field(default=8000, description="FastAPI port binding")

    # Database (PostgreSQL + pgvector)
    postgres_user: str = Field(default="aegis_user")
    postgres_password: str = Field(default="aegis_password")
    postgres_db: str = Field(default="aegis_db")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    database_url: str = Field(
        default="postgresql+asyncpg://aegis_user:aegis_password@localhost:5432/aegis_db",
        description="Async database connection URL",
    )
    database_sync_url: str = Field(
        default="postgresql://aegis_user:aegis_password@localhost:5432/aegis_db",
        description="Synchronous database connection URL for Alembic and Celery tasks",
    )

    # Redis & Celery
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")

    # Embeddings & LLM
    embedding_model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)
    ollama_base_url: str = Field(default="http://localhost:11434")
    default_llm_model: str = Field(default="gemma2:2b")
    fallback_llm_model: str = Field(default="qwen2.5:3b")

    # Notifications
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="example_sender@gmail.com")
    smtp_password: str = Field(default="replace-with-app-password")
    smtp_from_email: str = Field(default="aegis-alerts@example.com")
    smtp_use_tls: bool = Field(default=True)
    use_fake_email_backend: bool = Field(default=True)

    telegram_bot_token: str | None = Field(default=None)
    telegram_bot_enabled: bool = Field(default=False)

    # Self-Healing & Repair Guardrails
    aegis_repair_enabled: bool = Field(default=True)
    # MUST DEFAULT TO FALSE per Build Directive Section 2.1 & Phase 7
    aegis_auto_promote_repairs: bool = Field(default=False)
    repair_max_diff_lines: int = Field(default=200)
    repair_sandbox_timeout_seconds: int = Field(default=120)

    # SSRF Hardening Blocklists
    ssrf_blocked_hosts: str = Field(
        default="localhost,127.0.0.1,::1,169.254.169.254,metadata.google.internal"
    )
    ssrf_blocked_cidrs: str = Field(default="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")

    # Scheduling
    default_source_cadence_cron: str = Field(default="0 */6 * * *")
    max_fetch_timeout_seconds: int = Field(default=30)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def blocked_host_list(self) -> list[str]:
        return [host.strip() for host in self.ssrf_blocked_hosts.split(",") if host.strip()]

    @property
    def blocked_cidr_list(self) -> list[str]:
        return [cidr.strip() for cidr in self.ssrf_blocked_cidrs.split(",") if cidr.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
