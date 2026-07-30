#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Run directly (`python scripts/seed.py`) without the project being installed:
# put the repo root on sys.path so `import app` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.problem_sets import (
    ALGO_PROBLEMS,
    ALGO_TRACK_NAME,
    SQL_PROBLEMS,
    SQL_TRACK_NAME,
)

TRACKS_SUMMARY = f"{ALGO_TRACK_NAME} + {SQL_TRACK_NAME}"

__doc__ = f"""One-time seed: load {TRACKS_SUMMARY} into the problems table.

Usage:
    uv run python scripts/seed.py           # insert/update all
    uv run python scripts/seed.py --dry-run # print (queries LeetCode; no DB)

Idempotent: upserts by slug — safe to re-run after correcting a slug.
If GraphQL returns null for a slug, the problem is skipped with a warning
(common for premium-only problems or typos in the list).
"""


# ── GraphQL helpers ───────────────────────────────────────────────────────────

_LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

_GQL_QUESTION = """
query questionTitle($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    difficulty
  }
}
"""


async def fetch_problem_meta(
    slug: str, client: httpx.AsyncClient
) -> tuple[str, str] | None:
    """Return (title, difficulty) or None if the slug is unknown/premium."""
    try:
        response = await client.post(
            _LEETCODE_GRAPHQL_URL,
            json={"query": _GQL_QUESTION, "variables": {"titleSlug": slug}},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://leetcode.com",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        q = data.get("data", {}).get("question")
        if not q:
            return None
        return q["title"], q["difficulty"].lower()
    except httpx.HTTPError as exc:
        logging.warning("HTTP error for slug=%s: %s", slug, exc)
        return None


# ── DB upsert ─────────────────────────────────────────────────────────────────


async def upsert_problem(
    session: AsyncSession,
    slug: str,
    title: str,
    difficulty: str,
    track: str,
    pattern: str,
    order_index: int,
    added_at: datetime,
) -> None:
    await session.execute(
        text("""
            INSERT INTO problems (slug, title, difficulty, track, pattern, order_index, url, added_at)
            VALUES (:slug, :title, :difficulty, :track, :pattern, :order_index, :url, :added_at)
            ON CONFLICT (slug) DO UPDATE SET
                title       = EXCLUDED.title,
                difficulty  = EXCLUDED.difficulty,
                pattern     = EXCLUDED.pattern,
                order_index = EXCLUDED.order_index,
                url         = EXCLUDED.url
        """),
        {
            "slug": slug,
            "title": title,
            "difficulty": difficulty,
            "track": track,
            "pattern": pattern,
            "order_index": order_index,
            "url": f"https://leetcode.com/problems/{slug}/",
            "added_at": added_at,
        },
    )


# ── Main ──────────────────────────────────────────────────────────────────────


async def seed(*, dry_run: bool) -> None:
    from app.config import get_settings

    settings = get_settings()
    added_at = datetime.now(tz=ZoneInfo(settings.tz))

    problems: list[tuple[str, str, str, int]] = []  # (slug, pattern, track, order)
    for i, (slug, pattern) in enumerate(ALGO_PROBLEMS, start=1):
        problems.append((slug, pattern, "algo", i))
    for i, (slug, pattern) in enumerate(SQL_PROBLEMS, start=1):
        problems.append((slug, pattern, "sql", i))

    ok = skipped = 0

    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(httpx.AsyncClient())

        # Dry-run still queries LeetCode for titles/difficulty, but opens no DB
        # connection and writes nothing.
        session: AsyncSession | None = None
        if not dry_run:
            engine = create_async_engine(settings.database_url, echo=False)
            stack.push_async_callback(engine.dispose)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            session = await stack.enter_async_context(factory())
            await stack.enter_async_context(session.begin())

        for slug, pattern, track, order_index in problems:
            meta = await fetch_problem_meta(slug, client)
            if meta is None:
                logging.warning(
                    "SKIP %s — GraphQL returned null (premium or bad slug?)", slug
                )
                skipped += 1
                continue

            title, difficulty = meta
            if session is None:
                print(
                    f"  [{track}:{order_index:03d}] {slug!r} — {title} ({difficulty})"
                )
            else:
                await upsert_problem(
                    session,
                    slug,
                    title,
                    difficulty,
                    track,
                    pattern,
                    order_index,
                    added_at,
                )
            ok += 1

    total = ok + skipped
    print(f"\nDone: {ok}/{total} inserted/updated, {skipped} skipped.")
    if skipped:
        print("Re-run after fixing slugs above — the script is idempotent.")


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Seed {TRACKS_SUMMARY} problems")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be loaded; still queries LeetCode, no DB connection",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
