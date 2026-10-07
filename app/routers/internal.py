from __future__ import annotations

from fastapi import APIRouter

from app.jobs import daily_job

router = APIRouter()


@router.post("/internal/daily-job", status_code=204)
async def run_daily_job() -> None:
    """Run the daily sync/introduce job synchronously.

    Triggered by a host launchd agent (see notifier/), not by an in-process
    scheduler — see docs/DECISIONS.md for why. Not authenticated: this is a
    single-user tool bound to localhost, matching /digest/today.
    """
    await daily_job()
