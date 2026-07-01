from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Base


@pytest.fixture
def settings() -> Settings:
    return Settings(
        leetcode_username="test",
        consolidation_intervals=[3, 14, 45],
        maintenance_interval_days=90,
        review_per_day_cap=4,
        new_problems_per_day_total=1,
        tz="UTC",
        postgres_user="x",
        postgres_password="x",  # noqa: S106
        postgres_db="x",
        postgres_host="localhost",
        postgres_port=5432,
    )


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()
