# pacer — Spec: local LeetCode spaced-repetition tracker

## 1. Goal

Personal tool (not portfolio, not public, no external hosting). Acts as a
mentor: it **decides for you** what to solve today — across two tracks
(algorithms + SQL), pacing new problems from curated lists while tracking
already-solved ones with review dates via spaced repetition. The user doesn't
choose what to solve, and **enters nothing manually** — the only data source
is LeetCode (all practice, including what used to be solved with AI in chat
or in Sublime Text, now happens only there), the only source of "what's
today" is the daily digest. Automatically pulls solved LeetCode problems and
sends a push notification every morning with new problems and review
problems. Runs entirely locally on macOS, comes up automatically on system
boot via Docker.

## 2. Architecture

Three Docker containers + one process on the host (outside Docker):

```
┌─────────────────────────────────────────────┐
│ Docker (docker-compose, restart: unless-stopped) │
│                                               │
│  ┌──────────┐   ┌──────────────────┐        │
│  │ frontend │──▶│ backend           │        │
│  │ (min UI) │   │ FastAPI + APScheduler │    │
│  └──────────┘   └─────────┬────────┘        │
│                            │                 │
│                  ┌─────────▼────────┐        │
│                  │ db (PostgreSQL)  │        │
│                  └──────────────────┘        │
└─────────────────────────────────────────────┘
              ▲
              │ HTTP polling (once a day, morning)
┌─────────────┴─────────────────────┐
│ Host script (launchd, outside Docker) │
│ Python + plyer / osascript        │
│ → macOS Notification Center       │
└────────────────────────────────────┘
```

**Why the host script lives outside Docker:** a container has no access to
macOS's notification bus (Notification Center is a host-level API). This is
the only part of the system that has to live outside Docker.

## 3. Components and stack

