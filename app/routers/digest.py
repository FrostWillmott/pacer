from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Problem, Progress, Status
from app.db.session import get_db
from app.services.digest import ProblemSummary, build_digest

router = APIRouter()


class ProblemOut(BaseModel):
    slug: str
    title: str
    url: str
    difficulty: str
    track: str
    pattern: str

    @classmethod
    def from_summary(cls, s: ProblemSummary) -> ProblemOut:
        return cls(
            slug=s.slug,
            title=s.title,
            url=s.url,
            difficulty=s.difficulty,
            track=s.track,
            pattern=s.pattern,
        )


class DigestOut(BaseModel):
    new: dict[str, list[ProblemOut]]
    review: list[ProblemOut]
    review_overdue_total: int


class ProgressSummaryOut(BaseModel):
    by_status: dict[str, dict[str, int]]
    unintroduced: dict[str, int]


@router.get("/progress/summary", response_model=ProgressSummaryOut)
async def get_progress_summary(
    session: AsyncSession = Depends(get_db),
) -> ProgressSummaryOut:
    rows = (
        await session.execute(
            select(Problem.track, Progress.status, func.count())
            .join(Progress, Progress.problem_slug == Problem.slug)
            .group_by(Problem.track, Progress.status)
        )
    ).all()

    by_status: dict[str, dict[str, int]] = {
        "algo": {s.value: 0 for s in Status},
        "sql": {s.value: 0 for s in Status},
    }
    for track, status, count in rows:
        by_status[track][status] = count

    unintroduced_rows = (
        await session.execute(
            select(Problem.track, func.count())
            .where(Problem.slug.notin_(select(Progress.problem_slug)))
            .group_by(Problem.track)
        )
    ).all()

    unintroduced: dict[str, int] = {"algo": 0, "sql": 0}
    for track, count in unintroduced_rows:
        unintroduced[track] = count

    return ProgressSummaryOut(by_status=by_status, unintroduced=unintroduced)


@router.get("/digest/today", response_model=DigestOut)
async def get_digest_today(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DigestOut:
    digest = await build_digest(session, settings, date.today())
    return DigestOut(
        new={
            track: [ProblemOut.from_summary(p) for p in problems]
            for track, problems in digest.new.items()
        },
        review=[ProblemOut.from_summary(p) for p in digest.review],
        review_overdue_total=digest.review_overdue_total,
    )
