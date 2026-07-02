# Architecture & technical decisions

Rationale behind the non-obvious choices in this codebase — why, not what.
The what is already documented in `CLAUDE.md` (quick reference) and
`docs/pacer_spec.md` (full functional spec). This file is the connective
tissue between them: for each decision, the constraint that produced it and
the alternative that was rejected.

## Deployment topology

**Two Docker containers (db + backend, the latter also serving the frontend as
static files) + one host process.**

The host notifier is the only piece that cannot live in Docker: macOS
Notification Center is a host-level API, unreachable from inside a
container's network/IPC namespace. Everything else that *can* be
containerized is, so `docker compose up -d` plus one `launchd` agent is the
entire deployment surface — no separate provisioning step, no systemd units
to hand-write, no app-specific host installation beyond the notifier script.

Rejected: running the whole stack outside Docker. Docker was kept for the
backend/db specifically so `restart: unless-stopped` + "Docker starts on
boot" (already configured) gives auto-start for free, without reimplementing
process supervision for a Postgres + FastAPI pair.

**Frontend served as static files from the backend container, not a
separate container.**

The frontend is a single read-only page with no build step and no forms
(see "Read-only frontend" below). A dedicated frontend container would add a
second image, a second port, and a reverse-proxy decision for zero
functional gain — there's no independent scaling, deploy cadence, or
technology reason to split it. `StaticFiles(directory="frontend", html=True)`
mounted on the same FastAPI app is the entire frontend deployment story.

**`daily_job` is triggered by a host `launchd` agent (`POST
/internal/daily-job`), not by an in-process scheduler.**

The original design ran an in-process APScheduler `AsyncScheduler` with a
`CronTrigger` inside the backend container. In practice it silently never
fired: the host Mac spends most of the night in Idle Sleep, and a suspended
machine doesn't run the container's event loop, so a wall-clock timer set for
08:00 simply never got CPU time to elapse (confirmed via `pmset -g log`
showing continuous sleep/dark-wake cycles straight through the scheduled
time — not an APScheduler bug). `launchd`'s `StartCalendarInterval`, by
contrast, is driven by the host's real-time clock: per `launchd.plist(5)`, a
fire missed while the machine is *asleep* runs (coalesced into one) as soon
as it wakes — exactly the semantics an unattended laptop needs. This does
not extend to the machine being fully powered off across the scheduled time;
in that case the fire is simply skipped until the next occurrence, same as
cron. Verified live: `launchctl kickstart -k gui/<uid>/com.pacer.notifier`
runs the real `.venv/bin/python notifier/notify.py` under launchd's
environment end-to-end (trigger → digest → notification) without error.

The notifier and the job trigger are one launchd agent (`notifier/notify.py`),
not two independently-scheduled ones. An earlier design fired a "run the job"
agent and a "poll + notify" agent a couple of minutes apart; on a wake-driven
coalesced run, both become due near-simultaneously with no ordering
guarantee between them, so the notifier could poll yesterday's digest before
the job had run. Doing `POST /internal/daily-job` (awaits completion) then
`GET /digest/today` then the notification in one script, from one agent, makes
the ordering structural instead of timing-dependent.

**Notification via `terminal-notifier`, not plain `osascript -e 'display
notification'`.**

The first version used bare `osascript`, which only shows text — no click
action. Once the notification needed to name specific problems, a plain count
("1 new / 4 for review") stopped being useful; the natural next step is
clicking through to LeetCode. `osascript`'s `display notification` has no
`-open`-equivalent, so `terminal-notifier` (`brew install terminal-notifier`)
replaced it — a new host dependency, but the only way to get click-to-open
without shipping a full macOS app bundle with `NSUserNotificationCenter`
entitlements, which is disproportionate for a personal tool. Caveat found
during setup: `launchd` runs agents with a minimal `PATH` that excludes
Homebrew's bin dirs, so `shutil.which("terminal-notifier")` resolves under an
interactive shell but not under `launchd` — `notify.py` falls back to the
known Homebrew prefixes (`/opt/homebrew/bin`, `/usr/local/bin`) rather than
relying on `PATH` alone.

