from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Status
from app.services.progress import ProgressState, advance_state, compute_progress

INTERVALS = [3, 14, 45]
MAINTENANCE = 90

T0 = datetime(2025, 1, 1, tzinfo=UTC)


def days(n: int) -> datetime:
    from datetime import timedelta

    return T0 + timedelta(days=n)


def initial_state() -> ProgressState:
    return ProgressState(
        status=Status.introduced,
        interval_index=None,
        last_reviewed_at=None,
        next_review_at=None,
    )


def test_no_submissions_stays_introduced() -> None:
    state = compute_progress([], INTERVALS, MAINTENANCE)
    assert state.status == Status.introduced
    assert state.interval_index is None
    assert state.last_reviewed_at is None
    assert state.next_review_at is None


def test_first_solve_uses_interval_0() -> None:
    state = advance_state(initial_state(), T0, INTERVALS, MAINTENANCE)
    assert state.status == Status.learning
    assert state.interval_index == 0
    assert state.last_reviewed_at == T0
    assert state.next_review_at == days(3)


def test_second_solve_uses_interval_1() -> None:
    s1 = advance_state(initial_state(), T0, INTERVALS, MAINTENANCE)
    s2 = advance_state(s1, days(3), INTERVALS, MAINTENANCE)
    assert s2.status == Status.learning
    assert s2.interval_index == 1
    assert s2.next_review_at == days(3 + 14)


def test_third_solve_reaches_maintenance() -> None:
    s1 = advance_state(initial_state(), T0, INTERVALS, MAINTENANCE)
    s2 = advance_state(s1, days(3), INTERVALS, MAINTENANCE)
    s3 = advance_state(s2, days(3 + 14), INTERVALS, MAINTENANCE)
    assert s3.status == Status.maintenance
    assert s3.interval_index == 2
    assert s3.next_review_at == days(3 + 14 + 45)


def test_maintenance_solve_resets_to_90d() -> None:
    s1 = advance_state(initial_state(), T0, INTERVALS, MAINTENANCE)
    s2 = advance_state(s1, days(3), INTERVALS, MAINTENANCE)
    s3 = advance_state(s2, days(3 + 14), INTERVALS, MAINTENANCE)
    s4 = advance_state(s3, days(3 + 14 + 45), INTERVALS, MAINTENANCE)
    assert s4.status == Status.maintenance
    assert s4.next_review_at == days(3 + 14 + 45 + 90)
    assert s4.interval_index == 2  # unchanged in maintenance


def test_compute_progress_fold_matches_manual_chain() -> None:
    timestamps = [T0, days(3), days(17), days(62)]
    result = compute_progress(timestamps, INTERVALS, MAINTENANCE)
    assert result.status == Status.maintenance
    assert result.last_reviewed_at == days(62)
    assert result.next_review_at == days(62 + 90)


def test_idempotent_recompute() -> None:
    timestamps = [T0, days(3), days(17)]
    first = compute_progress(timestamps, INTERVALS, MAINTENANCE)
    second = compute_progress(timestamps, INTERVALS, MAINTENANCE)
    assert first == second
