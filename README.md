# pacer

A personal LeetCode spaced-repetition tracker. It decides what to solve each day
across two tracks — **NeetCode 150** (algorithms) and **SQL 50** — paces the
introduction of new problems, and schedules review of solved ones via spaced
repetition. Solved problems are pulled automatically from LeetCode, and a native
macOS notification is fired every morning with the day's digest.

Runs locally on Docker (auto-starts on boot); a small host script delivers the
notification.

## How it works

- **Two tracks, one shared quota.** New problems are introduced one at a time,
  alternating between the algo and SQL tracks. A new problem is only introduced
  once the current one is resolved — the pace is "one thing in flight," not
  "one added per day regardless of backlog."
- **Spaced repetition.** After a solve, a problem is reviewed at fixed intervals
  (`[3, 14, 45]` days) and then enters an indefinite 90-day maintenance loop, so
  nothing ages out of practice.
- **LeetCode is the only source of truth.** There is no manual "mark as solved";
  a daily job polls LeetCode's `recentAcSubmissionList` and reconciles it against
  the database.
- **The digest is a read-only view.** `GET /digest/today` never mutates state;
  all writes happen in the scheduled daily job.

For the reasoning behind the non-obvious design choices, see
[`docs/DECISIONS.md`](docs/DECISIONS.md); for the full functional spec, see
[`docs/pacer_spec.md`](docs/pacer_spec.md).

## Stack

FastAPI · async SQLAlchemy 2.0 · asyncpg · PostgreSQL · Alembic · APScheduler 4.x ·
[uv](https://github.com/astral-sh/uv) for dependency management. Host notifier: a
Python script run via `launchd` + `osascript`.

## Quick start

```bash
# 1. Configure
cp .env.example .env          # set POSTGRES_PASSWORD, LEETCODE_USERNAME, review TZ

# 2. Start backend + DB (backend runs `alembic upgrade head` on startup)
docker compose up -d

# 3. Seed the two curated problem lists (NeetCode 150 + SQL 50)
docker compose exec backend uv run python scripts/seed.py
```

The frontend is then served at `http://localhost:8000/` (a single read-only page),
alongside the API.

### Endpoints

| Method | Path                | Description                                   |
|--------|---------------------|-----------------------------------------------|
| `GET`  | `/digest/today`     | Today's new + due-for-review problems         |
| `GET`  | `/progress/summary` | Per-track counts by status                    |
| `GET`  | `/`                 | Read-only frontend                            |

## Configuration

All tunables live in `.env` (see `.env.example`):

| Variable                     | Meaning                                          |
|------------------------------|--------------------------------------------------|
| `LEETCODE_USERNAME`          | Your LeetCode handle (profile must be public)    |
| `NEW_PROBLEMS_PER_DAY_TOTAL` | Shared daily quota for introducing new problems  |
| `CONSOLIDATION_INTERVALS`    | Post-solve review intervals, in days             |
| `MAINTENANCE_INTERVAL_DAYS`  | Repeating maintenance cadence after consolidation|
| `REVIEW_PER_DAY_CAP`         | Max review items shown per day                   |
| `TZ`                         | Container timezone — must match your macOS zone  |
| `DIGEST_TIME`                | Local time the daily job runs (`HH:MM`)          |
| `BACKEND_PORT`               | Host port for the backend                        |
| `POSTGRES_*`                 | Database credentials and host                    |

## macOS notifications (host notifier)

The notifier can't live in Docker — macOS Notification Center is a host-level API.
It polls `GET /digest/today` and fires a notification via `osascript`, driven by
`launchd`. One-time activation (run as your user, after editing the paths in
`notifier/com.pacer.notifier.plist` to match your checkout):

```bash
ln -sf "$(pwd)/notifier/com.pacer.notifier.plist" \
       ~/Library/LaunchAgents/com.pacer.notifier.plist
launchctl load ~/Library/LaunchAgents/com.pacer.notifier.plist
```

## Development

```bash
make install   # uv sync --all-extras + install pre-commit hooks
make check     # lint + format check + type check + tests — run before finishing
make fix       # ruff --fix + format
make test      # pytest
```

Tests default to in-memory SQLite for speed. To run the DB-semantic suite against
a real PostgreSQL (as CI does), set `TEST_DATABASE_URL`:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db \
  uv run pytest tests/ --ignore=tests/routers
```

## Architecture

Lightweight 3-layer split: `routers/` (HTTP only) → `services/` (business logic) →
async SQLAlchemy. `app/services/sync.py` is deliberately isolated as a fragile
external integration (LeetCode's undocumented GraphQL API) — no other module
imports from it.