**`notify.py` polls `GET /health` for up to 90s before triggering the daily
job, rather than hitting `/internal/daily-job` immediately.**

On the exact scenario this whole redesign targets — overnight sleep, wake in
the morning — `launchd` fires this agent "as soon as possible" after wake,
which can be before Docker Desktop's VM has finished resuming and the
backend is accepting connections. Without the wait, a POST that loses that
race fails fast (connection refused, not a timeout) and the daily job simply
doesn't run that morning — the same silent-digest outcome as the original
bug, just converted into a failure notification instead of no notification
at all. Verified live: stopping the backend, running the notifier, and
starting the backend ~8s into the poll loop completes successfully instead
of failing immediately; a backend that never comes up within the window
still fails, cleanly, after the deadline.

## Data model

**`submissions` (append-only log) and `progress` (computed, overwritten) are
separate tables, not one.**

If `progress` also held history, changing the interval algorithm (e.g.
`CONSOLIDATION_INTERVALS`) would require a data migration to reinterpret old
rows under the new rule. Instead `progress` is a *cache* of
`compute_progress(submissions, ...)` — see `app/services/progress.py`. It can
be dropped and rebuilt from `submissions` at any time with zero data loss.
This is why `compute_progress` is written as a pure fold with no I/O: it's
the single source of truth for "given this submission history and these
config values, what should the row say," independent of whatever the row
currently says.

**`status='review'` is not a stored enum value.**

`Status` only has `introduced / learning / maintenance` (`app/db/models.py`).
"Due for review" is a query condition
(`next_review_at <= today AND status != 'introduced'`), not a state. Storing
a `review` status would create a second source of truth for "is this due" —
every write path that changes `next_review_at` would also have to
remember to flip the status, and a missed update would silently desync the
two. Deriving it at query time makes that class of bug impossible instead of
disciplined against.

**`introduced_at` is `NOT NULL` on every `progress` row.**

Track alternation (`introduce_if_needed` in `app/services/digest.py`) needs
"what was the most recently introduced track," found via
`ORDER BY introduced_at DESC LIMIT 1`. PostgreSQL sorts `NULL` last in `DESC`
order — a nullable `introduced_at` would make ahead-of-pace solves (which
still get a `progress` row, per `sync.py`'s "ahead-of-pace solve" branch)
invisible to that query, silently breaking alternation. Ahead-of-pace rows
set `introduced_at = solved_at` specifically to satisfy this invariant rather
than leaving it null and special-casing the query.

**`problems.order_index` is unique within track, not globally.**

The two curated lists (NeetCode 150, SQL 50) are independent study plans with
independent orderings. A global ordering would force an arbitrary interleave
decision between two unrelated curricula for no benefit, since every query
that uses `order_index` already filters by `track` first.

**`Submission` has a `UniqueConstraint(problem_slug, solved_at)`.**

LeetCode's `recentAcSubmissionList` is polled once a day with a 20-item
window (see "Fragile external integration" below); the same accepted
submission can appear in more than one day's poll if the queue doesn't
advance fast enough, or the sync job retries after a partial failure. The
constraint — backed by an in-memory `existing_pairs` set in `sync.py` to
avoid a redundant `IntegrityError` per duplicate — makes re-polling
idempotent instead of requiring the caller to reason about what was already
inserted.

## Progress / spaced-repetition algorithm

**Fixed interval progression (`[3, 14, 45]` then infinite 90-day loop),
not SM-2 or a full Anki-style algorithm.**

The LeetCode API surfaces only a binary Accepted/not-Accepted signal — no
recall-difficulty rating, no timing data. SM-2-family algorithms adjust
intervals based on a self-reported ease factor; with no such signal to
consume, implementing one would add branching complexity that has nothing to
condition on. A flat progression is not a simplification made *despite* the
domain — it's the algorithm that matches the actual information available.

**`maintenance` is an infinite loop, not a terminal "mastered" status.**

An earlier version of the design used `mastered` (excluded from rotation
after consolidation). That directly contradicted the tool's stated purpose —
"staying sharp" — by letting a problem age out of practice indefinitely once
consolidated. Replacing the exit with a fixed 90-day repeating cadence keeps
every problem in the rotation for as long as the tool is used, at a cost
that's bounded and known in advance (`pool_size / MAINTENANCE_INTERVAL_DAYS`
≈ 2.2 reviews/day at steady state for ~200 problems — see spec §5.6).

