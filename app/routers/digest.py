from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.digest import ProblemSummary, build_digest, get_progress_summary

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
async def get_progress_summary_endpoint(
    session: AsyncSession = Depends(get_db),
) -> ProgressSummaryOut:
    summary = await get_progress_summary(session)
    return ProgressSummaryOut(
        by_status=summary.by_status, unintroduced=summary.unintroduced
    )


@router.get("/digest/today", response_model=DigestOut)
async def get_digest_today(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DigestOut:
    # Derive "today" from the configured tz rather than the server's local
    # clock, so the review-due comparison is self-consistent regardless of
    # the container's TZ setting.
    today = datetime.now(tz=ZoneInfo(settings.tz)).date()
    digest = await build_digest(session, settings, today)
    return DigestOut(
        new={
            track: [ProblemOut.from_summary(p) for p in problems]
            for track, problems in digest.new.items()
        },
        review=[ProblemOut.from_summary(p) for p in digest.review],
        review_overdue_total=digest.review_overdue_total,
    )