| Component | Stack | Container |
|---|---|---|
| Backend | FastAPI + async SQLAlchemy 2 + APScheduler | `backend` |
| DB | PostgreSQL | `db` |
| Frontend | minimal, read-only (today's queue + progress, no forms) | merged into `backend` (served as static files) |
| Host notifier | Python script, `plyer` or direct `osascript`, launched via `launchd` | outside Docker |

### 3a. Configuration (`.env`)

Anything specific to a particular user/instance is not hardcoded — it lives
in `.env` (plus an `.env.example` with placeholders in the repo, in case this
ever gets published/forked):

```
# LeetCode
LEETCODE_USERNAME=Frost1981          # public profile, see 5.5

# Study plan (5.4, 5.6, 5.4a)
NEW_PROBLEMS_PER_DAY_TOTAL=1
CONSOLIDATION_INTERVALS=3,14,45      # days, one-time consolidation chain
MAINTENANCE_INTERVAL_DAYS=90         # days, infinite tail after consolidation
REVIEW_PER_DAY_CAP=4

# Digest and networking (5.7, section 8)
DIGEST_TIME=08:00
BACKEND_PORT=8000

# DB (standard docker-compose practice, not specific to this project)
POSTGRES_USER=leetcode_tracker
POSTGRES_PASSWORD=<generated on first run>
POSTGRES_DB=leetcode_tracker
```

`docker-compose.yml` picks these up via `env_file: .env` for `backend`, and
the host notifier (5.8, lives outside Docker) reads `BACKEND_PORT` and
`DIGEST_TIME` from the same file directly — a single source of configuration,
not two separate places where you could change the port in one and forget
the other.

None of the functional logic (5.1-5.9) changes — only the **source** of
values that were previously called "default" or "closed" in the spec text
changes. It's the same set of numbers, just not in the code.

## 4. Data model

```
problems
├── slug          (PK, str)       -- e.g. "two-sum"
├── title         (str)
├── difficulty    (enum: easy/medium/hard)
├── track         (enum: algo/sql)  -- which curated list
├── pattern       (str)           -- algo: "Sliding Window" etc.
│                                     sql: "Joins" / "Aggregation" /
│                                     "Window Functions" / "Subqueries" etc.
├── order_index   (int)           -- position in the study plan, **unique
│                                     within track**, not globally
├── url           (str)
└── added_at      (datetime)

submissions                        -- append-only log, source of truth
├── id            (PK, autoincrement)
├── problem_slug  (FK -> problems.slug)
└── solved_at     (datetime)

progress                           -- computed state, overwritten
├── problem_slug  (PK, FK -> problems.slug)
├── status        (enum: new/introduced/learning/review/maintenance)
├── introduced_at (datetime)      -- when it was introduced into the digest;
│                                     determines whose track is next (5.4)
├── interval_index (int)          -- index into CONSOLIDATION_INTERVALS,
│                                     unused after transitioning to maintenance
├── last_reviewed_at (datetime)
└── next_review_at   (datetime)
```

**Semantics of `maintenance`:** this is not a terminal status — it's an
infinite loop with a fixed period (5.6). A problem **never leaves rotation
for good** — that's the whole point of "staying sharp," not a one-time
consolidation followed by being forgotten.

**Semantics of `new`:** the problem exists in `problems`, but there's no row
in `progress` for it yet — it's simply waiting its turn by `order_index`. A
`progress` row is created the moment a problem is **introduced** into the
digest (status `introduced`), not only once it's solved — this lets the
pipeline distinguish "offered, but not solved yet" from "never shown at all."

`submissions` and `progress` are deliberately separate: changing the interval
algorithm shouldn't require migrating history — `progress` can always be
recomputed from scratch from `submissions`.

## 5. Functional requirements

### 5.1. Initial problem list load (seed, one-time)

Two independent curated lists, each with its own `order_index`:

- **Track `algo`:** NeetCode 150 — Blind 75 + categorization into 18
  patterns and the canonical study order (Arrays & Hashing → Two Pointers →
  Sliding Window → Stack → Binary Search → Linked List → Trees → Tries →
  Heap → Backtracking → Graphs → 1D DP → Intervals → Greedy → Advanced
  Graphs → 2D DP → Bit Manipulation → Math & Geometry).
- **Track `sql`:** **LeetCode SQL 50** — LeetCode's own official study plan
  (not a community list), grouped by topic: Select/Where → Joins →
  Aggregation → Sorting/Grouping → Advanced Select/Join → Subqueries →
  Window Functions. Given 4 Database + 3 Pandas problems are already solved
  (visible on the profile) — this isn't starting from zero, it's extending
  the track.
- The slug list for each track is hardcoded in the seed script (public
  data, no LeetCode call needed at this step).
- The script enriches each slug via `https://leetcode.com/graphql` (public
  title/difficulty/url fields, no auth) and loads it into `problems` with
  `track` and `order_index` matching its position in its own list.
- Run manually, not at application runtime. **Both lists (200+ problems
  total) are loaded all at once** — what's dynamic isn't the load itself,
  it's the pace of introduction into the digest (5.4).
- **Note on the SQL track:** LeetCode checks SQL solutions against the
  MySQL dialect, while your working stack is PostgreSQL. Syntax
  differences (e.g. `LIMIT`/`OFFSET` are nearly identical, but window
  functions and types may differ) aren't a blocker for practicing the
  patterns (JOIN/aggregation/subqueries transfer directly), but worth
  keeping in mind while solving.

### 5.4. Introducing new problems (study plan, alternating tracks)

- **One shared quota, not a separate one per track** — the track alternates
  based on the actual event (not the calendar day — so skipped days don't
  throw off the rhythm):
  ```
  NEW_PROBLEMS_PER_DAY_TOTAL = 1
  ```
- Determining "whose turn it is" needs the last-introduced track — hence
  `introduced_at` in the `progress` schema (see section 4): look at the
  track of the most recent `introduced` row and take the opposite one.
- Top-up logic when building the digest:
  ```sql
  introduced_count = SELECT COUNT(*) FROM progress WHERE status = 'introduced'

  if introduced_count < NEW_PROBLEMS_PER_DAY_TOTAL:
      last_track = SELECT pr.track FROM progress p
                   JOIN problems pr ON pr.slug = p.problem_slug
                   ORDER BY p.introduced_at DESC LIMIT 1
      next_track = 'sql' if last_track == 'algo' else 'algo'  -- if empty, start with algo

      candidate = SELECT * FROM problems
                  WHERE track = next_track AND slug NOT IN (SELECT problem_slug FROM progress)
                  ORDER BY order_index LIMIT 1

      if candidate is None:  -- next_track is already fully completed
          candidate = SELECT * FROM problems
                      WHERE track = (the other track) AND slug NOT IN (...)
                      ORDER BY order_index LIMIT 1  -- fall back to the remaining track

      -- INSERT INTO progress(status='introduced', introduced_at=now(),
      --                      interval_index=NULL, next_review_at=NULL)
  ```
  The explicit fallback to the opposite track matters: without it, once one
  track finishes, alternation would silently skip days instead of switching
  fully to the remaining track.
- **Natural track completion:** SQL 50 (50 problems) at a pace of 0.5/day
  (alternating, not 1/day per track) finishes in about **14 weeks**;
  NeetCode 150 finishes in about **10 months**. After that, all further
  introduction goes to the algo track without alternation (thanks to the
  fallback above) — no separate "SQL is done, switch over" logic needed,
  it's a side effect of the same query.
- **Doesn't burn out:** if an introduced problem isn't solved that day, it
  stays `introduced` and keeps appearing in the digest the next day — a new
  problem isn't introduced until the current one is cleared, regardless of
  track.
- The moment a submission comes in for a problem — `status` moves to
  `learning`, and the algorithm from 5.6 takes over from there.

### 5.4a. Review cap (protection against digest overflow)

- `REVIEW_PER_DAY_CAP = 4` — a **buffer above** the true average of the
  onboarding phase (2/day, see the exact calculation in 5.6), not the
  average itself. The cap doesn't solve the load problem (the choice of
  consolidation intervals and intro pace does that) — it specifically
  guards against **spikes**: if you skip several days in a row, more than 2
  overdue problems will pile up, and without a buffer they'd all dump into
  a single digest at once.
