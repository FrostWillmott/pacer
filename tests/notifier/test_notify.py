from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import httpx
import notify
import pytest


class _FixedDateTime(datetime):
    """Stand-in for `datetime` with a frozen `now()`, used to control
    `main()`'s "is it past DIGEST_TIME yet" gate without touching the wall
    clock. Subclassing keeps `strptime`/`combine`/etc. working as normal."""

    _fixed: datetime

    @classmethod
    def now(cls, tz: object = None) -> _FixedDateTime:
        return cls._fixed  # type: ignore[return-value]


def _freeze_now(monkeypatch: pytest.MonkeyPatch, when: datetime) -> None:
    _FixedDateTime._fixed = when
    monkeypatch.setattr(notify, "datetime", _FixedDateTime)


def _set_project_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    # main() derives project_root from Path(__file__).parent.parent; faking
    # notify's own __file__ (rather than patching Path itself, which would
    # corrupt every Path instance in the process) redirects it to tmp_path.
    monkeypatch.setattr(notify, "__file__", str(root / "notifier" / "notify.py"))


def _stub_job_success(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Wires main()'s HTTP-touching helpers to a successful run and returns
    the list of HTTP-ish calls made, in order, for assertions."""
    calls: list[str] = []
    monkeypatch.setattr(notify, "_wait_for_backend", lambda base_url: True)

    def _fake_post(url: str, timeout: float) -> httpx.Response:
        calls.append(f"post:{url}")
        return httpx.Response(200, request=httpx.Request("POST", url))

    def _fake_get(url: str, timeout: float) -> httpx.Response:
        calls.append(f"get:{url}")
        return httpx.Response(
            200, json={"new": {}, "review": []}, request=httpx.Request("GET", url)
        )

    def _fake_notify(message: str, *, open_url: str | None = None) -> None:
        calls.append("notify")

    # Patch the shared `httpx` module object directly (`notify.httpx is httpx`)
    # rather than `notify.httpx.post` — mypy's strict no-implicit-reexport
    # check rejects reaching through `notify` for a name it merely imports.
    monkeypatch.setattr(httpx, "post", _fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get)
    monkeypatch.setattr(notify, "_notify", _fake_notify)
    return calls


class TestLastRunDate:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert notify._last_run_date(tmp_path / "does-not-exist") is None

    def test_corrupt_content_returns_none(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state"
        state_path.write_text("not-a-date")

        assert notify._last_run_date(state_path) is None

    def test_valid_iso_date_is_parsed(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state"
        state_path.write_text("2026-07-23")

        assert notify._last_run_date(state_path) == date(2026, 7, 23)


class TestRecordRunDate:
    def test_writes_iso_date(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state"

        notify._record_run_date(state_path, date(2026, 7, 23))

        assert state_path.read_text() == "2026-07-23"

    def test_swallows_oserror_on_unwritable_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A directory can't be written to as a file — triggers a real OSError.
        unwritable = tmp_path / "not-a-file"
        unwritable.mkdir()

        notify._record_run_date(unwritable, date(2026, 7, 23))  # must not raise

        assert "failed to write state file" in capsys.readouterr().err


class TestMainCatchUpGating:
    def test_noop_when_todays_job_already_ran(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_path = tmp_path / notify._STATE_FILE_NAME
        state_path.write_text("2026-07-23")
        _set_project_root(monkeypatch, tmp_path)
        monkeypatch.setattr(notify, "read_env", lambda path: {"DIGEST_TIME": "08:00"})
        wait_called: list[bool] = []

        def _wait_for_backend(base_url: str) -> bool:
            wait_called.append(True)
            return True

        monkeypatch.setattr(notify, "_wait_for_backend", _wait_for_backend)
        _freeze_now(monkeypatch, datetime(2026, 7, 23, 9, 0, 0))

        notify.main()

        assert wait_called == []  # never got past the same-day gate
        assert state_path.read_text() == "2026-07-23"  # untouched

    def test_noop_when_run_at_load_fires_before_digest_time(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_path = tmp_path / notify._STATE_FILE_NAME
        _set_project_root(monkeypatch, tmp_path)
        monkeypatch.setattr(notify, "read_env", lambda path: {"DIGEST_TIME": "08:00"})
        wait_called: list[bool] = []

        def _wait_for_backend(base_url: str) -> bool:
            wait_called.append(True)
            return True

        monkeypatch.setattr(notify, "_wait_for_backend", _wait_for_backend)
        _freeze_now(monkeypatch, datetime(2026, 7, 23, 7, 0, 0))  # before 08:00

        notify.main()

        assert wait_called == []  # ordinary early boot — waits for the calendar trigger
        assert not state_path.exists()

    def test_catch_up_run_records_todays_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_path = tmp_path / notify._STATE_FILE_NAME
        state_path.write_text("2026-07-22")  # yesterday — job never ran today
        _set_project_root(monkeypatch, tmp_path)
        monkeypatch.setattr(notify, "read_env", lambda path: {"DIGEST_TIME": "08:00"})
        calls = _stub_job_success(monkeypatch)
        _freeze_now(monkeypatch, datetime(2026, 7, 23, 9, 0, 0))  # past DIGEST_TIME

        notify.main()

        assert state_path.read_text() == "2026-07-23"
        assert calls[0].startswith("post:")  # daily-job triggered before digest fetch

    def test_state_not_recorded_when_daily_job_trigger_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_path = tmp_path / notify._STATE_FILE_NAME
        _set_project_root(monkeypatch, tmp_path)
        monkeypatch.setattr(notify, "read_env", lambda path: {"DIGEST_TIME": "08:00"})
        monkeypatch.setattr(notify, "_wait_for_backend", lambda base_url: True)

        def _failing_post(url: str, timeout: float) -> httpx.Response:
            return httpx.Response(500, request=httpx.Request("POST", url))

        def _noop_notify(message: str, *, open_url: str | None = None) -> None:
            return None

        monkeypatch.setattr(httpx, "post", _failing_post)
        monkeypatch.setattr(notify, "_notify", _noop_notify)
        _freeze_now(monkeypatch, datetime(2026, 7, 23, 9, 0, 0))

        notify.main()

        assert not state_path.exists()  # a failed trigger must not be recorded as a run
