from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Difficulty, Problem, Progress, Status, Track
from app.services.digest import build_digest, introduce_if_needed

_T0 = datetime(2025, 1, 1, tzinfo=UTC)
_TODAY = _T0.date()


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


@pytest.mark.asyncio
async def test_introduce_empty_db_picks_algo(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_problem("recyclable", Track.sql, 1))
    await session.flush()

    await introduce_if_needed(session, settings, _T0)
    await session.flush()

    rows = (await session.execute(select(Progress))).scalars().all()
    assert len(rows) == 1
    assert rows[0].problem_slug == "two-sum"
    assert rows[0].status == Status.introduced


@pytest.mark.asyncio
async def test_introduce_alternates_to_sql_after_algo(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_problem("recyclable", Track.sql, 1))
    session.add(_progress("two-sum", status=Status.learning, introduced_at=_T0))
    await session.flush()

    await introduce_if_needed(session, settings, _T0 + timedelta(days=1))
    await session.flush()

    rows = (await session.execute(select(Progress))).scalars().all()
    assert len(rows) == 2
    new_row = next(r for r in rows if r.problem_slug == "recyclable")
    assert new_row.status == Status.introduced


@pytest.mark.asyncio
async def test_introduce_noop_when_quota_full(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_progress("two-sum", status=Status.introduced, introduced_at=_T0))
    await session.flush()

    await introduce_if_needed(session, settings, _T0 + timedelta(hours=1))
    await session.flush()

    rows = (await session.execute(select(Progress))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_introduce_fallback_when_primary_track_exhausted(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum", Track.algo, 1))
    session.add(_problem("recyclable", Track.sql, 1))
    session.add(_problem("valid-anagram", Track.algo, 2))
    # Last introduced was algo (two-sum) then sql (recyclable) → next should be algo
    # but let's test: last introduced=algo → next=sql, sql exhausted → fallback to algo
    session.add(
        _progress(
            "two-sum", status=Status.learning, introduced_at=_T0 - timedelta(days=1)
        )
    )
    session.add(_progress("recyclable", status=Status.learning, introduced_at=_T0))
    await session.flush()

    await introduce_if_needed(session, settings, _T0 + timedelta(days=1))
    await session.flush()

    rows = (await session.execute(select(Progress))).scalars().all()
    new_rows = [r for r in rows if r.status == Status.introduced]
    assert len(new_rows) == 1
    assert new_rows[0].problem_slug == "valid-anagram"


@pytest.mark.asyncio
async def test_review_due_today_at_14h_visible_in_morning_digest(
    session: AsyncSession, settings: Settings
) -> None:
    """A review due today at 14:00 (settings.tz) must show up in an 08:00 poll.

    Regression test for the date-cast boundary: comparing raw timestamps
    against datetime.now() would hide this until the clock reaches 14:00.
    """
    tz_settings = settings.model_copy(update={"tz": "Europe/Moscow"})
    moscow = ZoneInfo("Europe/Moscow")
    today = date(2025, 6, 15)

    session.add(_problem("two-sum", Track.algo, 1))
    session.add(
        _progress(
            "two-sum",
            status=Status.learning,
            introduced_at=datetime(2025, 6, 1, tzinfo=moscow),
            interval_index=0,
            next_review_at=datetime(2025, 6, 15, 14, 0, tzinfo=moscow),
        )
    )
    await session.flush()

    digest = await build_digest(session, tz_settings, today)

    assert [p.slug for p in digest.review] == ["two-sum"]
    assert digest.review_overdue_total == 1


@pytest.mark.asyncio
async def test_review_due_tomorrow_just_after_midnight_not_yet_visible(
    session: AsyncSession, settings: Settings
) -> None:
    """A review due 00:30 tomorrow (settings.tz) must not appear in today's digest."""
    tz_settings = settings.model_copy(update={"tz": "Europe/Moscow"})
    moscow = ZoneInfo("Europe/Moscow")
    today = date(2025, 6, 15)

    session.add(_problem("two-sum", Track.algo, 1))
    session.add(
        _progress(
            "two-sum",
            status=Status.learning,
            introduced_at=datetime(2025, 6, 1, tzinfo=moscow),
            interval_index=0,
            next_review_at=datetime(2025, 6, 16, 0, 30, tzinfo=moscow),
        )
    )
    await session.flush()

    digest = await build_digest(session, tz_settings, today)

    assert digest.review == []
    assert digest.review_overdue_total == 0


@pytest.mark.asyncio
async def test_review_cap_returns_oldest_first(
    session: AsyncSession, settings: Settings
) -> None:
    for i in range(6):
        slug = f"problem-{i}"
        overdue_days = 10 + i
        session.add(_problem(slug, Track.algo, i + 1))
        session.add(
            _progress(
                slug,
                status=Status.learning,
                introduced_at=_T0 - timedelta(days=overdue_days + 1),
                interval_index=0,
                next_review_at=_T0 - timedelta(days=overdue_days),
            )
        )
    await session.flush()

    digest = await build_digest(session, settings, _TODAY)

    # ORDER BY next_review_at ASC: problem-5 is most overdue (earliest due date)
    assert digest.review_overdue_total == 6
    assert len(digest.review) == 4
    assert digest.review[0].slug == "problem-5"
    assert digest.review[3].slug == "problem-2"
