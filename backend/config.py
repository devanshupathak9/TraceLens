from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ChatJippity API"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    # NoDecode: stop pydantic-settings JSON-parsing this before the validator
    # below can split the comma-separated .env value.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # --- database ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/chatjippity"
    database_url_direct: str | None = None
    db_transaction_pooler: bool = False
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # --- jwt ---------------------------------------------------------
    jwt_secret: str = "change-me-this-is-not-a-secret"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24 * 7

    # --- llm --------------------------------------------------------------
    # Provider is chosen from the model name (see providers.py): claude-* goes
    # to Anthropic, everything else to OpenAI.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    default_model: str = "gpt-4o"
    llm_request_timeout_seconds: float = 60.0
    max_context_messages: int = 10
    system_prompt: str = "You are ChatJippity, a concise and helpful assistant."

    tracelens_ingest_url: str = "http://localhost:8001"
    tracelens_api_key: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string, since .env files can't hold lists."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def migration_url(self) -> str:
        """
        URL Alembic should use.

        Falls back to the runtime URL locally, where they're identical. On a
        managed pooler they differ: DDL needs the direct connection.
        """
        return self.database_url_direct or self.database_url

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def check_production_safety(self) -> list[str]:
        if not self.is_production:
            return []

        problems: list[str] = []
        if self.jwt_secret == "change-me-this-is-not-a-secret":
            problems.append("JWT_SECRET is still the default value")
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is shorter than 32 characters")
        if self.debug:
            problems.append("DEBUG is enabled in production")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS contains a wildcard")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
