#!/usr/bin/env python3
"""Host notifier for pacer — runs outside Docker via launchd.

Polls GET /digest/today and fires a plain macOS notification via osascript.

Activation (one-time): generate + load the launchd agent, which derives its
schedule (DIGEST_TIME + 2 min) and paths from this checkout:
    make install-notifier   # or: uv run python notifier/install_agent.py
Re-run the same command after changing DIGEST_TIME to resync the schedule.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _read_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _notify(message: str) -> None:
    safe = message.replace('"', '\\"')
    subprocess.run(  # noqa: S603
        [
            "/usr/bin/osascript",
            "-e",
            f'display notification "{safe}" with title "pacer"',
        ],
        check=False,
        capture_output=True,
    )


def main() -> None:
    import httpx  # imported here so the script can be syntax-checked without venv

    project_root = Path(__file__).parent.parent
    env = _read_env(project_root / ".env")
    port = env.get("BACKEND_PORT", "8000")

    try:
        response = httpx.get(f"http://localhost:{port}/digest/today", timeout=5.0)
        response.raise_for_status()
        data: dict[str, object] = response.json()
    except httpx.HTTPError as exc:
        print(f"pacer notifier: HTTP error — {exc}", file=sys.stderr)
        return
    except Exception as exc:  # notifier must not crash on unexpected parse failure
        print(f"pacer notifier: unexpected error — {exc}", file=sys.stderr)
        return

    new_raw = data.get("new")
    new_total = (
        sum(len(v) for v in new_raw.values() if isinstance(v, list))
        if isinstance(new_raw, dict)
        else 0
    )
    review_raw = data.get("review")
    review_count = len(review_raw) if isinstance(review_raw, list) else 0
    overdue_raw = data.get("review_overdue_total")
    overdue = int(overdue_raw) if isinstance(overdue_raw, int) else 0

    if new_total == 0 and review_count == 0:
        return

    parts: list[str] = []
    if new_total:
        parts.append(f"{new_total} new")
    if review_count:
        suffix = f" (of {overdue} overdue)" if overdue > review_count else ""
        parts.append(f"{review_count} for review{suffix}")

    _notify(" / ".join(parts))


if __name__ == "__main__":
    main()
