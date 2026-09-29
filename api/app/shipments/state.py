"""Vòng đời lô hàng (spec mục 2 "Vòng đời trạng thái"): cạnh chuyển tay, thứ tự mốc container."""

from enum import StrEnum
from typing import Protocol

from app.envelope import AppError


class ShipmentStatus(StrEnum):
    CREATED = "CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    CUSTOMS_CLEARING = "CUSTOMS_CLEARING"
    CLEARED = "CLEARED"
    AT_WAREHOUSE = "AT_WAREHOUSE"
    DELIVERING = "DELIVERING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


S = ShipmentStatus

STATUS_RANK = {S.CREATED: 0, S.IN_TRANSIT: 1, S.ARRIVED: 2, S.CUSTOMS_CLEARING: 3, S.CLEARED: 4,
               S.AT_WAREHOUSE: 5, S.DELIVERING: 6, S.COMPLETED: 7}

# Chỉ các cạnh nhân viên bấm tay; từ CLEARED trở đi hệ thống tự chuyển, CANCELLED có endpoint riêng.
MANUAL_TRANSITIONS = {
    S.CREATED: {S.IN_TRANSIT},
    S.IN_TRANSIT: {S.ARRIVED, S.CUSTOMS_CLEARING},
    S.ARRIVED: {S.CUSTOMS_CLEARING},
    S.CUSTOMS_CLEARING: {S.CLEARED},
}

STATUS_LABEL_VI = {
    S.CREATED: "Mới tạo", S.IN_TRANSIT: "Đang vận chuyển", S.ARRIVED: "Đã đến cảng",
    S.CUSTOMS_CLEARING: "Đang thông quan", S.CLEARED: "Đã thông quan", S.AT_WAREHOUSE: "Đã về kho",
    S.DELIVERING: "Đang giao", S.COMPLETED: "Hoàn tất", S.CANCELLED: "Đã huỷ",
}

DISCHARGE_ALLOWED = frozenset({S.ARRIVED, S.CUSTOMS_CLEARING, S.CLEARED})
CONTAINER_MILESTONE_ORDER = ("DISCHARGED", "GATE_OUT_FULL", "EMPTY_RETURNED")

IN_TRANSIT_FIELD_LABELS = {
    "bl_no": "số B/L (MBL hoặc HBL)", "carrier_id": "hãng tàu", "pol_port_id": "cảng xếp",
    "pod_port_id": "cảng dỡ", "eta": "ETA",
}


class ShipmentLike(Protocol):
    mbl_no: str | None
    hbl_no: str | None
    carrier_id: int | None
    pol_port_id: int | None
    pod_port_id: int | None
    eta: object | None


def assert_manual_transition(from_status: str, to_status: str) -> None:
    if S(to_status) not in MANUAL_TRANSITIONS.get(S(from_status), set()):
        raise AppError(
            "INVALID_TRANSITION",
            f"Không chuyển được từ {STATUS_LABEL_VI[S(from_status)]} sang {STATUS_LABEL_VI[S(to_status)]}",
            409,
        )


def missing_for_in_transit(shipment: ShipmentLike) -> list[str]:
    """Các trường còn thiếu để sang IN_TRANSIT, theo thứ tự cố định."""
    checks = [
        ("bl_no", shipment.mbl_no or shipment.hbl_no),
        ("carrier_id", shipment.carrier_id),
        ("pol_port_id", shipment.pol_port_id),
        ("pod_port_id", shipment.pod_port_id),
        ("eta", shipment.eta),
    ]
    return [key for key, value in checks if not value]
