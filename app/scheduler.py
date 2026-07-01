from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.db.session import get_session_factory
from app.services.digest import introduce_if_needed
from app.services.sync import fetch_recent_ac, sync_submissions

logger = logging.getLogger(__name__)


async def daily_job() -> None:
    """Sync LeetCode submissions and introduce a new problem if the quota allows."""
    settings = get_settings()
    session_factory = get_session_factory()
    local_tz = ZoneInfo(settings.tz)

    async with session_factory() as session, session.begin():
        async with httpx.AsyncClient() as client:
            try:
                raw = await fetch_recent_ac(settings.leetcode_username, client=client)
            except httpx.HTTPError as exc:
                logger.error("LeetCode sync failed: %s", exc)
                return

        count = await sync_submissions(session, settings, raw)
        logger.info("sync: %d new submission(s)", count)

        now = datetime.now(tz=local_tz)
        await introduce_if_needed(session, settings, now)


async def register_jobs(
    scheduler: AsyncScheduler, hour: int, minute: int, tz: str
) -> None:
    """Add the daily digest job to an already-started scheduler."""
    await scheduler.add_schedule(
        daily_job,
        CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(tz)),
    )
