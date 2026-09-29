"""Ghi `Dataset` (từ `seed_dataset.build_dataset`) vào DB bằng ORM. Không commit, không ghi audit."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fpdf import FPDF
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.models import User
from app.catalog.models import Carrier, Customer, Driver, Port, Truck, Warehouse
from app.documents.models import DEFAULT_VISIBLE_TYPES, DocType, Document
from app.documents.storage import path_for
from app.finance.models import Charge
from app.finance.service import compute_amount_vnd
from app.freetime.models import FreeTimeRule, FreeTimeTier
from app.lastmile.models import LastMileEvent, LastMileOrder
from app.shipments.models import Container, ContainerEvent, CustomsDeclaration, Shipment, ShipmentEvent
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.state import derive_status as derive_trucking
from scripts.seed_dataset import DRIVER_COUNT, ChargePlan, Dataset, ShipmentPlan, vn

RULE_CARRIERS = ("MAEU", "REGU")  # ONEY cố ý không có quy tắc để có đồng hồ NO_RULE
RULE_PORTS = ("VNSGN", "VNHPH", "VNCMT")
FX_USD_VND = 25_400
FLAGGED_EVERY = 3  # cứ 3 lô có 1 lô chi phí DEM/DET lệch quá 20% so với ước tính


def _pdf(title: str, detail: str) -> bytes:
    pdf = FPDF()
    pdf.set_creation_date(datetime(2026, 1, 1, tzinfo=UTC))
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "SIMULATED DOCUMENT - CHUNG TU MO PHONG", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, f"{title}\n{detail}")
    return bytes(pdf.output())


def _store_pdf(title: str, detail: str) -> tuple[str, int]:
    data = _pdf(title, detail)
    sha = hashlib.sha256(data).hexdigest()
    path = path_for(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha, len(data)


def seed_free_time_rules(db: Session) -> None:
    """Quy tắc mẫu: DEM free 5 ngày (20GP: 4), DET free 7 ngày; bậc giá tính bằng cent USD, hiệu lực 2026-01-01."""
    carriers = {c.code: c for c in db.scalars(select(Carrier))}
    ports = {p.code: p for p in db.scalars(select(Port))}
    for carrier in RULE_CARRIERS:
        for port in RULE_PORTS:
            for container_type, dem_days in (("40HC", 5), ("20GP", 4)):
                dem_tiers = [(dem_days + 1, dem_days + 5, 2000), (dem_days + 6, None, 4000)]
                for fee, days, tiers in (("DEM", dem_days, dem_tiers), ("DET", 7, [(8, None, 1000)])):
                    rule = FreeTimeRule(carrier_id=carriers[carrier].id, port_id=ports[port].id,
                                        container_type=container_type, fee_type=fee, free_days=days,
                                        effective_from=date(2026, 1, 1))
                    db.add(rule)
                    db.flush()
                    db.add_all(FreeTimeTier(rule_id=rule.id, from_day=a, to_day=b, rate_amount=rate, currency="USD")
                               for a, b, rate in tiers)


class _Catalog:
    def __init__(self, db: Session):
        self.customers = list(db.scalars(select(Customer).order_by(Customer.id)))
        self.carriers = {c.code: c for c in db.scalars(select(Carrier))}
        self.ports = {p.code: p for p in db.scalars(select(Port))}
        self.warehouse = db.scalars(select(Warehouse).order_by(Warehouse.id)).first()
        self.drivers = list(db.scalars(select(Driver).order_by(Driver.id)))[:DRIVER_COUNT]
        self.trucks = {t.trucker_id: t for t in db.scalars(select(Truck).order_by(Truck.id).limit(50))}
        self.docs = db.scalar(select(User).where(User.email == "docs@fwdflow.local"))
        self.dispatch = db.scalar(select(User).where(User.email == "dispatch@fwdflow.local"))
        self.driver_user = db.scalar(select(User).where(User.role == "DRIVER"))


def _write_shipment(db: Session, cat: _Catalog, plan: ShipmentPlan, index: int) -> tuple[Shipment, list[Container]]:
    sc, staff = plan.scenario, cat.docs
    status = plan.transitions[-1][0]
    shipment = Shipment(
        load_type=sc.load_type, delivery_mode=sc.delivery_mode, customer_id=cat.customers[sc.customer].id,
        staff_id=staff.id, carrier_id=cat.carriers[plan.carrier].id, pol_port_id=cat.ports[plan.pol].id,
        pod_port_id=cat.ports[plan.pod].id, dest_warehouse_id=cat.warehouse.id,
        mbl_no=f"MBL{index + 1:07d}" if sc.load_type == "FCL" else None, hbl_no=f"HBL{index + 1:07d}",
        vessel="EVER DEMO", voyage=f"{index % 90 + 10:03d}E", etd=plan.etd, eta=plan.eta, claims_fta=sc.fta,
        do_no=f"DO{index + 1:06d}" if plan.do_valid_until else None, do_valid_until=plan.do_valid_until,
        total_packages=plan.total_packages, status=status)
    db.add(shipment)
    db.flush()
    previous = None
    for to_status, when, auto in plan.transitions:
        db.add(ShipmentEvent(shipment_id=shipment.id, kind="TRANSITION", from_status=previous, to_status=to_status,
                             occurred_at=when, recorded_at=when, actor_id=None if auto else staff.id,
                             reason="Tự chuyển (dữ liệu mô phỏng)" if auto else None))
        previous = to_status
    containers = []
    for c in plan.containers:
        container = Container(shipment_id=shipment.id, container_no=c.container_no, container_type=c.container_type)
        db.add(container)
        db.flush()
        for kind, when in (("DISCHARGED", c.discharged), ("GATE_OUT_FULL", c.gate_out), ("EMPTY_RETURNED", c.returned)):
            if when:
                db.add(ContainerEvent(container_id=container.id, kind=kind, occurred_at=when, recorded_at=when,
                                      actor_id=staff.id))
                container.status = kind
        containers.append(container)
    if plan.declaration:
        number, registered, cleared = plan.declaration
        db.add(CustomsDeclaration(shipment_id=shipment.id, declaration_no=number, type_code="A11",
                                  registered_at=registered, lane="GREEN" if cleared else None, cleared_at=cleared))
    for doc_type in plan.documents:
        sha, size = _store_pdf(f"{doc_type} - shipment #{index + 1}", f"Container/lo: {index + 1}")
        db.add(Document(shipment_id=shipment.id, doc_type=doc_type, file_sha256=sha, mime="application/pdf",
                        size_bytes=size, pages=1, visible_to_customer=DocType(doc_type) in DEFAULT_VISIBLE_TYPES,
                        uploaded_by=staff.id))
    db.flush()
    return shipment, containers


def _write_trucking(db: Session, cat: _Catalog, plan: ShipmentPlan, shipment: Shipment, containers: list[Container],
                    index: int) -> None:
    for t in plan.trucking:
        driver = cat.drivers[(index + t.container_index) % len(cat.drivers)]
        truck = cat.trucks[driver.trucker_id]
        order = TruckingOrder(
            shipment_id=shipment.id, container_id=containers[t.container_index].id, kind=t.kind,
            trucker_id=driver.trucker_id, truck_id=truck.id, driver_id=driver.id,
            pickup_location="Cảng Cát Lái (VNSGN)", drop_location=cat.warehouse.address, planned_at=t.planned_at,
            created_by_id=cat.dispatch.id)
        db.add(order)
        db.flush()
        rows = []
        for kind, when in t.events:
            actor = cat.dispatch.id if kind == "ASSIGNED" else (
                cat.driver_user.id if driver.id == cat.drivers[0].id and cat.driver_user else None)
            row = TruckingOrderEvent(order_id=order.id, kind=kind, occurred_at=when, recorded_at=when, actor_id=actor,
                                     truck_id=truck.id, driver_id=driver.id)
            db.add(row)
            rows.append(row)
        db.flush()
        order.status = derive_trucking(rows)


def _write_orders(db: Session, cat: _Catalog, plan: ShipmentPlan, shipment: Shipment) -> None:
    for o in plan.orders:
        driver = cat.drivers[o.driver_index] if o.driver_index is not None else None
        order = LastMileOrder(shipment_id=shipment.id, tracking_code=o.tracking_code, recipient_name=o.recipient_name,
                              recipient_phone=o.recipient_phone, address=o.address, packages=o.packages,
                              planned_date=o.planned_date, driver_id=driver.id if driver else None, status=o.status,
                              created_by=cat.dispatch.id)
        db.add(order)
        db.flush()
        for kind, when in o.events:
            db.add(LastMileEvent(order_id=order.id, kind=kind, occurred_at=when, recorded_at=when,
                                 actor_id=cat.dispatch.id if kind in ("CREATED", "ASSIGNED", "CANCELLED") else None,
                                 driver_id=driver.id if kind == "ASSIGNED" and driver else None))


def _add_charge(db: Session, shipment: Shipment, plan: ChargePlan, actor: User) -> None:
    amount_vnd, fx = compute_amount_vnd(plan.amount, plan.currency, Decimal(plan.fx_rate) if plan.fx_rate else None)
    db.add(Charge(shipment_id=shipment.id, direction=plan.direction, category=plan.category, amount=plan.amount,
                  currency=plan.currency, fx_rate=fx, amount_vnd=amount_vnd, charge_date=plan.charge_date,
                  created_by=actor.id))


def _add_demdet_costs(db: Session, cat: _Catalog, as_of: date, shipments: list[Shipment]) -> None:
    """Chi phí DEM thực tế bám ước tính theo bậc giá: 1/3 lô lệch quá 20% (gắn cờ), còn lại lệch nhẹ."""
    estimate: dict[int, int] = {}
    for row in db.execute(text("SELECT shipment_id, fee_amount, fee_currency FROM container_freetime(:d)"),
                          {"d": as_of}).mappings():
        if row["fee_amount"]:
            vnd = row["fee_amount"] if row["fee_currency"] == "VND" else compute_amount_vnd(
                row["fee_amount"], "USD", Decimal(FX_USD_VND))[0]
            estimate[row["shipment_id"]] = estimate.get(row["shipment_id"], 0) + vnd
    for n, shipment in enumerate(s for s in shipments if estimate.get(s.id)):
        actual = estimate[shipment.id] * 3 // 2 + 1 if n % FLAGGED_EVERY == 0 else estimate[shipment.id] * 95 // 100
        db.add(Charge(shipment_id=shipment.id, direction="COST", category="DEM", amount=actual, currency="VND",
                      fx_rate=Decimal(1), amount_vnd=actual, charge_date=as_of, created_by=cat.docs.id))


def _driver_scenario(db: Session, cat: _Catalog, as_of: date, written: list[tuple[Shipment, list[Container]]]) -> int:
    """3 lệnh lấy hàng đầy đã phân công cho tài xế demo (đăng nhập bằng SĐT), hôm nay 08:00, 10:00, 13:00."""
    driver = cat.drivers[0]
    cleared = [c for s, cs in written if s.status == "CLEARED" for c in cs]
    made = 0
    for container, hour in zip(cleared, (8, 10, 13), strict=False):
        order = TruckingOrder(
            shipment_id=container.shipment_id, container_id=container.id, kind="PICKUP_FULL",
            trucker_id=driver.trucker_id, truck_id=cat.trucks[driver.trucker_id].id, driver_id=driver.id,
            pickup_location="Cảng Cát Lái (VNSGN)", drop_location=cat.warehouse.address,
            planned_at=vn(as_of, hour), status="ASSIGNED", created_by_id=cat.dispatch.id)
        db.add(order)
        db.flush()
        when = vn(as_of - timedelta(days=1), 16)
        db.add(TruckingOrderEvent(order_id=order.id, kind="ASSIGNED", occurred_at=when, recorded_at=when,
                                  actor_id=cat.dispatch.id, truck_id=order.truck_id, driver_id=driver.id))
        made += 1
    return made


def write_dataset(db: Session, dataset: Dataset) -> dict[str, int]:
    """Ghi toàn bộ dữ liệu; trả bộ đếm để in ra. Danh mục + tài khoản phải có sẵn (`seed_demo.seed`)."""
    seed_free_time_rules(db)
    cat = _Catalog(db)
    written = []
    for index, plan in enumerate(dataset.shipments):
        shipment, containers = _write_shipment(db, cat, plan, index)
        _write_trucking(db, cat, plan, shipment, containers, index)
        _write_orders(db, cat, plan, shipment)
        for charge in plan.charges:
            _add_charge(db, shipment, charge, cat.docs)
        written.append((shipment, containers))
    db.flush()
    _add_demdet_costs(db, cat, dataset.as_of, [s for s, _ in written])
    driver_orders = _driver_scenario(db, cat, dataset.as_of, written)
    db.flush()
    return {"shipments": len(written), "containers": dataset.container_count, "last_mile_orders": dataset.order_count,
            "charges": db.scalar(text("SELECT count(*) FROM charges")), "driver_orders": driver_orders}

