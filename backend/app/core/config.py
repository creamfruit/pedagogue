from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CAPACITOR_ORIGINS = ("capacitor://localhost", "http://localhost", "https://localhost")


def with_driver(url: str, driver: str) -> str:
    scheme, separator, rest = url.partition("://")
    if not separator or scheme not in {"postgres", "postgresql"} and not scheme.startswith("postgresql+"):
        return url
    return f"postgresql+{driver}://{rest}"


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

    admin_emails_raw: str = Field(default="", validation_alias=AliasChoices("ADMIN_EMAILS", "admin_emails_raw"))
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:4173",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins_raw"),
    )
    website_url: str | None = None
    allow_capacitor_origins: bool = True

    storage_endpoint: str | None = None
    storage_bucket: str = "piano-pedagogue"
    storage_access_key: str | None = None
    storage_secret_key: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    job_queue: Literal["background", "redis", "inline"] = "background"
    musicbrainz_contact: str = "https://github.com/creamfruit/pedagogue"
    embedding_dim: int = 64

    max_upload_mb: int = 50

    @model_validator(mode="before")
    @classmethod
    def normalise_database_urls(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        lowered = {key.lower(): key for key in values}
        database_key = lowered.get("database_url")
        if database_key and values.get(database_key):
            raw = str(values[database_key])
            values[database_key] = with_driver(raw, "asyncpg")
            alembic_key = lowered.get("alembic_database_url")
            if not alembic_key or not values.get(alembic_key):
                values["alembic_database_url"] = with_driver(raw, "psycopg")
        alembic_key = lowered.get("alembic_database_url")
        if alembic_key and values.get(alembic_key):
            values[alembic_key] = with_driver(str(values[alembic_key]), "psycopg")
        return values

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.cors_origins_raw.split(",") if origin.strip()]
        if self.website_url:
            origins.append(self.website_url.strip().rstrip("/"))
        if self.allow_capacitor_origins:
            origins.extend(CAPACITOR_ORIGINS)
        return list(dict.fromkeys(origins))

    @property
    def admin_emails(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails_raw.split(",") if email.strip()}

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
