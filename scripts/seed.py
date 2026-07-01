#!/usr/bin/env python3
"""One-time seed: load NeetCode 150 + SQL 50 into the problems table.

Usage:
    uv run python scripts/seed.py           # insert/update all
    uv run python scripts/seed.py --dry-run # print (queries LeetCode; no DB)

Idempotent: upserts by slug — safe to re-run after correcting a slug.
If GraphQL returns null for a slug, the problem is skipped with a warning
(common for premium-only problems or typos in the list).
"""

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

# ── Problem lists ─────────────────────────────────────────────────────────────
# Each entry: (slug, pattern)
# order_index is implicit (1-based position within each list)

ALGO_PROBLEMS: list[tuple[str, str]] = [
    # Arrays & Hashing
    ("contains-duplicate", "Arrays & Hashing"),
    ("valid-anagram", "Arrays & Hashing"),
    ("two-sum", "Arrays & Hashing"),
    ("group-anagrams", "Arrays & Hashing"),
    ("top-k-frequent-elements", "Arrays & Hashing"),
    ("encode-and-decode-strings", "Arrays & Hashing"),
    ("product-of-array-except-self", "Arrays & Hashing"),
    ("valid-sudoku", "Arrays & Hashing"),
    ("longest-consecutive-sequence", "Arrays & Hashing"),
    # Two Pointers
    ("valid-palindrome", "Two Pointers"),
    ("two-sum-ii-input-array-is-sorted", "Two Pointers"),
    ("3sum", "Two Pointers"),
    ("container-with-most-water", "Two Pointers"),
    ("trapping-rain-water", "Two Pointers"),
    # Sliding Window
    ("best-time-to-buy-and-sell-stock", "Sliding Window"),
    ("longest-substring-without-repeating-characters", "Sliding Window"),
    ("longest-repeating-character-replacement", "Sliding Window"),
    ("permutation-in-string", "Sliding Window"),
    ("minimum-window-substring", "Sliding Window"),
    ("sliding-window-maximum", "Sliding Window"),
    # Stack
    ("valid-parentheses", "Stack"),
    ("min-stack", "Stack"),
    ("evaluate-reverse-polish-notation", "Stack"),
    ("generate-parentheses", "Stack"),
    ("daily-temperatures", "Stack"),
    ("car-fleet", "Stack"),
    ("largest-rectangle-in-histogram", "Stack"),
    # Binary Search
    ("binary-search", "Binary Search"),
    ("search-a-2d-matrix", "Binary Search"),
    ("koko-eating-bananas", "Binary Search"),
    ("find-minimum-in-rotated-sorted-array", "Binary Search"),
    ("search-in-rotated-sorted-array", "Binary Search"),
    ("time-based-key-value-store", "Binary Search"),
    ("median-of-two-sorted-arrays", "Binary Search"),
    # Linked List
    ("reverse-linked-list", "Linked List"),
    ("merge-two-sorted-lists", "Linked List"),
    ("reorder-list", "Linked List"),
    ("remove-nth-node-from-end-of-list", "Linked List"),
    ("copy-list-with-random-pointer", "Linked List"),
    ("add-two-numbers", "Linked List"),
    ("linked-list-cycle", "Linked List"),
    ("find-the-duplicate-number", "Linked List"),
    ("lru-cache", "Linked List"),
    ("merge-k-sorted-lists", "Linked List"),
    ("reverse-nodes-in-k-group", "Linked List"),
    # Trees
    ("invert-binary-tree", "Trees"),
    ("maximum-depth-of-binary-tree", "Trees"),
    ("diameter-of-binary-tree", "Trees"),
    ("balanced-binary-tree", "Trees"),
    ("same-tree", "Trees"),
    ("subtree-of-another-tree", "Trees"),
    ("lowest-common-ancestor-of-a-binary-search-tree", "Trees"),
    ("binary-tree-level-order-traversal", "Trees"),
    ("binary-tree-right-side-view", "Trees"),
    ("count-good-nodes-in-binary-tree", "Trees"),
    ("validate-binary-search-tree", "Trees"),
    ("kth-smallest-element-in-a-bst", "Trees"),
    ("construct-binary-tree-from-preorder-and-inorder-traversal", "Trees"),
    ("binary-tree-maximum-path-sum", "Trees"),
    ("serialize-and-deserialize-binary-tree", "Trees"),
    # Tries
    ("implement-trie-prefix-tree", "Tries"),
    ("design-add-and-search-words-data-structure", "Tries"),
    ("word-search-ii", "Tries"),
    # Heap / Priority Queue
    ("kth-largest-element-in-a-stream", "Heap / Priority Queue"),
    ("last-stone-weight", "Heap / Priority Queue"),
    ("k-closest-points-to-origin", "Heap / Priority Queue"),
    ("kth-largest-element-in-an-array", "Heap / Priority Queue"),
    ("task-scheduler", "Heap / Priority Queue"),
    ("design-twitter", "Heap / Priority Queue"),
    ("find-median-from-data-stream", "Heap / Priority Queue"),
    # Backtracking
    ("subsets", "Backtracking"),
    ("combination-sum", "Backtracking"),
    ("permutations", "Backtracking"),
    ("subsets-ii", "Backtracking"),
    ("combination-sum-ii", "Backtracking"),
    ("word-search", "Backtracking"),
    ("palindrome-partitioning", "Backtracking"),
    ("letter-combinations-of-a-phone-number", "Backtracking"),
    ("n-queens", "Backtracking"),
    # Graphs
    ("number-of-islands", "Graphs"),
    ("clone-graph", "Graphs"),
    ("max-area-of-island", "Graphs"),
    ("pacific-atlantic-water-flow", "Graphs"),
    ("surrounded-regions", "Graphs"),
    ("rotting-oranges", "Graphs"),
    ("walls-and-gates", "Graphs"),
    ("course-schedule", "Graphs"),
    ("course-schedule-ii", "Graphs"),
    ("redundant-connection", "Graphs"),
    ("number-of-connected-components-in-an-undirected-graph", "Graphs"),
    ("graph-valid-tree", "Graphs"),
    ("word-ladder", "Graphs"),
    # Advanced Graphs
    ("reconstruct-itinerary", "Advanced Graphs"),
    ("min-cost-to-connect-all-points", "Advanced Graphs"),
    ("network-delay-time", "Advanced Graphs"),
    ("swim-in-rising-water", "Advanced Graphs"),
    ("alien-dictionary", "Advanced Graphs"),
    ("cheapest-flights-within-k-stops", "Advanced Graphs"),
    # 1D DP
    ("climbing-stairs", "1D DP"),
    ("min-cost-climbing-stairs", "1D DP"),
    ("house-robber", "1D DP"),
    ("house-robber-ii", "1D DP"),
    ("longest-palindromic-substring", "1D DP"),
    ("palindromic-substrings", "1D DP"),
    ("decode-ways", "1D DP"),
    ("coin-change", "1D DP"),
    ("maximum-product-subarray", "1D DP"),
    ("word-break", "1D DP"),
    ("longest-increasing-subsequence", "1D DP"),
    ("partition-equal-subset-sum", "1D DP"),
    # 2D DP
    ("unique-paths", "2D DP"),
    ("longest-common-subsequence", "2D DP"),
    ("best-time-to-buy-and-sell-stock-with-cooldown", "2D DP"),
    ("coin-change-ii", "2D DP"),
    ("target-sum", "2D DP"),
    ("interleaving-string", "2D DP"),
    ("longest-increasing-path-in-a-matrix", "2D DP"),
    ("distinct-subsequences", "2D DP"),
    ("edit-distance", "2D DP"),
    ("burst-balloons", "2D DP"),
    ("regular-expression-matching", "2D DP"),
    # Greedy
    ("maximum-subarray", "Greedy"),
    ("jump-game", "Greedy"),
    ("jump-game-ii", "Greedy"),
    ("gas-station", "Greedy"),
    ("hand-of-straights", "Greedy"),
    ("merge-triplets-to-form-target-triplet", "Greedy"),
    ("partition-labels", "Greedy"),
    ("valid-parenthesis-string", "Greedy"),
    # Intervals
    ("insert-interval", "Intervals"),
    ("merge-intervals", "Intervals"),
    ("non-overlapping-intervals", "Intervals"),
    ("meeting-rooms", "Intervals"),
    ("meeting-rooms-ii", "Intervals"),
    ("minimum-interval-to-include-each-query", "Intervals"),
    # Bit Manipulation
    ("number-of-1-bits", "Bit Manipulation"),
    ("counting-bits", "Bit Manipulation"),
    ("reverse-bits", "Bit Manipulation"),
    ("missing-number", "Bit Manipulation"),
    ("sum-of-two-integers", "Bit Manipulation"),
    ("reverse-integer", "Bit Manipulation"),
    ("single-number", "Bit Manipulation"),
    # Math & Geometry
    ("rotate-image", "Math & Geometry"),
    ("spiral-matrix", "Math & Geometry"),
    ("set-matrix-zeroes", "Math & Geometry"),
    ("happy-number", "Math & Geometry"),
    ("plus-one", "Math & Geometry"),
    ("pow-x-n", "Math & Geometry"),
    ("multiply-strings", "Math & Geometry"),
    ("detect-squares", "Math & Geometry"),
]

