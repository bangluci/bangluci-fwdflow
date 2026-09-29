from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.envelope import AppError
from app.trucking.state import (
    REASSIGNABLE,
    TRANSITIONS,
    TruckingStatus,
    assert_can_reassign,
    assert_transition,
    derive_status,
)

ALL = list(TruckingStatus)
VALID = [(a, b) for a, targets in TRANSITIONS.items() for b in targets]
INVALID = [(a, b) for a in ALL for b in ALL if b not in TRANSITIONS[a]]
T0 = datetime(2026, 11, 26, tzinfo=UTC)


def event(i, kind, adjusts=None):
    return SimpleNamespace(id=i, kind=kind, occurred_at=T0 + timedelta(minutes=i), recorded_at=T0 + timedelta(minutes=i),
                           actor_id=None, adjusts_event_id=adjusts)


@pytest.mark.parametrize(("from_", "to"), VALID)
def test_valid_edge_accepted(from_, to):
    assert_transition(from_, to)


@pytest.mark.parametrize(("from_", "to"), INVALID)
def test_invalid_edge_rejected(from_, to):
    with pytest.raises(AppError) as info:
        assert_transition(from_, to)
    assert info.value.code == "INVALID_TRANSITION" and info.value.status == 409


@pytest.mark.parametrize("status", ALL)
def test_reassign_allowed_only_when_assigned_or_started(status):
    if status in REASSIGNABLE:
        assert_can_reassign(status)
    else:
        with pytest.raises(AppError, match="đổi xe"):
            assert_can_reassign(status)


def test_derive_status_ignores_reassigned():
    events = [event(1, "ASSIGNED"), event(2, "STARTED"), event(3, "REASSIGNED")]
    assert derive_status(events) == TruckingStatus.STARTED


def test_derive_status_after_void_returns_previous():
    events = [event(1, "ASSIGNED"), event(2, "STARTED"), event(3, "VOID", adjusts=2)]
    assert derive_status(events) == TruckingStatus.ASSIGNED
    assert derive_status([]) == TruckingStatus.PLANNED
