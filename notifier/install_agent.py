#!/usr/bin/env python3
"""Generate, install, and (re)load the pacer notifier launchd agent.

Everything is derived from this checkout and `.env`, so the notifier's fire
time stays in sync with DIGEST_TIME and the paths never need hand-editing.
Re-run after changing DIGEST_TIME to resync the schedule.

    uv run python notifier/install_agent.py             # install/refresh + load
    uv run python notifier/install_agent.py --uninstall # unload + remove

Or via the Makefile: `make install-notifier` / `make uninstall-notifier`.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

LABEL = "com.pacer.notifier"
# The backend's daily job runs at DIGEST_TIME; fire the notifier a couple of
# minutes later so the digest it polls already reflects today's run.
NOTIFIER_BUFFER_MIN = 2
LAUNCHCTL = "/bin/launchctl"


def _read_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _notifier_time(digest_time: str) -> tuple[int, int]:
    fire = datetime.strptime(digest_time, "%H:%M") + timedelta(
        minutes=NOTIFIER_BUFFER_MIN
    )
    return fire.hour, fire.minute


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
        "RunAtLoad": False,
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

    digest_time = _read_env(project_root / ".env").get("DIGEST_TIME", "08:00")
    hour, minute = _notifier_time(digest_time)

    agent_path.parent.mkdir(parents=True, exist_ok=True)
    _unload(agent_path)  # no-op if not currently loaded
    agent_path.write_bytes(_build_plist(project_root, hour, minute))
    _load(agent_path)

    print(
        f"Installed {agent_path}\n"
        f"Fires daily at {hour:02d}:{minute:02d} "
        f"(DIGEST_TIME={digest_time} + {NOTIFIER_BUFFER_MIN}m)."
    )


if __name__ == "__main__":
    main()
