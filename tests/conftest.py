from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Base

# Default to in-memory SQLite for a fast local suite; CI sets TEST_DATABASE_URL
# to a real Postgres so the divergent bits (cast-to-Date, tz-aware columns,
# ON CONFLICT) get exercised against the production engine.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


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
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as sess:
            yield sess
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