- **Prioritization on overflow:** if there are more problems with
  `next_review_at <= today` than `REVIEW_PER_DAY_CAP`, the most overdue ones
  are taken first — `ORDER BY next_review_at ASC LIMIT REVIEW_PER_DAY_CAP`.
  Nothing starves forever: whatever didn't make it in today stays the most
  overdue tomorrow, and is guaranteed to be among the first to make the cap.
- **The backlog isn't hidden, it's shown separately:** the digest contains
  not just the capped list but also the total overdue count —
  `review_overdue_total` — so you can see the real scale of the backlog
  instead of finding out only once it spills into one scary list.

### 5.5. Auto-detecting solved problems (the only data source)

- Once a day (see 5.8) the backend calls
  `recentAcSubmissionList(username=LEETCODE_USERNAME, limit=20)` — a public
  LeetCode GraphQL endpoint, **no authentication required**, but the
  profile must be public. `LEETCODE_USERNAME` comes from `.env` (see 3a),
  not hardcoded — for a fork, it's one line changed, no code edits.
  Verified with a curl request against `Frost1981` — data comes back.
- Matches the returned slugs against `problems`.
- Every match → a new row in `submissions`, no duplicates (checked by
  `problem_slug + solved_at` before insert).
- If the solved problem hadn't been `introduced` yet (the user solved it
  ahead of pace, on their own initiative) — a `progress` row is created
  right then, skipping the `introduced` stage.
- **There is no manual input at all** — by the user's decision, all
  practice, including what used to be solved with AI in chat or in Sublime
  Text, now happens only on LeetCode, so auto-detection is the sole and
  sufficient source. **A review means resubmitting the same slug on
  LeetCode**, not mentally recalling it — that's the only way the system
  sees a review happened. Side effect: if an attempt fails (no Accepted),
  no submission shows up — `next_review_at` stays in the past, the problem
  doesn't disappear, it becomes the top-priority item in the capped review
  list (5.4a) until it's successfully submitted. No separate "reset" logic
  is needed — overdue priority already provides that.
- **Known limitation:** the endpoint is unofficial, with a fetch limit of
  ~15-20 recent submissions. If more than that get solved in one day, some
  may be missed. Not an issue at the current pace (1-2 problems/day).

### 5.6. Recomputing progress and the interval algorithm (consolidation + infinite tail)

With no manual input, there's no signal about how hard a solve was — the
LeetCode API doesn't provide that, only the Accepted fact. The algorithm is
a flat progression with no branches, but runs in two distinct modes: a
one-time consolidation chain, then an **infinite maintenance loop**, rather
than an exit from rotation.

```
CONSOLIDATION_INTERVALS = [3, 14, 45]  # days, one-time chain on first learning
MAINTENANCE_INTERVAL = 90              # days, infinite loop after consolidation

on new submission for problem X:
    if status == "maintenance":
        # already consolidated — loops forever at a fixed period
        next_review_at = solved_at + MAINTENANCE_INTERVAL
        # status stays "maintenance"
    else:
        interval_index = min(interval_index + 1, len(CONSOLIDATION_INTERVALS) - 1)
        next_review_at = solved_at + CONSOLIDATION_INTERVALS[interval_index]
        if interval_index >= len(CONSOLIDATION_INTERVALS) - 1:
            status = "maintenance"  # consolidation chain complete, tail begins
        else:
            status = "learning"
```

