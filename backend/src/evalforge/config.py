from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EvalForge"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://evalforge:evalforge@localhost:5432/evalforge"
    cors_origins: str = "http://localhost:5173"
    default_provider: str = "fake"
    fake_provider_seed: str = "evalforge-local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
