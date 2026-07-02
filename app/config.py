from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env is deliberately shared with the host notifier, which
    # reads DIGEST_TIME directly (see docs/DECISIONS.md) — not a Settings field.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    leetcode_username: str = ""

    max_new_in_flight: int = 1
    # NoDecode: skip pydantic-settings' JSON decoding of this env var so the
    # comma-separated form (CONSOLIDATION_INTERVALS=3,14,45) reaches the
    # mode="before" validator below instead of failing json.loads.
    consolidation_intervals: Annotated[list[int], NoDecode] = [3, 14, 45]
    maintenance_interval_days: int = 90
    review_per_day_cap: int = 4

    tz: str = "Europe/Moscow"
    backend_port: int = 8000

    postgres_user: str = "leetcode_tracker"
    postgres_password: str = "changeme"  # noqa: S105 — dev fallback, real value in .env
    postgres_db: str = "leetcode_tracker"
    postgres_host: str = "db"
    postgres_port: int = 5432

    @field_validator("consolidation_intervals", mode="before")
    @classmethod
    def parse_intervals(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",")]
        return v

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