**Interval values `[3, 14, 45]` specifically (2 post-solve reviews, not 1 or
3+).**

Grounded in the spacing effect for newly-learned material: day 0 (solve) +
day 3 + day ~17 gives two spaced reencounters before a problem is considered
consolidated. Fewer reviews would under-consolidate; more would push the
onboarding-phase load (see below) past what's sustainable at a 1/day intro
pace.

**A capped, prioritized review queue (`REVIEW_PER_DAY_CAP=4`,
`ORDER BY next_review_at ASC LIMIT cap`) instead of showing every overdue
item.**

The true steady-state average is ~2 reviews/day during onboarding; the cap
is deliberately set *above* that average as a buffer against spikes (e.g.
after a multi-day gap), not as the expected load. Capping without hiding the
overflow (`review_overdue_total` is still returned) means: a bad day never
produces an unbounded digest, but the backlog is never invisible either.
`ORDER BY next_review_at ASC` guarantees the most-overdue items always win a
cap slot, so nothing is starved forever — whatever misses today's cap is, by
definition, more overdue tomorrow and moves toward the front of the queue.

**No separate "reset interval on failed review" logic.**

A failed re-attempt on LeetCode produces no Accepted submission, so no row
lands in `submissions` and `next_review_at` simply stays in the past. That
alone makes the problem the top-priority candidate for the next capped
digest (oldest `next_review_at` sorts first) — equivalent to a reset in
effect, without needing to distinguish "failed" from "not yet attempted,"
which the sync source can't tell apart anyway (LeetCode's public API doesn't
expose failed submissions for this account).

## Track alternation and pacing

