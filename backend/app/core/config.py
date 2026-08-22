from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NetGrid API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid"
    test_database_url: str = "postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid_test"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-generate-a-long-random-string"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7

    # Fernet key for NAS shared secrets at rest (Phase 7). Like jwt_secret,
    # the default is a dev-only bootstrap — set a real key in production.
    fernet_key: str = "QPfl8PTxda-hLHz5q6dDShAEvWMb9YNpqk4lKwPxTAM="

    cors_origins: list[str] = ["http://localhost:3000"]

    # Over-quota enforcement job (data-cap lifecycle): how often the APScheduler
    # job polls the usage report, and the per-subscriber cooldown between
    # enforcement attempts (a re-run inside the cooldown window skips a breach
    # it already acted on, so a stuck session isn't hammered every interval).
    quota_enforcement_interval_minutes: int = 5
    quota_enforce_cooldown_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
