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
        yield


app = FastAPI(title="pacer", lifespan=lifespan)

app.include_router(digest.router)

try:
    app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
except RuntimeError:
    logger.info("frontend/ not found — static files not mounted")
