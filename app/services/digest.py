from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Difficulty, Problem, Progress, Status, Track


@dataclass
class ProblemSummary:
    slug: str
    title: str
    url: str
    difficulty: Difficulty
    track: Track
    pattern: str


@dataclass
class DigestResponse:
    new: dict[str, list[ProblemSummary]] = field(
        default_factory=lambda: {"algo": [], "sql": []}
    )
    review: list[ProblemSummary] = field(default_factory=list)
    review_overdue_total: int = 0


def _to_summary(problem: Problem) -> ProblemSummary:
    return ProblemSummary(
        slug=problem.slug,
        title=problem.title,
        url=problem.url,
        difficulty=problem.difficulty,
        track=problem.track,
        pattern=problem.pattern,
    )


async def _find_candidate(session: AsyncSession, track: Track) -> Problem | None:
    """Find the next problem in `track` that has no progress row yet."""
    introduced_slugs = select(Progress.problem_slug)
    result = await session.execute(
        select(Problem)
        .where(Problem.track == track)
        .where(Problem.slug.notin_(introduced_slugs))
        .order_by(Problem.order_index)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def introduce_if_needed(
    session: AsyncSession,
    settings: Settings,
    now: datetime,
) -> None:
    """Insert a progress row for one new problem if the quota allows it.

    Called by the scheduler, not by the GET endpoint — keeps the endpoint
    side-effect-free so the notifier can safely poll it multiple times.
    """
    count_result = await session.execute(
        select(func.count()).where(Progress.status == Status.introduced)
    )
    introduced_count: int = count_result.scalar_one()

    if introduced_count >= settings.new_problems_per_day_total:
        return

    last_track_result = await session.execute(
        select(Problem.track)
        .join(Progress, Progress.problem_slug == Problem.slug)
        .order_by(Progress.introduced_at.desc())
        .limit(1)
    )
    last_track = last_track_result.scalar_one_or_none()

    if last_track is None or last_track == Track.sql:
        next_track = Track.algo
    else:
        next_track = Track.sql

    candidate = await _find_candidate(session, next_track)

    if candidate is None:
        other = Track.sql if next_track == Track.algo else Track.algo
        candidate = await _find_candidate(session, other)

    if candidate is None:
        return  # all problems have been introduced — nothing left

    session.add(
        Progress(
            problem_slug=candidate.slug,
            status=Status.introduced,
            introduced_at=now,
            interval_index=None,
            last_reviewed_at=None,
            next_review_at=None,
        )
    )
    await session.flush()


async def build_digest(
    session: AsyncSession,
    settings: Settings,
    today: date,
) -> DigestResponse:
    """Assemble the current digest — purely read-only; no writes.

    Review comparison uses date-cast so a problem due at 14:00 on `today`
    does not require the caller's clock to reach that exact time.
    """
    new_result = await session.execute(
        select(Problem)
        .join(Progress, Progress.problem_slug == Problem.slug)
        .where(Progress.status == Status.introduced)
        .order_by(Problem.order_index)
    )
    new_problems = new_result.scalars().all()

    new_by_track: dict[str, list[ProblemSummary]] = {"algo": [], "sql": []}
    for p in new_problems:
        new_by_track[p.track].append(_to_summary(p))

    overdue_filter = (
        Progress.status != Status.introduced,
        cast(Progress.next_review_at, Date) <= today,
    )

    total_result = await session.execute(
        select(func.count()).select_from(Progress).where(*overdue_filter)
    )
    overdue_total: int = total_result.scalar_one()

    review_result = await session.execute(
        select(Problem)
        .join(Progress, Progress.problem_slug == Problem.slug)
        .where(*overdue_filter)
        .order_by(Progress.next_review_at)
        .limit(settings.review_per_day_cap)
    )
    review_problems = review_result.scalars().all()

    return DigestResponse(
        new=new_by_track,
        review=[_to_summary(p) for p in review_problems],
        review_overdue_total=overdue_total,
    )
