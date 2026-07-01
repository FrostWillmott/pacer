from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler import AsyncScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import digest
from app.scheduler import register_jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    hour, minute = (int(x) for x in settings.digest_time.split(":"))
    async with AsyncScheduler() as scheduler:
        await register_jobs(scheduler, hour, minute, settings.tz)
        # AsyncScheduler() as a context manager only wires up the data store +
        # event broker — it does NOT run the schedule-processing loop. Without
        # this call add_schedule() just persists the schedule and nothing ever
        # executes it. Note: APScheduler 4.x defaults to an in-memory data
        # store, so schedules don't survive a restart — that's fine here only
        # because register_jobs() re-adds the schedule on every startup.
        await scheduler.start_in_background()
        yield


app = FastAPI(title="pacer", lifespan=lifespan)

app.include_router(digest.router)

try:
    app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
except RuntimeError:
    logger.info("frontend/ not found — static files not mounted")
