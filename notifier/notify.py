#!/usr/bin/env python3
"""Host notifier for pacer — runs outside Docker via launchd.

Triggers the daily sync/introduce job, then polls GET /digest/today and fires
a macOS notification via `terminal-notifier` naming the actual problems (not
just a count), clickable through to the frontend for the LeetCode links. Both
steps run from one launchd agent, in order, so there's no race between "job
ran" and "digest reflects the job" — see docs/DECISIONS.md for why a
two-agent buffered design was dropped.

Requires `terminal-notifier` on the host (`brew install terminal-notifier`):
plain `osascript -e 'display notification'` has no click-to-open action, and
we want a click on the notification to land on the digest page.

Activation (one-time): generate + load the launchd agent, which derives its
schedule (DIGEST_TIME) and paths from this checkout:
    make install-notifier   # or: uv run python notifier/install_agent.py
Re-run the same command after changing DIGEST_TIME to resync the schedule.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from _env import read_env

_NOTIFIER_GROUP = "com.pacer.notifier"

# On wake from overnight sleep, launchd fires this agent "as soon as
# possible" — which can be before Docker Desktop's VM has finished resuming
# and the backend is accepting connections. Give it a window to come up
# rather than failing immediately, or the daily job would silently not run
# on most mornings (the exact failure mode this whole redesign exists to fix).
_BACKEND_WAIT_TIMEOUT = 90.0
_BACKEND_WAIT_INTERVAL = 3.0

# launchd runs agents with a minimal PATH that doesn't include Homebrew's bin
# dirs, so shutil.which("terminal-notifier") finds it in an interactive shell
# but not under launchd. Check both known Homebrew prefixes as a fallback.
_NOTIFIER_FALLBACK_PATHS = (
    "/opt/homebrew/bin/terminal-notifier",  # Apple Silicon
    "/usr/local/bin/terminal-notifier",  # Intel
)


def _find_terminal_notifier() -> str | None:
    found = shutil.which("terminal-notifier")
    if found is not None:
        return found
    for candidate in _NOTIFIER_FALLBACK_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


def _notify(message: str, *, open_url: str | None = None) -> None:
    binary = _find_terminal_notifier()
    if binary is None:
        print(
            "pacer notifier: terminal-notifier not found on PATH — "
            "install with `brew install terminal-notifier`",
            file=sys.stderr,
        )
        return

    args = [binary, "-title", "pacer", "-message", message, "-group", _NOTIFIER_GROUP]
    if open_url:
        args += ["-open", open_url]
    subprocess.run(args, check=False, capture_output=True)  # noqa: S603


def _titles(problems: object) -> list[str]:
    if not isinstance(problems, list):
        return []
    return [str(p["title"]) for p in problems if isinstance(p, dict) and "title" in p]


def _wait_for_backend(base_url: str) -> bool:
    deadline = time.monotonic() + _BACKEND_WAIT_TIMEOUT
    while True:
        try:
            response = httpx.get(f"{base_url}/health", timeout=3.0)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass  # not up yet — connection refused, timeout, etc.
        if time.monotonic() >= deadline:
            return False
        time.sleep(_BACKEND_WAIT_INTERVAL)


def main() -> None:
    project_root = Path(__file__).parent.parent
    env = read_env(project_root / ".env")
    port = env.get("BACKEND_PORT", "8000")
    base_url = f"http://localhost:{port}"

    if not _wait_for_backend(base_url):
        print(
            f"pacer notifier: backend not healthy after {_BACKEND_WAIT_TIMEOUT:.0f}s"
            " — check Docker",
            file=sys.stderr,
        )
        _notify("backend did not come up in time — check Docker")
        return

    try:
        trigger = httpx.post(f"{base_url}/internal/daily-job", timeout=30.0)
        trigger.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"pacer notifier: daily-job trigger failed — {exc}", file=sys.stderr)
        _notify("daily job failed to run — check backend logs")
        return

    try:
        response = httpx.get(f"{base_url}/digest/today", timeout=5.0)
        response.raise_for_status()
        data: dict[str, object] = response.json()
    except httpx.HTTPError as exc:
        print(f"pacer notifier: HTTP error — {exc}", file=sys.stderr)
        _notify("digest fetch failed — check backend logs")
        return
    except Exception as exc:  # notifier must not crash on unexpected parse failure
        print(f"pacer notifier: unexpected error — {exc}", file=sys.stderr)
        _notify("digest fetch failed — check backend logs")
        return

    new_raw = data.get("new")
    new_titles: list[str] = []
    if isinstance(new_raw, dict):
        for track_problems in new_raw.values():
            new_titles.extend(_titles(track_problems))

    review_titles = _titles(data.get("review"))
    overdue_raw = data.get("review_overdue_total")
    overdue = int(overdue_raw) if isinstance(overdue_raw, int) else 0

    if not new_titles and not review_titles:
        return

    lines: list[str] = []
    if new_titles:
        lines.append("New: " + ", ".join(new_titles))
    if review_titles:
        hidden = overdue - len(review_titles)
        suffix = f" (+{hidden} more overdue)" if hidden > 0 else ""
        lines.append("Review: " + ", ".join(review_titles) + suffix)

    _notify("\n".join(lines), open_url=f"{base_url}/")


if __name__ == "__main__":
    main()
