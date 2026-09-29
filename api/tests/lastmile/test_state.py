from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.envelope import AppError
from app.lastmile.state import TRANSITIONS, LastMileStatus, assert_transition, derive_status

ALL = list(LastMileStatus)
VALID = [(a, b) for a, targets in TRANSITIONS.items() for b in targets]
INVALID = [(a, b) for a in ALL for b in ALL if a != b and b not in TRANSITIONS[a]]
T0 = datetime(2026, 12, 1, tzinfo=UTC)


def _event(i, kind, adjusts=None):
    at = T0 + timedelta(minutes=i)
    return SimpleNamespace(id=i, kind=kind, occurred_at=at, recorded_at=at, actor_id=None, adjusts_event_id=adjusts)


def test_counts_match_spec():
    assert len(VALID) == 8 and len(INVALID) == 34


@pytest.mark.parametrize(("from_", "to"), VALID)
def test_valid_edge_accepted(from_, to):
    assert_transition(from_, to)


@pytest.mark.parametrize(("from_", "to"), INVALID)
def test_invalid_edge_rejected(from_, to):
    with pytest.raises(AppError) as info:
        assert_transition(from_, to)
    assert (info.value.code, info.value.status) == ("INVALID_TRANSITION", 409)


def test_derive_status_ignores_reassigned_and_voided():
    events = [_event(1, "CREATED"), _event(2, "ASSIGNED"), _event(3, "REASSIGNED"), _event(4, "PICKED_UP"),
              _event(5, "DELIVERED"), _event(6, "VOID", adjusts=5)]
    assert derive_status(events) == LastMileStatus.PICKED_UP
