from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.models import Status


@dataclass
class ProgressState:
    """Computable part of a progress row — everything except introduced_at."""

    status: Status
    interval_index: int | None
    last_reviewed_at: datetime | None
    next_review_at: datetime | None


def advance_state(
    state: ProgressState,
    solved_at: datetime,
    consolidation_intervals: list[int],
    maintenance_interval: int,
) -> ProgressState:
    """Apply one submission event, returning the next progress state.

    Pure function — no I/O, no settings import. Pass config values explicitly
    so tests stay DB- and env-free.
    """
    if state.status == Status.maintenance:
        return ProgressState(
            status=Status.maintenance,
            interval_index=state.interval_index,
            last_reviewed_at=solved_at,
            next_review_at=solved_at + timedelta(days=maintenance_interval),
        )

    # introduced or learning: advance through the consolidation chain
    # treat None as -1 so the first solve lands at index 0
    idx = -1 if state.interval_index is None else state.interval_index
    new_idx = min(idx + 1, len(consolidation_intervals) - 1)
    is_final = new_idx >= len(consolidation_intervals) - 1
    return ProgressState(
        status=Status.maintenance if is_final else Status.learning,
        interval_index=new_idx,
        last_reviewed_at=solved_at,
        next_review_at=solved_at + timedelta(days=consolidation_intervals[new_idx]),
    )


def compute_progress(
    submissions: list[datetime],
    consolidation_intervals: list[int],
    maintenance_interval: int,
) -> ProgressState:
    """Fold over ordered submission timestamps to compute current progress state.

    Starts from the `introduced` state (no submissions yet). Replaying the
    same submission list always yields the same result (idempotent recompute).
    """
    state = ProgressState(
        status=Status.introduced,
        interval_index=None,
        last_reviewed_at=None,
        next_review_at=None,
    )
    for solved_at in sorted(submissions):
        state = advance_state(
            state, solved_at, consolidation_intervals, maintenance_interval
        )
    return state
