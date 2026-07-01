from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
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
