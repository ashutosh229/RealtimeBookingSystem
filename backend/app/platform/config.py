from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=32)
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 7
    db_pool_size: int = 10
    campus_tz: str = "UTC"
    fair_share_window_days: int = 14
    sweep_interval_seconds: int = 30
    contention_min_waiting: int = 2
    promotion_min_gap_minutes: int = 0
    amqp_url: str = "amqp://guest:guest@localhost:5672/"
    relay_poll_ms: int = 200
    consumer_prefetch: int = 20
    max_delivery_attempts: int = 5
    redis_url: str = "redis://localhost:6379/0"
    avail_ttl_seconds: int = 10
    # Live surge protection (ADR-0022): per-user token bucket on booking requests. Off by default.
    rate_limit_enabled: bool = False
    rate_limit_per_second: float = 1.0
    rate_limit_burst: int = 10
    # Invariant checker (ADR-0023): every N seconds in the worker; 0 disables.
    invariant_check_seconds: int = 60
    invariant_lookback_days: int = 3  # 0 = check the whole ledger
    # Operations (ADR-0024)
    attempts_retention_days: int = 90  # 0 = keep booking_attempts forever
    user_cache_seconds: int = 0  # in-process cache of the JWT user lookup; 0 = off
    cors_origins: str = "http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006"

    @property
    def dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


