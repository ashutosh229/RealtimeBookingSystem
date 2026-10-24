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

    @property
    def dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
