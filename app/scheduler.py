from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import get_settings
from app.db.session import get_session_factory
from app.services.digest import introduce_if_needed
from app.services.sync import LeetCodeResponseError, fetch_recent_ac, sync_submissions

logger = logging.getLogger(__name__)


async def daily_job() -> None:
    """Sync LeetCode submissions and introduce a new problem if the quota allows.

    Triggered by a host launchd agent hitting POST /internal/daily-job, not by
    an in-process scheduler — see docs/DECISIONS.md for why (host sleep silently
    starves in-process cron timers; launchd coalesces missed fires on wake).
    """
    settings = get_settings()
    session_factory = get_session_factory()
    local_tz = ZoneInfo(settings.tz)

    async with session_factory() as session, session.begin():
        async with httpx.AsyncClient() as client:
            try:
                raw = await fetch_recent_ac(settings.leetcode_username, client=client)
            except (httpx.HTTPError, LeetCodeResponseError) as exc:
                logger.error("LeetCode sync failed: %s", exc)
                return

        count = await sync_submissions(session, settings, raw)
        logger.info("sync: %d new submission(s)", count)

        now = datetime.now(tz=local_tz)
        await introduce_if_needed(session, settings, now)
