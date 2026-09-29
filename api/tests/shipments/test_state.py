from types import SimpleNamespace

import pytest

from app.envelope import AppError
from app.shipments.state import (
    MANUAL_TRANSITIONS,
    STATUS_RANK,
    ShipmentStatus,
    assert_manual_transition,
    missing_for_in_transit,
)

ALL = list(ShipmentStatus)


@pytest.mark.parametrize("to_status", ALL)
@pytest.mark.parametrize("from_status", ALL)
def test_manual_transition_matrix(from_status, to_status):
    if to_status in MANUAL_TRANSITIONS.get(from_status, set()):
        assert_manual_transition(from_status, to_status)
        return
    with pytest.raises(AppError) as err:
        assert_manual_transition(from_status, to_status)
    assert err.value.code == "INVALID_TRANSITION" and err.value.status == 409


def test_in_transit_to_customs_clearing_allowed():
    assert_manual_transition("IN_TRANSIT", "CUSTOMS_CLEARING")


def _shipment(**overrides):
    base = {"mbl_no": "MAEU123", "hbl_no": None, "carrier_id": 1, "pol_port_id": 2, "pod_port_id": 3, "eta": "2026-10-01"}
    return SimpleNamespace(**{**base, **overrides})


@pytest.mark.parametrize(("field", "missing"), [
    ("mbl_no", "bl_no"), ("carrier_id", "carrier_id"), ("pol_port_id", "pol_port_id"),
    ("pod_port_id", "pod_port_id"), ("eta", "eta"),
])
def test_in_transit_requires_field(field, missing):
    assert missing_for_in_transit(_shipment(**{field: None})) == [missing]


def test_in_transit_accepts_hbl_without_mbl():
    assert missing_for_in_transit(_shipment(mbl_no=None, hbl_no="HBL9")) == []


def test_status_rank_main_path_increasing():
    path = ["CREATED", "IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING", "CLEARED", "AT_WAREHOUSE", "DELIVERING", "COMPLETED"]
    ranks = [STATUS_RANK[ShipmentStatus(s)] for s in path]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
