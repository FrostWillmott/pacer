"""LeetCode GraphQL sync — FRAGILE external integration.

recentAcSubmissionList is an undocumented, unofficial LeetCode endpoint.
No authentication required; the profile must be public. Fields and
availability can change without notice. All LeetCode HTTP communication is
isolated to this module — app/jobs.py is its sole consumer.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import cast
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Problem, Progress, Status, Submission
from app.services.progress import compute_progress

logger = logging.getLogger(__name__)


class LeetCodeResponseError(Exception):
    """Raised when a 200 response doesn't have the expected GraphQL shape.

    Covers both an explicit {"errors": [...]} body and unexpected/missing
    fields in individual submissions — LeetCode's endpoint is unofficial and
    undocumented, so either can change without notice.
    """


def _ensure_aware(dt: datetime) -> datetime:
    """Return a timezone-aware datetime, assuming UTC if tzinfo is absent.

    SQLite strips tzinfo on reads; PostgreSQL preserves UTC. This normalizes
    both so the in-memory dedup set comparison works across drivers.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


_LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

_GQL_RECENT_AC = """
query recentAcSubmissionList($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""


async def fetch_recent_ac(
    username: str,
    *,
    limit: int = 20,
    client: httpx.AsyncClient,
) -> list[dict[str, object]]:
    """Fetch recent accepted submissions from LeetCode's unofficial GraphQL API."""
    response = await client.post(
        _LEETCODE_GRAPHQL_URL,
        json={
            "query": _GQL_RECENT_AC,
            "variables": {"username": username, "limit": limit},
        },
        headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("errors"):
        raise LeetCodeResponseError(f"GraphQL errors: {data['errors']}")

    payload = data.get("data")
    if not isinstance(payload, dict) or "recentAcSubmissionList" not in payload:
        raise LeetCodeResponseError(f"unexpected response shape: {data!r}")

    submissions = payload["recentAcSubmissionList"]
    if not isinstance(submissions, list):
        raise LeetCodeResponseError(
            f"recentAcSubmissionList is not a list: {submissions!r}"
        )

    return cast(list[dict[str, object]], submissions)


async def sync_submissions(
    session: AsyncSession,
    settings: Settings,
    submissions_raw: list[dict[str, object]],
) -> int:
    """Insert new submissions and recompute progress for affected problems.

    Takes the already-fetched list so the DB orchestration is testable
    without a live LeetCode call (mock fetch_recent_ac at the boundary).
    Returns the number of new submissions inserted.
    """
    local_tz = ZoneInfo(settings.tz)

    known_result = await session.execute(select(Problem.slug))
    known_slugs: set[str] = set(known_result.scalars().all())

    existing_result = await session.execute(
        select(Submission.problem_slug, Submission.solved_at)
    )
    # Track in-memory so duplicate slugs within one batch don't cause IntegrityError.
    # Normalize naive datetimes to UTC-aware (_ensure_aware) so comparison works across
    # DB drivers — SQLite strips tzinfo; PostgreSQL preserves it as UTC.
    existing_pairs: set[tuple[str, datetime]] = {
        (row[0], _ensure_aware(row[1])) for row in existing_result.all()
    }

    progress_result = await session.execute(select(Progress.problem_slug))
    progress_slugs: set[str] = set(progress_result.scalars().all())

    new_count = 0
    affected_slugs: set[str] = set()

    for raw in submissions_raw:
        try:
            slug = str(raw["titleSlug"])
            solved_at = datetime.fromtimestamp(int(str(raw["timestamp"])), tz=local_tz)
        except (KeyError, ValueError) as exc:
            raise LeetCodeResponseError(f"malformed submission entry {raw!r}") from exc

        if slug not in known_slugs:
            continue

        if (slug, solved_at) in existing_pairs:
            continue

        session.add(Submission(problem_slug=slug, solved_at=solved_at))
        existing_pairs.add((slug, solved_at))
        new_count += 1

        if slug not in progress_slugs:
            # Ahead-of-pace solve: skip 'introduced' stage; fold will set real status
            session.add(
                Progress(
                    problem_slug=slug,
                    status=Status.introduced,
                    introduced_at=solved_at,
                    interval_index=None,
                    last_reviewed_at=None,
                    next_review_at=None,
                )
            )
            progress_slugs.add(slug)

        affected_slugs.add(slug)

    if not affected_slugs:
        return new_count

    await session.flush()
    await _recompute_progress(session, affected_slugs, settings)

    return new_count


async def _recompute_progress(
    session: AsyncSession,
    slugs: set[str],
    settings: Settings,
) -> None:
    """Recompute stored progress for each slug from its full submission log.

    Batched: one query for all submissions and one for all progress rows,
    grouped in memory — avoids a per-slug round trip.
    """
    times_result = await session.execute(
        select(Submission.problem_slug, Submission.solved_at)
        .where(Submission.problem_slug.in_(slugs))
        .order_by(Submission.problem_slug, Submission.solved_at)
    )
    times_by_slug: dict[str, list[datetime]] = defaultdict(list)
    for slug, solved_at in times_result.all():
        times_by_slug[slug].append(solved_at)

    progress_result = await session.execute(
        select(Progress).where(Progress.problem_slug.in_(slugs))
    )
    progress_by_slug = {p.problem_slug: p for p in progress_result.scalars().all()}

    for slug in slugs:
        progress = progress_by_slug.get(slug)
        if progress is None:
            logger.warning("recompute: no progress row for slug=%s", slug)
            continue

        state = compute_progress(
            times_by_slug[slug],
            settings.consolidation_intervals,
            settings.maintenance_interval_days,
        )

        progress.status = state.status
        progress.interval_index = state.interval_index
        progress.last_reviewed_at = state.last_reviewed_at
        progress.next_review_at = state.next_review_at

    await session.flush()