**Why this shape:** `[3, 14, 45]` gives a problem 3 events — the solve (day
0) and **2 reviews** after it (day 3 and roughly day 17) — for initial
consolidation (grounded in the spacing effect for newly learned material).
After that, the problem **doesn't disappear** — it moves into a rare,
infinite loop, once every 90 days, until you stop maintaining the tool.
This is the difference from the previous version (`mastered` = excluded
forever), which broke the very goal of "staying sharp" — a problem would
have been forgotten for good right after consolidation.

**Load calculation during the onboarding phase** (while new problems are
still being introduced per 5.4, alternating tracks, intro pace of 1/day
total, not 2):

```
reviews/day ≈ intro_pace × reviews_after_solve = 1 × 2 = 2/day
```

So the **true average** in this phase is: `1 new + 2 reviews = 3/day`.
`REVIEW_PER_DAY_CAP` (5.4a) is a **buffer above** the true average of 2, not
the average itself; the cap only kicks in on spike days after a gap, not
every day.

**Load calculation in the steady-state long-term regime** (once the whole
pool of ~200 problems has completed consolidation and settled into
`maintenance`):

```
load/day ≈ pool_size / MAINTENANCE_INTERVAL = 200 / 90 ≈ 2.2/day
```

This is exactly the figure you intuitively named early on ("2-3 a day") — it
just referred not to the onboarding phase (where load is higher due to
concurrent new-problem introduction, see 6), but to this long-term phase.

### 5.7. Daily digest (once a day, morning)

Two blocks in one notification, "new" grouped by track for clarity:

- **New:** the result of step 5.4 (`status = 'introduced'`), grouped as
  `{"algo": [...], "sql": [...]}` — at most 1 problem total (per the
  alternation in 5.4, one of the two lists is empty).
- **Review:** capped and prioritized per 5.4a —
  `WHERE next_review_at <= today() AND status != 'introduced'
   ORDER BY next_review_at ASC LIMIT REVIEW_PER_DAY_CAP` — note that
  `maintenance` is **not** excluded from this query (unlike the earlier
  version with `mastered`) — that's the entire point of the infinite tail —
  plus the total overdue count separately, for backlog visibility.
- An APScheduler job in `backend`, cron trigger in the morning (default
  08:00, macOS system time).
- The result is assembled into `GET /digest/today` →
  `{"new": {"algo": [...], "sql": [...]}, "review": [...], "review_overdue_total": N}`,
  which the host script polls.

### 5.8. Host notifier

- A separate Python process, **outside Docker**, auto-started via `launchd`
  (a macOS agent that starts on user login).
- Once a day (synced with the job in 5.7, with a small time buffer) calls
  `GET /digest/today` on the backend container (`localhost:<port>`).
- If at least one of the blocks is non-empty → a native macOS push via
  `plyer` (or `osascript -e 'display notification'` as a dependency-free
  fallback), stating "N new / M for review" separately.
- The push is clickable (opens `localhost:<port>` with the frontend) — to
  be confirmed at implementation time whether `plyer`/`osascript` support a
  click action on macOS.

### 5.9. Minimal frontend (read-only)

- A single page, served by the backend container as static files (no
  separate frontend container, per the earlier decision to keep the
  frontend minimal).
- **No forms or input controls at all** — since there's no manual input
  whatsoever, the frontend purely displays state, it never writes to the DB.
- Features:
  - Two sections for today: "New" (with an algo/sql track badge on each,
    at most 1) and "Review" (capped at 4, plus a caption like "showing 4 of
    7 overdue" when overflowing)
  - Overall progress view: how many are introduced / consolidating /
    in infinite maintenance (`maintenance`) per track, optionally
    aggregated by `pattern`
- Fallback role (see 6): if the push doesn't arrive, this page is the only
  way to see today's queue.

## 6. Non-functional requirements

- **Auto-start:** Docker is already set to start with the system
  (confirmed). Backend and db come up via `docker-compose up -d` with
  `restart: unless-stopped`.
- **Locality:** no external hosting. The only external call is the public
  LeetCode GraphQL endpoint (no auth, no private data transmitted).
- **Timezone:** all dates (`solved_at`, `next_review_at`) are in the host's
  system time (macOS), no UTC conversions (personal tool, single user).
- **Fallback access:** if the push doesn't arrive (host script didn't
  start, the launchd agent crashed, etc.) — the frontend on `localhost` is
  always available to manually check the queue.
