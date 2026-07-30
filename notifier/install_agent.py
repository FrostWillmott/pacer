#!/usr/bin/env python3
"""Generate, install, and (re)load the pacer notifier launchd agent.

Everything is derived from this checkout and `.env`, so the notifier's fire
time stays in sync with DIGEST_TIME and the paths never need hand-editing.
Re-run after changing DIGEST_TIME to resync the schedule.

The agent is also set to RunAtLoad, so a day where DIGEST_TIME was missed
because the machine was fully off (not merely asleep) gets a catch-up run at
the next login/reboot; notify.py itself gates that extra trigger so it's a
no-op on an ordinary login that happens after today's job already ran, or
before DIGEST_TIME even arrives.

    uv run python notifier/install_agent.py             # install/refresh + load
    uv run python notifier/install_agent.py --uninstall # unload + remove

Or via the Makefile: `make install-notifier` / `make uninstall-notifier`.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from _env import read_env

LABEL = "com.pacer.notifier"
LAUNCHCTL = "/bin/launchctl"


def _parse_time(digest_time: str) -> tuple[int, int]:
    parsed = datetime.strptime(digest_time, "%H:%M")
    return parsed.hour, parsed.minute


def _agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _build_plist(project_root: Path, hour: int, minute: int) -> bytes:
    data: dict[str, object] = {
        "Label": LABEL,
        "ProgramArguments": [
            str(project_root / ".venv" / "bin" / "python"),
            str(project_root / "notifier" / "notify.py"),
        ],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardErrorPath": "/tmp/pacer-notifier.err",  # noqa: S108
        # Catch-up run for a DIGEST_TIME missed while the machine was fully
        # off — notify.py's own date/time gate makes this safe to also fire
        # on an ordinary login (see module docstring).
        "RunAtLoad": True,
    }
    return plistlib.dumps(data)


def _unload(agent_path: Path) -> None:
    subprocess.run(  # noqa: S603
        [LAUNCHCTL, "unload", str(agent_path)], check=False, capture_output=True
    )


def _load(agent_path: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [LAUNCHCTL, "load", str(agent_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"launchctl load failed: {result.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install/refresh the pacer notifier launchd agent"
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="Unload and remove the agent"
    )
    args = parser.parse_args()

    if sys.platform != "darwin":
        raise SystemExit("The notifier agent is macOS-only (launchd).")

    project_root = Path(__file__).resolve().parent.parent
    agent_path = _agent_path()

    if args.uninstall:
        _unload(agent_path)
        agent_path.unlink(missing_ok=True)
        print(f"Removed {agent_path}")
        return

    digest_time = read_env(project_root / ".env").get("DIGEST_TIME", "08:00")
    hour, minute = _parse_time(digest_time)

    agent_path.parent.mkdir(parents=True, exist_ok=True)
    _unload(agent_path)  # no-op if not currently loaded
    agent_path.write_bytes(_build_plist(project_root, hour, minute))
    _load(agent_path)

    print(
        f"Installed {agent_path}\n"
        f"Fires daily at {hour:02d}:{minute:02d} (DIGEST_TIME={digest_time})."
    )


if __name__ == "__main__":
    main()
