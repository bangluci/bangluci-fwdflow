"""Fixture `ft` dựng quy tắc, container và override free time; đọc kết quả từ `container_freetime(as_of)`."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.catalog.models import Carrier, Port
from app.freetime.models import FreeTimeRule, FreeTimeTier, ShipmentFreeTimeOverride

RCL, MSK = "REGU", "MAEU"


def at(day: str) -> datetime:
    """12:00 giờ Việt Nam của `day` (YYYY-MM-DD), tránh nhập nhằng ranh giới ngày."""
    return datetime.fromisoformat(f"{day}T05:00:00+00:00").astimezone(UTC)


@pytest.fixture
def ft(db, make_shipment, make_container):
    carriers, ports = {}, {}

    def carrier(code: str = RCL) -> Carrier:
        if code not in carriers:
            carriers[code] = db.query(Carrier).filter_by(code=code).one_or_none() or Carrier(code=code, name=code)
            db.add(carriers[code])
            db.flush()
        return carriers[code]

    def port(code: str = "VNSGN") -> Port:
        if code not in ports:
            ports[code] = db.query(Port).filter_by(code=code).one_or_none() or Port(code=code, name=code)
            db.add(ports[code])
            db.flush()
        return ports[code]

    def rules(carrier_code, port_code, container_type, effective_from="2026-01-01", dem=None, det=None,
              combined=None):
        """Mỗi loại phí dạng `(free_days, [(from_day, to_day, rate, currency), ...])`."""
        made = []
        for fee_type, spec in (("DEM", dem), ("DET", det), ("COMBINED", combined)):
            if spec is None:
                continue
            free_days, tiers = spec
            rule = FreeTimeRule(carrier_id=carrier(carrier_code).id, port_id=port(port_code).id,
                                container_type=container_type, fee_type=fee_type, free_days=free_days,
                                effective_from=datetime.fromisoformat(effective_from).date())
            db.add(rule)
            db.flush()
            db.add_all(FreeTimeTier(rule_id=rule.id, from_day=a, to_day=b, rate_amount=rate, currency=cur)
                       for a, b, rate, cur in tiers)
            made.append(rule)
        db.flush()
        return made

    def container(status="ARRIVED", eta="2026-11-01", carrier_code=RCL, port_code="VNSGN", container_type="40HC",
                  milestones=None, load_type="FCL",
                  **shipment_fields):
        shipment = make_shipment(status=status, load_type=load_type, carrier_id=carrier(carrier_code).id,
                                 pod_port_id=port(port_code).id, eta=datetime.fromisoformat(eta).date(),
                                 **shipment_fields)
        return make_container(shipment, container_type=container_type,
                              milestones={kind: day if isinstance(day, datetime) else at(day)
                                                 for kind, day in (milestones or {}).items()})

    def override(shipment_id, fee_type, free_days, source="DO"):
        row = ShipmentFreeTimeOverride(shipment_id=shipment_id, fee_type=fee_type, free_days=free_days, source=source)
        db.add(row)
        db.flush()
        return row

    def rows(as_of, container_row=None):
        sql = "SELECT * FROM container_freetime(:as_of)"
        params = {"as_of": datetime.fromisoformat(as_of).date() if isinstance(as_of, str) else as_of}
        if container_row is not None:
            sql += " WHERE container_id = :cid"
            params["cid"] = container_row.id
        return {row["fee_type"]: row for row in db.execute(text(sql), params).mappings()}

    def standard_rules():
        """Bộ quy tắc mẫu R1..R5 (hãng tàu RCL, hiệu lực 2026-01-01, USD tính bằng cent)."""
        rules(RCL, "VNSGN", "40HC", dem=(5, [(6, 10, 2000, "USD"), (11, None, 4000, "USD")]),
              det=(7, [(8, None, 1000, "USD")]))
        rules(RCL, "VNHPH", "40HC", combined=(10, [(11, 20, 1500, "USD"), (21, None, 3000, "USD")]))
        rules(RCL, "VNCMT", "20GP", dem=(4, [(5, None, 500000, "VND")]), det=(4, [(5, None, 300000, "VND")]))
        rules(RCL, "VNSGN", "20GP", dem=(5, [(6, None, 1500, "USD")]), det=(7, [(8, None, 800, "USD")]))
        rules(RCL, "VNHPH", "20GP", dem=(3, [(4, None, 1500, "USD")]), det=(5, [(6, None, 800, "USD")]))

    return SimpleNamespace(carrier=carrier, port=port, rules=rules, container=container, override=override,
                           rows=rows, standard_rules=standard_rules, at=at)
