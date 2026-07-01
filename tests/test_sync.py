from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Difficulty, Problem, Progress, Status, Submission, Track
from app.services.sync import sync_submissions

_T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


def _problem(slug: str) -> Problem:
    return Problem(
        slug=slug,
        title=slug.title(),
        difficulty=Difficulty.easy,
        track=Track.algo,
        pattern="Test",
        order_index=1,
        url=f"https://leetcode.com/problems/{slug}/",
        added_at=_T0,
    )


def _raw(slug: str, ts: datetime) -> dict[str, object]:
    return {"titleSlug": slug, "timestamp": str(int(ts.timestamp()))}


@pytest.mark.asyncio
async def test_new_submission_creates_submission_and_progress(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum"))
    await session.flush()

    count = await sync_submissions(session, settings, [_raw("two-sum", _T0)])

    assert count == 1
    subs = (await session.execute(select(Submission))).scalars().all()
    assert len(subs) == 1
    progs = (await session.execute(select(Progress))).scalars().all()
    assert len(progs) == 1
    assert progs[0].status == Status.learning


@pytest.mark.asyncio
async def test_unknown_slug_is_skipped(
    session: AsyncSession, settings: Settings
) -> None:
    count = await sync_submissions(session, settings, [_raw("unknown-problem", _T0)])

    assert count == 0
    subs = (await session.execute(select(Submission))).scalars().all()
    assert len(subs) == 0


@pytest.mark.asyncio
async def test_duplicate_submission_not_inserted(
    session: AsyncSession, settings: Settings
) -> None:
    session.add(_problem("two-sum"))
    session.add(Submission(problem_slug="two-sum", solved_at=_T0))
    session.add(
        Progress(
            problem_slug="two-sum",
            status=Status.learning,
            introduced_at=_T0 - timedelta(days=1),
            interval_index=0,
            last_reviewed_at=_T0,
            next_review_at=_T0 + timedelta(days=3),
        )
    )
    await session.flush()

    count = await sync_submissions(session, settings, [_raw("two-sum", _T0)])

    assert count == 0
    subs = (await session.execute(select(Submission))).scalars().all()
    assert len(subs) == 1


@pytest.mark.asyncio
async def test_in_batch_duplicate_not_inserted_twice(
    session: AsyncSession, settings: Settings
) -> None:
    """Two identical entries in one LeetCode batch must not cause IntegrityError."""
    session.add(_problem("two-sum"))
    await session.flush()

    count = await sync_submissions(
        session, settings, [_raw("two-sum", _T0), _raw("two-sum", _T0)]
    )

    assert count == 1
    subs = (await session.execute(select(Submission))).scalars().all()
    assert len(subs) == 1


@pytest.mark.asyncio
async def test_ahead_of_pace_sets_introduced_at_to_solved_at(
    session: AsyncSession, settings: Settings
) -> None:
    """Problem solved before being introduced gets introduced_at = solved_at."""
    session.add(_problem("two-sum"))
    await session.flush()

    await sync_submissions(session, settings, [_raw("two-sum", _T0)])

    progs = (await session.execute(select(Progress))).scalars().all()
    assert len(progs) == 1
    assert progs[0].introduced_at is not None
