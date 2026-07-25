from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TraceLens Logging Service"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = ""

    # Shared secret the SDK sends as X-API-Key. Left empty in development so the
    # service works out of the box; required in production, enforced at startup.
    ingest_api_key: str | None = None

    # How many recent events to keep in memory for /v1/events and /v1/stats.
    # This is a development aid, not storage — see the note in main.py.
    buffer_size: int = 1000

    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
