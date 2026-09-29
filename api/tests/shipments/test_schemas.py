import pytest
from pydantic import ValidationError

from app.shipments.schemas import CancelIn, ShipmentCreate, ShipmentUpdate


def test_create_rejects_lcl_container_to_door():
    with pytest.raises(ValidationError, match="LCL"):
        ShipmentCreate(load_type="LCL", delivery_mode="CONTAINER_TO_DOOR", customer_id=1)


def test_create_rejects_etd_after_eta():
    with pytest.raises(ValidationError, match="ETD"):
        ShipmentCreate(load_type="FCL", delivery_mode="VIA_WAREHOUSE", customer_id=1, etd="2026-10-10", eta="2026-10-01")


def test_update_requires_version():
    with pytest.raises(ValidationError):
        ShipmentUpdate(mbl_no="X")


def test_update_tracks_explicit_null():
    data = ShipmentUpdate(version=1, mbl_no=None)
    assert "mbl_no" in data.model_fields_set and "hbl_no" not in data.model_fields_set


def test_update_forbids_status_and_code():
    with pytest.raises(ValidationError):
        ShipmentUpdate(version=1, status="CLEARED")


def test_cancel_reason_min_3_chars():
    assert CancelIn(reason="  khách huỷ ").reason == "khách huỷ"
    with pytest.raises(ValidationError):
        CancelIn(reason=" ab ")


def test_bl_no_normalized_and_capped():
    data = ShipmentCreate(load_type="FCL", delivery_mode="VIA_WAREHOUSE", customer_id=1, mbl_no=" maeu123 ", hbl_no="  ")
    assert data.mbl_no == "MAEU123" and data.hbl_no is None
    with pytest.raises(ValidationError):
        ShipmentCreate(load_type="FCL", delivery_mode="VIA_WAREHOUSE", customer_id=1, mbl_no="A" * 36)


def test_total_packages_not_negative():
    with pytest.raises(ValidationError):
        ShipmentCreate(load_type="FCL", delivery_mode="VIA_WAREHOUSE", customer_id=1, total_packages=-1)
