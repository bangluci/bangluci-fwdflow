from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.catalog.models import Customer
from app.documents.checklist import missing_documents
from app.lastmile.models import LastMileEvent, LastMileOrder
from app.lastmile.state import POOL_EXCLUDED
from app.lastmile.state import derive_status as derive_last_mile
from app.notifications.reminder import collect_reminders, do_expiring_shipments
from app.shipments.iso6346 import is_valid_container_no
from app.shipments.models import Container, ContainerEvent, Shipment, ShipmentEvent
from app.trucking.models import TruckingOrder, TruckingOrderEvent
from app.trucking.state import derive_status as derive_trucking
from scripts.seed_dataset import build_dataset
from scripts.seed_demo import run
from tests.conftest import TEST_PASSWORD

AS_OF = date(2026, 12, 15)
MILESTONES = ("DISCHARGED", "GATE_OUT_FULL", "EMPTY_RETURNED")


@pytest.fixture
def seeded(db):
    assert run(db, seed_value=1, reset=True, env="dev", password=TEST_PASSWORD, size="small", as_of=AS_OF) == 0
    db.execute(text("SELECT set_config('app.as_of', :d, true)"), {"d": AS_OF.isoformat()})


def test_build_dataset_is_deterministic():
    assert build_dataset(1, "small", AS_OF) == build_dataset(1, "small", AS_OF)
    assert build_dataset(1, "small", AS_OF) != build_dataset(2, "small", AS_OF)
    full = build_dataset(1, "full", AS_OF)
    assert (len(full.shipments), full.container_count, full.order_count) == (200, 500, 2000)
    assert sum(s.scenario.load_type == "LCL" for s in full.shipments) == 40
    assert sum(s.scenario.delivery_mode == "CONTAINER_TO_DOOR" for s in full.shipments) == 30


def test_seed_small_counts_and_invariants(db, seeded):
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    assert (count(Shipment), count(Container), count(LastMileOrder)) == (20, 50, 200)
    for shipment in db.scalars(select(Shipment)):
        events = db.scalars(select(ShipmentEvent).where(ShipmentEvent.shipment_id == shipment.id)).all()
        latest = max((e for e in events if e.kind == "TRANSITION"), key=lambda e: (e.occurred_at, e.id))
        assert shipment.status == latest.to_status
        if shipment.status in ("CLEARED", "AT_WAREHOUSE", "DELIVERING", "COMPLETED"):
            assert missing_documents(db, shipment) == []
        pool = sum(o.packages for o in db.scalars(select(LastMileOrder).where(
            LastMileOrder.shipment_id == shipment.id, LastMileOrder.status.notin_(list(POOL_EXCLUDED)))))
        assert pool <= shipment.total_packages
    for container in db.scalars(select(Container)):
        assert is_valid_container_no(container.container_no)
        events = db.scalars(select(ContainerEvent).where(ContainerEvent.container_id == container.id)
                            .order_by(ContainerEvent.id)).all()
        kinds = [e.kind for e in events]
        assert kinds == list(MILESTONES[: len(kinds)]) and container.status == (kinds[-1] if kinds else None)
        assert [e.occurred_at for e in events] == sorted(e.occurred_at for e in events)
    for order in db.scalars(select(TruckingOrder)):
        events = db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id)).all()
        assert order.status == derive_trucking(events)
    codes = []
    for order in db.scalars(select(LastMileOrder)):
        events = db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id)).all()
        assert order.status == derive_last_mile(events)
        codes.append(order.tracking_code)
    assert len(set(codes)) == 200 and all(len(c) == 10 for c in codes)


def test_seed_small_covers_freetime_states_and_do_expiring(db, seeded):
    rows = db.execute(text("SELECT status, level FROM container_freetime(:d)"), {"d": AS_OF}).all()
    assert {"NOT_STARTED", "OPEN", "CLOSED", "NO_RULE", "MISSING_DATA"} <= {r.status for r in rows}
    assert {"GREEN", "YELLOW", "RED", "NO_RULE", "MISSING_DATA"} <= {r.level for r in rows}
    assert len(do_expiring_shipments(db, AS_OF)) >= 1
    assert {o.status for o in db.scalars(select(LastMileOrder))} >= {"DELIVERED", "FAILED", "RETURNED", "CANCELLED"}


def test_seed_has_two_customers_sharing_staff_and_carrier(db, seeded):
    payloads = collect_reminders(db, AS_OF)
    first, second = payloads["kh1@example.com"], payloads["kh2@example.com"]
    assert first.customer_items and second.customer_items
    assert {i.level for i in first.customer_items + second.customer_items} <= {"YELLOW", "RED"}
    assert "docs@fwdflow.local" in payloads
    carriers = {i.carrier_name for i in first.customer_items} & {i.carrier_name for i in second.customer_items}
    assert carriers, "hai khách phải có container cùng hãng tàu"
    assert db.scalar(select(func.count()).select_from(Customer).where(Customer.email.is_not(None))) == 2


def test_seed_driver_scenario_gives_three_assigned_orders(client, db, seeded):
    orders = db.scalars(select(TruckingOrder).where(TruckingOrder.status == "ASSIGNED")
                        .order_by(TruckingOrder.planned_at)).all()
    assert len(orders) == 3 and {o.kind for o in orders} == {"PICKUP_FULL"}
    res = client.post("/api/auth/login", json={"identifier": "0900000006", "password": TEST_PASSWORD})
    assert res.status_code == 200
    tasks = client.get("/api/driver/tasks").json()["data"]
    trucking = [t for t in tasks if t["kind"] == "TRUCKING"]
    assert len(trucking) == 3 and trucking[0]["title"] == "Lấy cont" and trucking[0]["planned_at"][11:16] == "08:00"
