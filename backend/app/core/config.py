from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Piano Pedagogue"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = True

    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://piano:piano@localhost:5432/piano"
    )
    alembic_database_url: PostgresDsn = Field(
        default="postgresql+psycopg://piano:piano@localhost:5432/piano"
    )
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    secret_key: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:4173",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins_raw"),
    )

    storage_endpoint: str | None = None
    storage_bucket: str = "piano-pedagogue"
    storage_access_key: str | None = None
    storage_secret_key: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    job_queue: Literal["background", "redis", "inline"] = "background"
    embedding_dim: int = 64

    max_upload_mb: int = 50

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_dsn(self) -> str:
        return str(self.alembic_database_url)

    @property
    def async_dsn(self) -> str:
        return str(self.database_url)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