- **Expected load — two distinct phases, don't conflate them:**
  - **Onboarding phase** (while new problems are still being introduced,
    weeks/months): intro pace of 1/day total (algo/sql alternating, not
    simultaneous), true average for reviews — **2/day** (calculation in
    5.6), not 4 — `REVIEW_PER_DAY_CAP=4` is a cap-with-buffer for peak days,
    not the average. So the true average load: **1 new + 2 reviews =
    3/day** (~35-70 min: 15-40 min for the new problem, averaging between
    algo's 25-40 and sql's 15-25, + 2×(5-15 min per review, since this is
    already the second or third encounter with the problem, not solving
    from scratch) = 10-30 min on reviews). On peak days (after a gap) — up
    to 1 new + 4 reviews = 5/day, but that's not a typical day, it's the
    capped spike.
  - **Long-term phase** (once the entire pool of ~200 problems has
    completed consolidation and settled into the infinite `maintenance`
    loop, see 5.6): no new problems at all, load stabilizes at
    `200/90 ≈ 2.2 reviews/day` — permanently, not temporarily, regardless
    of how fast the onboarding phase went (this is now about the fixed
    size of the whole pool, not the speed at which it was built up). This
    is the "staying sharp" figure; on any given day it's a whole number
    (0, 1, 2, or 3), not literally "2.2" — that's an average over a long
    window, not a per-day count.
  - Both phases are noticeably above the historical pace (5 active days
    over the last year, per LeetCode profile data) — but since all practice
    now happens only on LeetCode (no AI chat/Sublime Text on the side),
    this number will become an honest reflection of real engagement, not
    just a fraction of it.

## 7. Out of scope (deliberately not doing)

- Auth/multi-user — this is a single-person tool.
- **Any manual input** — marking as solved, adding a problem outside the
  plan. By the user's decision, all practice goes through LeetCode only,
  so auto-detection is the sole data source, and the frontend is fully
  read-only.
- A full SM-2/Anki algorithm — a fixed interval progression is enough.
- Telegram/email channels — replaced by native OS push.
- Dynamically **loading** the problem list from LeetCode at runtime — the
  load of all problems into `problems` is one-time (5.1); what's dynamic is
  only the pace of their **introduction** into the digest (5.4) — not the
  same thing.
- Company tags (LeetCode Premium) — not reliable enough for automation, not
  included.
- **DataLemur / StrataScratch as a trackable SQL track** — checked: neither
  has a public API for auto-tracking, only a paid subscription with
  tracking inside their own interface. Since there's no manual input at
  all, any platform without a public API is automatically disqualified,
  regardless of content quality. If their business-context style content
  is appealing — that's separate, untracked practice outside this tool, not
  a replacement for LeetCode SQL 50.

## 8. Open questions before implementation starts

1. ~~LeetCode username~~ — **closed:** `LEETCODE_USERNAME=Frost1981` in
   `.env` (see 3a), public profile confirmed with a working curl request.
2. Exact time for the morning digest (default `DIGEST_TIME=08:00` in
   `.env` — good?).
3. Port for backend/frontend (default `BACKEND_PORT=8000` in `.env`, can be
   changed on conflict).
4. Does the push need to be clickable (opening the frontend on click), or
   is a plain text notification with the problem list enough?
5. ~~New-problem quotas and review cap~~ — **closed:**
   `NEW_PROBLEMS_PER_DAY_TOTAL=1` (algo/sql alternating by `introduced_at`,
   not simultaneous), `CONSOLIDATION_INTERVALS=[3,14,45]` (2 reviews after
   the solve, not 3), true onboarding average `1+2=3/day`,
   `REVIEW_PER_DAY_CAP=4` — a buffer for peak days, not the average itself.
   All of these values now live in `.env` (3a), not in the code.
6. The exact list of SQL 50 slugs — I'll collect it as a hardcoded list
   when writing the seed script, same as NeetCode 150 (this is data, not
   per-user configuration — it stays in code, not in `.env`). Nothing
   needed from you here, just flagging this is still pending at the code
   stage, not now.
7. ~~SQL platform~~ — **closed:** staying on LeetCode SQL 50. DataLemur and
   StrataScratch were checked — both lack a public API, not viable for
   auto-tracking without manual input, which no longer exists in this
   system.
8. ~~Long-term maintenance after finishing all problems~~ — **closed:**
   `mastered` was replaced with an infinite `maintenance` loop of
   `MAINTENANCE_INTERVAL=90` days. A problem is never excluded from
   rotation for good — steady-state long-term load ≈2.2 reviews/day across
   the whole pool (~200 problems).