**One shared in-flight cap across both tracks (`MAX_NEW_IN_FLIGHT`),
alternating by event (last `introduced_at`'s track), not a calendar-day-based
split or per-track quotas.**

A per-track cap (e.g. "1 algo + 1 SQL in flight") would double the true
onboarding load relative to the "2-3 problems/day, ~30-60 min" target that
motivated `MAX_NEW_IN_FLIGHT=1` in the first place. Basing alternation on the
last introduced row's track (not on `today()` vs `yesterday()`) means a
skipped day doesn't desync the rotation — the next introduction always
continues correctly from wherever the sequence actually left off, which a
calendar-based rule couldn't guarantee.

**A new problem is only introduced once the current `introduced` one is
resolved, never introduced "on a timer" regardless of pending state.**

`introduce_if_needed` checks `introduced_count >= MAX_NEW_IN_FLIGHT` and
returns early if so. This is what prevents the digest from silently piling up
unsolved new problems — the pacing mechanism is "one thing in flight," not
"one thing added per day regardless of backlog." The name deliberately says
*in flight*, not *per day*: the daily job checks this cap once a day, but the
semantics it enforces are about concurrently-open problems, not a
day-scoped counter that resets at midnight.

**Explicit track-completion fallback (try `next_track`, then the other) is
inline in `introduce_if_needed`, not a separate "track finished" check
elsewhere.**

SQL 50 (50 problems) will exhaust well before NeetCode 150 (150 problems).
Without a fallback, once SQL is exhausted, alternation would keep trying to
introduce a SQL problem, find none, and introduce nothing every other day —
silently halving the intro rate instead of continuing at full pace on the
remaining track. Making the fallback part of the same function/query means
"track finished" isn't a state that has to be detected and handled
separately; it falls out of `_find_candidate` returning `None`.

**`introduce_if_needed` runs from `daily_job`, never from
`GET /digest/today`.**

The digest endpoint is polled at minimum once by the host notifier and
potentially again by anyone loading the frontend the same day. If introducing
a new problem were a side effect of the GET, the *number of times the page
happens to be viewed* would affect how many problems get introduced —
non-deterministic and load-bearing on client behavior. Restricting writes to
the daily cron job makes `GET /digest/today` idempotent and safe to poll
freely.

## External integration

**All LeetCode HTTP/GraphQL code is isolated in `app/services/sync.py`; no
other module imports from it (enforced by convention, stated explicitly in
the module docstring and `CLAUDE.md`).**

`recentAcSubmissionList` is an undocumented, unofficial endpoint (confirmed
by manual curl, not by any published LeetCode API contract). It can change
shape or disappear without notice. Containing the blast radius of that risk
to one file — rather than letting other modules construct LeetCode requests
or parse its response shape directly — means a breaking change on LeetCode's
side requires touching one file, not doing an audit across the codebase to
find every place that assumed the old shape.

**`sync_submissions` takes an already-fetched `list[dict]`, not a username +
HTTP client, and does the fetch separately in `daily_job`.**

Splitting "fetch from LeetCode" (`fetch_recent_ac`, thin, does one HTTP call)
from "reconcile fetched data against the DB" (`sync_submissions`, all the
actual logic: dedup, ahead-of-pace detection, progress recomputation) means
the reconciliation logic — the part with actual bugs to have — is testable
by passing in a literal Python list, with no mocked HTTP client, no
`respx`/`httpx_mock` machinery, and no live network dependency in the test
suite.

**Poll once a day, 20-item window, no attempt to paginate or backfill
beyond that.**

The endpoint's own limit is ~15-20 recent items; at the tool's target pace
(1-2 problems/day), a daily poll with that window has comfortable headroom.
Building pagination or a backfill mechanism against an unofficial endpoint
would add complexity to handle a volume of submissions the tool's own pacing
design guarantees won't occur — documented as a known, accepted limitation
rather than engineered around.

## Timezones and dates

**All dates use host/local time via `settings.tz` (`ZoneInfo`), no UTC
storage or conversion at read/write boundaries.**

This is a single-user, single-machine personal tool — there is no second
timezone to reconcile against. Introducing UTC storage plus display-time
conversion would be the standard multi-user-service pattern, but here it
only adds a conversion step that has to be gotten right in both directions
for a problem (multiple users in different zones) that doesn't exist.

**Review-due comparison is `next_review_at < start of (today + 1 day) in
settings.tz` instead of comparing full timestamps or casting to `Date`.**

`next_review_at` carries a time-of-day component inherited from when the
prior submission happened (e.g. 22:00). A raw timestamp comparison against
`datetime.now()` would make a problem due "today" only appear once the clock
passes that same time-of-day — meaning a problem solved late at night would
be invisible in tomorrow's 08:00 digest until 22:00 tomorrow. Comparing
against the start of the next calendar day makes "due today" mean the
calendar day, matching how a human would read the digest.

An earlier version used `cast(Progress.next_review_at, Date) <= today`. That
has two problems this version avoids: `timestamptz::date` in PostgreSQL
converts through the *session's* `timezone` GUC, not `settings.tz` — the two
happen to agree only because both are currently seeded from the same `.env`
`TZ`, an unpinned coincidence, not something the code enforces. And a
function-wrapped column (`cast(next_review_at, Date)`) can't be served by
`ix_progress_next_review_at`'s range scan. Computing the boundary as a
`settings.tz`-aware Python `datetime` and comparing it directly against the
`timestamptz` column sidesteps both: the comparison is timezone-explicit
(doesn't depend on what the DB session happens to be configured with), and it
keeps the index usable.

**`settings.tz`-aware `datetime.now(tz=...).date()` in the router, not a bare
`date.today()`.**

`GET /digest/today` derives "today" from `datetime.now(tz=ZoneInfo(settings.tz))`
(`app/routers/digest.py`) rather than the process's local clock, so the
review date-cast comparison (`cast(next_review_at, Date) <= today`) stays
self-consistent regardless of the container's own `TZ`. In deployment the
container's `TZ` from `.env` (`docker-compose.yml`) already matches
`settings.tz`, so the two agree — but sourcing the digest date from
`settings.tz` explicitly means the endpoint doesn't silently depend on that
coupling being correct.

## Configuration

**All tunables (`MAX_NEW_IN_FLIGHT`, `CONSOLIDATION_INTERVALS`,
`REVIEW_PER_DAY_CAP`, `LEETCODE_USERNAME`, ports, etc.) live in `.env`, not
as constants in code.**

Nothing here is fixed by the domain — they're personal pacing preferences
that would differ for a different user or a fork of this project. Keeping
them in `.env` (with `.env.example` as a placeholder template) means forking
or retuning the tool is a config change, not a code change. The host notifier
reads `BACKEND_PORT` and `DIGEST_TIME` from the same `.env` file directly
(not a second config file) specifically so the port/time can't be changed in
one place and forgotten in the other.

**The two curated problem-list slugs (NeetCode 150, SQL 50) are hardcoded in
`scripts/seed.py`, not put in `.env` or the DB seeded from a remote source.**

This is data, not per-user configuration — every fork of this tool would use
the same two curricula unless deliberately changed, which is a code change
regardless of where the list lives. It's also loaded once, manually, not at
runtime (see "Out of scope" below), so there's no operational reason to
externalize it into environment configuration.

## Testing and pure-function boundaries

**`compute_progress` / `advance_state` (`app/services/progress.py`) take
explicit config values as arguments rather than importing `Settings`.**

This is what makes the core spaced-repetition logic testable with plain
`pytest` unit tests — no DB, no settings/env fixture, no monkeypatching. A
test can assert `compute_progress([...], intervals=[1,2,3], maintenance=90)`
against an expected `ProgressState` with total control over the inputs,
independent of whatever `.env` happens to contain in CI.

**Mocking is confined to `fetch_recent_ac` in sync tests; DB-touching code
runs against a real (SQLite/asyncpg) session, never a mocked one.**

Per the project's testing rules: a mocked DB that passes while the real DB
fails is worse than no test. The one genuine external system boundary here
is the LeetCode HTTP call — that's the only thing that gets faked; the
reconciliation SQL runs for real in every test.

## Deliberately out of scope

These aren't gaps — they were considered and rejected for stated reasons
(spec §7):

- **No auth / multi-user support.** Single person, single machine; auth
  would be pure overhead with nothing to protect against (no network
  exposure beyond `localhost`).
- **No manual "mark as solved" or ad-hoc problem entry.** The entire premise
  of the tool is that LeetCode is the sole source of truth for practice —
  allowing a second input path would let progress state and actual practice
  drift apart, which is the exact failure mode (AI-chat/Sublime practice not
  reflected anywhere) the tool exists to eliminate.
- **No SM-2/Anki algorithm.** Covered above — there's no ease/difficulty
  signal to feed one.
- **No Telegram/email notification channel.** A native OS push covers the
  single-user, single-device case with zero added infrastructure (no bot
  token, no SMTP credentials to manage).
- **No runtime loading of the problem list from LeetCode.** The list is
  fixed curriculum data, loaded once by a manual script; only the *pace of
  introduction* into the digest is dynamic. Conflating the two would require
  the seed script to run unattended and handle partial/failed loads, for a
  list that never changes after the initial load.
- **No company-tag tracking (LeetCode Premium data).** Explicitly checked
  and rejected: not reliable enough to automate against.
- **No DataLemur / StrataScratch SQL track.** Explicitly checked: neither
  exposes a public API, and since the tool's core rule is "no manual input,
  ever," a platform without an API is automatically disqualified regardless
  of content quality — this follows directly from the no-manual-input
  decision above, not a separate judgment call.
