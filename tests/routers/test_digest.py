from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Difficulty, Problem, Progress, Status, Track
from app.db.session import get_db
from app.main import app

_T0 = datetime(2025, 1, 1, tzinfo=UTC)


def _problem(slug: str, track: Track, order_index: int) -> Problem:
    return Problem(
        slug=slug,
        title=slug.replace("-", " ").title(),
        difficulty=Difficulty.medium,
        track=track,
        pattern="Test",
        order_index=order_index,
        url=f"https://leetcode.com/problems/{slug}/",
        added_at=_T0,
    )


def _progress(
    slug: str, *, status: Status, introduced_at: datetime, **kw: object
) -> Progress:
    return Progress(
        problem_slug=slug,
        status=status,
        introduced_at=introduced_at,
        interval_index=kw.get("interval_index"),
        last_reviewed_at=kw.get("last_reviewed_at"),
        next_review_at=kw.get("next_review_at"),
    )


@pytest.fixture
def client(
    session: AsyncSession, settings: Settings
) -> Generator[TestClient, None, None]:
    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_digest_today_returns_new_and_review_problems(
    client: TestClient, session: AsyncSession
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_progress("two-sum", status=Status.introduced, introduced_at=_T0))
    session.add(_problem("trips-and-users", Track.sql, 1))
    session.add(
        _progress(
            "trips-and-users",
            status=Status.learning,
            introduced_at=_T0 - timedelta(days=5),
            interval_index=0,
            next_review_at=_T0 - timedelta(days=1),
        )
    )
    await session.flush()

    response = client.get("/digest/today")

    assert response.status_code == 200
    body = response.json()
    assert [p["slug"] for p in body["new"]["algo"]] == ["two-sum"]
    assert body["new"]["sql"] == []
    assert [p["slug"] for p in body["review"]] == ["trips-and-users"]
    assert body["review_overdue_total"] == 1


@pytest.mark.asyncio
async def test_digest_today_empty_db_returns_empty_digest(client: TestClient) -> None:
    response = client.get("/digest/today")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "new": {"algo": [], "sql": []},
        "review": [],
        "review_overdue_total": 0,
    }


@pytest.mark.asyncio
async def test_progress_summary_counts_by_track_and_status(
    client: TestClient, session: AsyncSession
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_progress("two-sum", status=Status.introduced, introduced_at=_T0))
    session.add(_problem("valid-anagram", Track.algo, 2))
    session.add(_problem("trips-and-users", Track.sql, 1))
    await session.flush()

    response = client.get("/progress/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["by_status"]["algo"]["introduced"] == 1
    assert body["by_status"]["algo"]["learning"] == 0
    assert body["unintroduced"]["algo"] == 1
    assert body["unintroduced"]["sql"] == 1
