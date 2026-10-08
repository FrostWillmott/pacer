# pacer

A FastAPI spaced-repetition scheduling service with an integration to an
undocumented external API (LeetCode). It decides what to solve each day
across two tracks — **LeetCode Top Interview 150** (algorithms) and **SQL 50** — paces the
introduction of new problems, and schedules review of solved ones via spaced
repetition. Solved problems are pulled automatically via that integration, and
a native macOS notification is fired every morning with the day's digest.

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

FastAPI · async SQLAlchemy 2.0 · asyncpg · PostgreSQL · Alembic ·
[uv](https://github.com/astral-sh/uv) for dependency management. Host notifier: a
Python script run via `launchd` + `terminal-notifier`, which also triggers the
daily job.

## Quick start

```bash
# 1. Configure
cp .env.example .env          # set POSTGRES_PASSWORD, LEETCODE_USERNAME, review TZ

# 2. Start backend + DB (backend runs `alembic upgrade head` on startup)
docker compose up -d

# 3. Seed the two curated problem lists (Top Interview 150 + SQL 50)
docker compose exec backend uv run python scripts/seed.py

# 4. (macOS) Install the morning notification agent — see below
make install-notifier
```

The frontend is then served at `http://localhost:8000/` (a single read-only page),
alongside the API.

### Endpoints

| Method | Path                   | Description                                       |
|--------|------------------------|----------------------------------------------------|
| `GET`  | `/digest/today`        | Today's new + due-for-review problems             |
| `GET`  | `/progress/summary`    | Per-track counts by status                        |
| `POST` | `/internal/daily-job`  | Runs the sync/introduce job (host notifier only)   |
| `GET`  | `/health`              | Liveness check                                     |
| `GET`  | `/`                    | Read-only frontend                                 |

## Configuration

All tunables live in `.env` (see `.env.example`):

| Variable                     | Meaning                                          |
|------------------------------|--------------------------------------------------|
| `LEETCODE_USERNAME`          | Your LeetCode handle (profile must be public)    |
| `MAX_NEW_IN_FLIGHT`          | Max problems simultaneously in `introduced` status |
| `CONSOLIDATION_INTERVALS`    | Post-solve review intervals, in days             |
| `MAINTENANCE_INTERVAL_DAYS`  | Repeating maintenance cadence after consolidation|
| `REVIEW_PER_DAY_CAP`         | Max review items shown per day                   |
| `TZ`                         | Container timezone — must match your macOS zone  |
| `DIGEST_TIME`                | Local time the host notifier fires (`HH:MM`)     |
| `BACKEND_PORT`               | Host port for the backend                        |
| `POSTGRES_*`                 | Database credentials and host                    |

## macOS notifications (host notifier)

The notifier can't live in Docker — macOS Notification Center is a host-level API.
Driven by `launchd` at `DIGEST_TIME`, it triggers `POST /internal/daily-job`
(waits for it to finish), then polls `GET /digest/today` and fires a notification
naming the actual new/review problems (not just a count) — one script, one agent,
so the notification always reflects a job that has actually finished running. It
stays silent on days with nothing due, but does notify if the job or the digest
fetch itself fails. Clicking the notification opens the frontend, where each
problem links to LeetCode.

Requires [`terminal-notifier`](https://github.com/julienXX/terminal-notifier)
(`brew install terminal-notifier`) — plain `osascript -e 'display notification'`
has no click-to-open action, which is why this project uses it instead.

One-time activation generates the launchd agent from this checkout and loads it —
its schedule (`DIGEST_TIME`) and paths are derived automatically, nothing to
hand-edit:

```bash
brew install terminal-notifier   # one-time host dependency
make install-notifier            # or: uv run python notifier/install_agent.py
```

Re-run `make install-notifier` after changing `DIGEST_TIME` to resync the fire
time. To remove it: `make uninstall-notifier`.

## Development

```bash
make install   # uv sync + install pre-commit hooks
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
external integration (LeetCode's undocumented GraphQL API): all LeetCode HTTP
communication lives there, and `app/jobs.py` is its sole consumer.

**How this was built.** Spec ([docs/pacer_spec.md](docs/pacer_spec.md)), ADRs
([docs/DECISIONS.md](docs/DECISIONS.md)) and acceptance criteria are mine; implementation with Claude Code, every change reviewed by hand before commit.
The agent configuration lives in [developer-os](https://github.com/FrostWillmott/developer-os).
