from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="infra/env/.env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "ai-hotspot-radar"
    app_timezone: str = "Asia/Shanghai"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_hotspot_radar"


settings = Settings()