SQL_PROBLEMS: list[tuple[str, str]] = [
    # Select
    ("recyclable-and-low-fat-products", "Select"),
    ("find-customer-referee", "Select"),
    ("big-countries", "Select"),
    ("article-views-i", "Select"),
    ("invalid-tweets", "Select"),
    # Basic Joins
    ("replace-employee-id-with-the-unique-identifier", "Joins"),
    ("product-sales-analysis-i", "Joins"),
    ("customer-who-visited-but-did-not-make-any-transactions", "Joins"),
    ("rising-temperature", "Joins"),
    ("average-time-of-process-per-machine", "Joins"),
    ("employee-bonus", "Joins"),
    ("students-and-examinations", "Joins"),
    # Basic Aggregate Functions
    ("not-boring-movies", "Aggregation"),
    ("average-selling-price", "Aggregation"),
    ("project-employees-i", "Aggregation"),
    ("percentage-of-users-attended-a-contest", "Aggregation"),
    ("queries-quality-and-percentage", "Aggregation"),
    ("monthly-transactions-i", "Aggregation"),
    ("immediate-food-delivery-ii", "Aggregation"),
    ("game-play-analysis-iv", "Aggregation"),
    # Sorting and Grouping
    ("number-of-unique-subjects-taught-by-each-teacher", "Sorting & Grouping"),
    ("user-activity-for-the-past-30-days-i", "Sorting & Grouping"),
    ("product-sales-analysis-iii", "Sorting & Grouping"),
    ("classes-more-than-5-students", "Sorting & Grouping"),
    ("find-followers-count", "Sorting & Grouping"),
    # Advanced Select and Joins
    (
        "the-number-of-employees-which-report-to-each-employee",
        "Advanced Select & Joins",
    ),
    ("primary-department-for-each-employee", "Advanced Select & Joins"),
    ("triangle-judgement", "Advanced Select & Joins"),
    ("consecutive-numbers", "Advanced Select & Joins"),
    ("product-price-at-a-given-date", "Advanced Select & Joins"),
    ("last-person-to-fit-in-the-bus", "Advanced Select & Joins"),
    ("count-salary-categories", "Advanced Select & Joins"),
    # Subqueries
    ("employees-whose-manager-left-the-company", "Subqueries"),
    ("exchange-seats", "Subqueries"),
    ("movie-rating", "Subqueries"),
    ("restaurant-growth", "Subqueries"),
    ("friend-requests-ii-who-has-the-most-friends", "Subqueries"),
    ("investments-in-2016", "Subqueries"),
    ("department-top-three-salaries", "Subqueries"),
    # Advanced String Functions / Regex / Clause
    ("fix-names-in-a-table", "String Functions"),
    ("patients-with-a-condition", "String Functions"),
    ("delete-duplicate-emails", "String Functions"),
    ("second-highest-salary", "String Functions"),
    ("group-sold-products-by-the-date", "String Functions"),
    ("list-the-products-ordered-in-a-period", "String Functions"),
    ("find-users-with-valid-e-mails", "String Functions"),
    # Window Functions
    ("rank-scores", "Window Functions"),
    ("nth-highest-salary", "Window Functions"),
    ("department-highest-salary", "Window Functions"),
    ("managers-with-at-least-5-direct-reports", "Window Functions"),
]

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
    parser = argparse.ArgumentParser(description="Seed NeetCode 150 + SQL 50 problems")
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
