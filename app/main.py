from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.session import get_engine
from app.routers import digest, internal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # daily_job runs via POST /internal/daily-job, triggered by a host launchd
    # agent rather than an in-process scheduler — see docs/DECISIONS.md.
    yield
    await get_engine().dispose()


app = FastAPI(title="pacer", lifespan=lifespan)

app.include_router(digest.router)
app.include_router(internal.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


try:
    app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
except RuntimeError:
    logger.info("frontend/ not found — static files not mounted")
