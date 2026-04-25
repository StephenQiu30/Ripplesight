from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="infra/env/.env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "ai-hotspot-radar"
    app_timezone: str = "Asia/Shanghai"
    database_url: str = "postgresql+psycopg://root:change-me@localhost:5432/ai_hotspot_radar"
    database_init_retries: int = 10
    database_init_retry_seconds: float = 1.0
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str | None = None
    relevance_threshold: float = 50.0
    source_fetch_limit: int = 20
    scheduler_enabled: bool = False
    check_interval_minutes: int = 60
    daily_digest_enabled: bool = False
    daily_digest_hour: int = 8
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_to_email: str | None = None
    smtp_use_tls: bool = True


settings = Settings()
