# CLAUDE.md
Guidance for Claude Code when working in this repository.

## Project

Personal LeetCode spaced-repetition tracker. Decides what to solve each day across
two tracks (NeetCode 150 algo + SQL 50), paces new problems, and tracks solved ones
via spaced repetition. Pulls solved problems automatically from LeetCode, sends a
macOS push notification every morning. Runs locally on Docker (auto-start on boot).

Stack: FastAPI + async SQLAlchemy 2.0 + asyncpg + PostgreSQL + Alembic + APScheduler 4.x.
Package manager: uv. Host notifier: Python script via launchd + osascript.

## Active rule modules

`python-core`, `backend-fastapi`, `testing`, `workflow-scaffolding`

## Architecture divergences

3-layer split (routers / services / db), NOT full Clean Architecture. No repository
layer — services call SQLAlchemy directly via `AsyncSession`.

`sync.py` is deliberately isolated as a fragile external integration (undocumented
LeetCode GraphQL). No other module may import from it.

## Commands

```bash
make install   # uv sync --all-extras + pre-commit install
make check     # lint + type + test — run before finishing any task
make fix       # ruff --fix + format
make test      # uv run pytest tests/ -v
```

To start the backend + DB locally:
```bash
cp .env.example .env    # fill in POSTGRES_PASSWORD and review TZ
docker compose up -d    # backend runs `alembic upgrade head` on startup
docker compose exec backend uv run python scripts/seed.py
```

## Key design decisions

- **Progress fold**: `compute_progress(submission_times, intervals, maintenance)` is a
  pure function. Progress can always be recomputed from scratch; the DB row is a cache.
- **`introduced_at` NOT NULL invariant**: `ORDER BY introduced_at DESC` drives track
  alternation. NULL breaks PostgreSQL's DESC sort. Ahead-of-pace solves use `solved_at`.
- **`status='review'` does not exist**: the review queue is a query
  (`next_review_at::date <= today AND status != 'introduced'`), not a stored status.
- **Scheduler writes, GET reads**: `introduce_if_needed()` is called by the APScheduler
  daily job, never by `GET /digest/today`. Keeps the endpoint side-effect-free.
- **Date-cast in review query**: `cast(next_review_at, Date) <= today` prevents a review
  due at 14:00 from not appearing until the next day.
- **Track alternation first-call default**: if `progress` is empty → algo first.
  If last introduced was SQL → algo next; otherwise SQL. Fallback if track exhausted.

## Git

- Do not add AI-tool references, co-author lines, or "generated with" notes to
  commit messages.
