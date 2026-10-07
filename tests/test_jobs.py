from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import jobs
from app.config import Settings
from app.db.models import Base, Difficulty, Problem, Progress, Status, Track
from app.services.sync import LeetCodeResponseError

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


def _problem(slug: str, track: Track, order_index: int) -> Problem:
    return Problem(
        slug=slug,
        title=slug.replace("-", " ").title(),
        difficulty=Difficulty.easy,
        track=track,
        pattern="Test",
        order_index=order_index,
        url=f"https://leetcode.com/problems/{slug}/",
        added_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def _raw(slug: str, ts: datetime) -> dict[str, object]:
    return {"titleSlug": slug, "timestamp": str(int(ts.timestamp()))}


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """A real session factory (not a single session) — daily_job opens its own."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
def daily_job_settings() -> Settings:
    return Settings(
        leetcode_username="test",
        consolidation_intervals=[3, 14, 45],
        maintenance_interval_days=90,
        review_per_day_cap=4,
        max_new_in_flight=1,
        tz="UTC",
        postgres_user="x",
        postgres_password="x",  # noqa: S106
        postgres_db="x",
        postgres_host="localhost",
        postgres_port=5432,
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    fetch_result: list[dict[str, object]] | Exception,
) -> None:
    monkeypatch.setattr(jobs, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)

    async def _fake_fetch(
        username: str, *, limit: int = 20, client: httpx.AsyncClient
    ) -> list[dict[str, object]]:
        if isinstance(fetch_result, Exception):
            raise fetch_result
        return fetch_result

    monkeypatch.setattr(jobs, "fetch_recent_ac", _fake_fetch)


@pytest.mark.asyncio
async def test_daily_job_introduces_when_nothing_to_sync(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    daily_job_settings: Settings,
) -> None:
    async with session_factory() as session:
        session.add(_problem("two-sum", Track.algo, 1))
        session.add(_problem("select-x", Track.sql, 1))
        await session.commit()

    _wire(monkeypatch, session_factory, daily_job_settings, fetch_result=[])

    await jobs.daily_job()

    async with session_factory() as session:
        rows = (await session.execute(select(Progress))).scalars().all()
        assert len(rows) == 1
        assert rows[0].problem_slug == "two-sum"
        assert rows[0].status == Status.introduced


@pytest.mark.asyncio
async def test_daily_job_syncs_before_introducing_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    daily_job_settings: Settings,
) -> None:
    """A solve that frees up the in-flight slot must let introduce_if_needed
    use that freed slot in the same run — proves sync happens before introduce."""
    solved_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    async with session_factory() as session:
        session.add(_problem("two-sum", Track.algo, 1))
        session.add(_problem("valid-anagram", Track.algo, 2))
        session.add(_problem("select-x", Track.sql, 1))
        session.add(
            Progress(
                problem_slug="two-sum",
                status=Status.introduced,
                introduced_at=datetime(2024, 12, 20, tzinfo=UTC),
            )
        )
        await session.commit()

    _wire(
        monkeypatch,
        session_factory,
        daily_job_settings,
        fetch_result=[_raw("two-sum", solved_at)],
    )

    await jobs.daily_job()

    async with session_factory() as session:
        rows = {
            p.problem_slug: p
            for p in (await session.execute(select(Progress))).scalars().all()
        }
        assert rows["two-sum"].status == Status.learning
        assert rows["select-x"].status == Status.introduced


@pytest.mark.asyncio
async def test_daily_job_swallows_http_error_and_does_not_introduce(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    daily_job_settings: Settings,
) -> None:
    async with session_factory() as session:
        session.add(_problem("two-sum", Track.algo, 1))
        await session.commit()

    _wire(
        monkeypatch,
        session_factory,
        daily_job_settings,
        fetch_result=httpx.ConnectError("connection refused"),
    )

    await jobs.daily_job()  # must not raise

    async with session_factory() as session:
        rows = (await session.execute(select(Progress))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_daily_job_swallows_malformed_leetcode_response(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    daily_job_settings: Settings,
) -> None:
    async with session_factory() as session:
        session.add(_problem("two-sum", Track.algo, 1))
        await session.commit()

    _wire(
        monkeypatch,
        session_factory,
        daily_job_settings,
        fetch_result=LeetCodeResponseError("GraphQL errors: [...]"),
    )

    await jobs.daily_job()  # must not raise

    async with session_factory() as session:
        rows = (await session.execute(select(Progress))).scalars().all()
        assert rows == []
