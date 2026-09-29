"""Mọi route ghi dữ liệu phải để lại ít nhất một dòng audit_logs, và audit không chứa bí mật.

`WRITE_SAMPLES` dựng dữ liệu rồi trả một hàm gọi route; chỉ lời gọi đó được đếm dòng audit. Route chưa có mẫu phải nằm
trong `COVERED_ELSEWHERE` kèm tệp test đã kiểm audit cho nó, nên thêm route ghi mới mà quên audit / quên phân loại thì
test này đỏ."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.ai.hs.models import HsCode, HsSuggestionLog
from app.ai.nlq.models import NlQueryLog
from app.audit.models import AuditLog
from app.catalog.models import Customer, Driver, Truck
from app.lastmile.models import LastMileEvent
from app.trucking.models import TruckingOrderEvent
from tests.auth.test_role_matrix import ROUTES
from tests.driver_factories import discharged_at, jpeg

Sample = Callable[[SimpleNamespace], Callable[[], object]]
WRITE_SAMPLES: dict[tuple[str, str], Sample] = {}
EXCLUDED = {("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("POST", "/api/assistant/ask"),
            ("POST", "/api/hs/suggest")}
COVERED_ELSEWHERE = {
    ("POST", "/api/extractions/{extraction_id}/approve"): "tests/extraction/test_approve.py",
    ("POST", "/api/shipments/{shipment_id}/discrepancy-acks"): "tests/extraction/test_discrepancy_gate.py",
    ("POST", "/api/driver/actions"): "tests/driver/test_truck_actions.py",
}
NOW = datetime.now(UTC)
ITEM = {"description": "Vải cotton", "quantity": "100", "unit": "M"}
DECL = {"declaration_no": "301234567890", "type_code": "A11", "registered_at": "2026-10-01T02:00:00Z"}
USD_CHARGE = {"direction": "COST", "category": "OCEAN_FREIGHT", "amount": 12345, "currency": "USD", "fx_rate": "25410"}
DEM = {"fee_type": "DEM", "free_days": 5, "tiers": [{"from_day": 6, "to_day": None, "rate_amount": 2000, "currency": "USD"}]}
DET = {"fee_type": "DET", "free_days": 7, "tiers": [{"from_day": 8, "to_day": None, "rate_amount": 1000, "currency": "USD"}]}


def sample(method: str, path: str):
    def register(fn: Sample) -> Sample:
        WRITE_SAMPLES[(method, path)] = fn
        return fn

    return register


def _post(w, path, **kw):
    return lambda: w.client.post(path, **kw)


# --- người dùng, danh mục ---
@sample("POST", "/api/users")
def _(w):
    body = {"email": "moi@x.vn", "full_name": "Nguoi Moi", "role": "DOCS", "password": "Mat-khau-hop-le-1"}
    return _post(w, "/api/users", json=body)


@sample("PATCH", "/api/users/{user_id}")
def _(w):
    user = w.make_user("DOCS")
    return lambda: w.client.patch(f"/api/users/{user.id}", json={"role": "DISPATCH"})


@sample("POST", "/api/users/{user_id}/reset-password")
def _(w):
    return _post(w, f"/api/users/{w.make_user('DOCS').id}/reset-password", json={"password": "Mat-khau-moi-123"})


@sample("POST", "/api/users/{user_id}/unlock")
def _(w):
    return _post(w, f"/api/users/{w.make_user('DOCS').id}/unlock")


@sample("POST", "/api/catalog/{kind}")
def _(w):
    return _post(w, "/api/catalog/customers", json={"name": "Khach moi"})


def _customer(w):
    customer = Customer(name="Khach cu")
    w.db.add(customer)
    w.db.flush()
    return customer


@sample("PATCH", "/api/catalog/{kind}/{item_id}")
def _(w):
    customer = _customer(w)
    return lambda: w.client.patch(f"/api/catalog/customers/{customer.id}", json={"name": "Khach doi ten"})


@sample("DELETE", "/api/catalog/{kind}/{item_id}")
def _(w):
    customer = _customer(w)
    return lambda: w.client.delete(f"/api/catalog/customers/{customer.id}")


# --- lô hàng, dòng hàng, tờ khai, container ---
@sample("POST", "/api/shipments")
def _(w):
    customer = _customer(w)
    return _post(w, "/api/shipments", json={"load_type": "FCL", "delivery_mode": "VIA_WAREHOUSE",
                                            "customer_id": customer.id})


@sample("PATCH", "/api/shipments/{shipment_id}")
def _(w):
    shipment = w.make_shipment()
    return lambda: w.client.patch(f"/api/shipments/{shipment.id}", json={"version": shipment.version, "vessel": "EVER X"})


@sample("POST", "/api/shipments/{shipment_id}/transition")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/transition", json={"to_status": "IN_TRANSIT"})


@sample("POST", "/api/shipments/{shipment_id}/cancel")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/cancel", json={"reason": "khach huy don hang"})


def _item(w):
    shipment = w.make_shipment()
    item = w.client.post(f"/api/shipments/{shipment.id}/items", json=ITEM).json()["data"]
    return shipment, item


@sample("POST", "/api/shipments/{shipment_id}/items")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/items", json=ITEM)


@sample("PATCH", "/api/shipments/{shipment_id}/items/{item_id}")
def _(w):
    shipment, item = _item(w)
    return lambda: w.client.patch(f"/api/shipments/{shipment.id}/items/{item['id']}", json={"description": "Vai moi"})


@sample("DELETE", "/api/shipments/{shipment_id}/items/{item_id}")
def _(w):
    shipment, item = _item(w)
    return lambda: w.client.delete(f"/api/shipments/{shipment.id}/items/{item['id']}")


def _decl(w):
    shipment = w.make_shipment()
    decl = w.client.post(f"/api/shipments/{shipment.id}/customs-declarations", json=DECL).json()["data"]
    return shipment, decl


@sample("POST", "/api/shipments/{shipment_id}/customs-declarations")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/customs-declarations", json=DECL)


@sample("PATCH", "/api/shipments/{shipment_id}/customs-declarations/{decl_id}")
def _(w):
    shipment, decl = _decl(w)
    return lambda: w.client.patch(f"/api/shipments/{shipment.id}/customs-declarations/{decl['id']}",
                                  json={"type_code": "A12"})


@sample("DELETE", "/api/shipments/{shipment_id}/customs-declarations/{decl_id}")
def _(w):
    shipment, decl = _decl(w)
    return lambda: w.client.delete(f"/api/shipments/{shipment.id}/customs-declarations/{decl['id']}")


@sample("POST", "/api/shipments/{shipment_id}/containers")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/containers",
                 json={"container_no": "CSQU3054383", "container_type": "40HC"})


@sample("PATCH", "/api/shipments/{shipment_id}/containers/{container_id}")
def _(w):
    shipment = w.make_shipment()
    container = w.make_container(shipment)
    return lambda: w.client.patch(f"/api/shipments/{shipment.id}/containers/{container.id}", json={"seal_no": "SEAL1"})


@sample("DELETE", "/api/shipments/{shipment_id}/containers/{container_id}")
def _(w):
    shipment = w.make_shipment()
    container = w.make_container(shipment)
    return lambda: w.client.delete(f"/api/shipments/{shipment.id}/containers/{container.id}")


@sample("POST", "/api/containers/{container_id}/events")
def _(w):
    container = w.make_container(w.make_shipment(status="ARRIVED"))
    return _post(w, f"/api/containers/{container.id}/events",
                 json={"kind": "DISCHARGED", "occurred_at": (NOW - timedelta(hours=3)).isoformat()})


# --- chứng từ, nhận hàng LCL, đóng lô (có ảnh) ---
@sample("POST", "/api/shipments/{shipment_id}/documents")
def _(w):
    shipment = w.make_shipment()
    return _post(w, f"/api/shipments/{shipment.id}/documents", data={"doc_type": "ARRIVAL_NOTICE"},
                 files={"file": ("tb.jpg", jpeg("blue"), "image/jpeg")})


@sample("POST", "/api/documents/{document_id}/supersede")
def _(w):
    document = w.make_document(w.make_shipment(), "ARRIVAL_NOTICE")
    return _post(w, f"/api/documents/{document.id}/supersede", files={"file": ("tb2.jpg", jpeg("green"), "image/jpeg")})


@sample("POST", "/api/shipments/{shipment_id}/receive-at-warehouse")
def _(w):
    shipment = w.make_shipment(status="CLEARED", load_type="LCL")
    return _post(w, f"/api/shipments/{shipment.id}/receive-at-warehouse", data={"note": "nhan du kien"},
                 files={"photo": ("cfs.jpg", jpeg("gray"), "image/jpeg")})


@sample("POST", "/api/shipments/{shipment_id}/close")
def _(w):
    shipment = w.make_shipment(status="AT_WAREHOUSE", load_type="LCL")
    return _post(w, f"/api/shipments/{shipment.id}/close", data={"reason": "khach nhan truc tiep tai kho"},
                 files={"photo": ("bb.jpg", jpeg("black"), "image/jpeg")})


# --- AI: duyệt kết quả đọc chứng từ, gợi ý mã HS, hỏi đáp ---
def _extraction(w, status="REVIEW"):
    return w.make_extraction(shipment=w.make_shipment(), status=status)


@sample("POST", "/api/extractions/{extraction_id}/reject")
def _(w):
    extraction = _extraction(w)
    return lambda: w.client.post(f"/api/extractions/{extraction.id}/reject", json={"reason": "chung tu bi mo"})


@sample("POST", "/api/extractions/{extraction_id}/retry")
def _(w):
    extraction = _extraction(w, status="FAILED")
    return lambda: w.client.post(f"/api/extractions/{extraction.id}/retry")


@sample("POST", "/api/hs/suggestions/{log_id}/choice")
def _(w):
    w.db.add(HsCode(code="84713020", chapter=84, description_vi="Máy tính xách tay"))
    w.db.flush()
    log = HsSuggestionLog(user_id=w.admin.id, description="laptop", search_degraded=False, status="OK",
                          candidates=[{"code": "84713020"}], top3=[], latency_ms=5)
    w.db.add(log)
    w.db.flush()
    return _post(w, f"/api/hs/suggestions/{log.id}/choice", json={"code": "84713020"})


@sample("POST", "/api/assistant/{log_id}/rating")
def _(w):
    log = NlQueryLog(user_id=w.admin.id, nlq_role="nlq_finance", question="Đếm lô", validation_result="OK", latency_ms=5)
    w.db.add(log)
    w.db.flush()
    return _post(w, f"/api/assistant/{log.id}/rating", json={"correct": True})


# --- free time ---
def _rule_body(w, effective_from="2031-01-01"):
    shipment = w.make_shipment()
    return {"carrier_id": shipment.carrier_id, "port_id": shipment.pod_port_id, "container_type": "40HC",
            "effective_from": effective_from, "rules": [DEM, DET]}


@sample("POST", "/api/freetime/rules")
def _(w):
    return _post(w, "/api/freetime/rules", json=_rule_body(w))


@sample("DELETE", "/api/freetime/rules/{rule_id}")
def _(w):
    version = w.client.post("/api/freetime/rules", json=_rule_body(w)).json()["data"]
    rule_id = version["rules"][0]["id"]
    return lambda: w.client.delete(f"/api/freetime/rules/{rule_id}")


@sample("PUT", "/api/shipments/{shipment_id}/freetime-overrides")
def _(w):
    shipment = w.make_shipment()
    return lambda: w.client.put(f"/api/shipments/{shipment.id}/freetime-overrides",
                                json={"fee_type": "DEM", "free_days": 10, "source": "DO"})


@sample("DELETE", "/api/shipments/{shipment_id}/freetime-overrides/{fee_type}")
def _(w):
    shipment = w.make_shipment()
    w.client.put(f"/api/shipments/{shipment.id}/freetime-overrides", json={"fee_type": "DEM", "free_days": 10, "source": "DO"})
    return lambda: w.client.delete(f"/api/shipments/{shipment.id}/freetime-overrides/DEM")


# --- điều xe ---
def _pickup_container(w):
    shipment = w.make_shipment(status="CLEARED")
    return w.make_container(shipment, milestones={"DISCHARGED": discharged_at()})


@sample("POST", "/api/trucking-orders")
def _(w):
    container, team = _pickup_container(w), w.make_trucker()
    body = {"container_id": container.id, "kind": "PICKUP_FULL", "trucker_id": team.trucker.id,
            "pickup_location": "Cảng Cát Lái", "drop_location": "Kho Bình Dương",
            "planned_at": (NOW + timedelta(days=1)).isoformat()}
    return _post(w, "/api/trucking-orders", json=body)


@sample("POST", "/api/trucking-orders/{order_id}/assign")
def _(w):
    team = w.make_trucker()
    order = w.make_trucking_order(_pickup_container(w), team=team)
    return _post(w, f"/api/trucking-orders/{order.id}/assign", json={"truck_id": team.truck.id, "driver_id": team.driver.id})


@sample("POST", "/api/trucking-orders/{order_id}/reassign")
def _(w):
    team = w.make_trucker()
    order = w.make_trucking_order(_pickup_container(w), events=("ASSIGNED",), team=team)
    truck = Truck(trucker_id=team.trucker.id, plate_no="51C-99999")
    driver = Driver(trucker_id=team.trucker.id, full_name="Tai xe thay the")
    w.db.add_all([truck, driver])
    w.db.flush()
    return _post(w, f"/api/trucking-orders/{order.id}/reassign",
                 json={"truck_id": truck.id, "driver_id": driver.id, "reason": "xe cu bi hong"})


@sample("POST", "/api/trucking-orders/{order_id}/cancel")
def _(w):
    order = w.make_trucking_order(_pickup_container(w))
    return _post(w, f"/api/trucking-orders/{order.id}/cancel", json={"reason": "khach hoan nhan hang"})


def _started_event(w):
    order = w.make_trucking_order(_pickup_container(w), events=("ASSIGNED", "STARTED"))
    event = w.db.scalars(select(TruckingOrderEvent).where(TruckingOrderEvent.order_id == order.id,
                                                          TruckingOrderEvent.kind == "STARTED")).one()
    return order, event


@sample("POST", "/api/trucking-orders/{order_id}/events/{event_id}/void")
def _(w):
    order, event = _started_event(w)
    return _post(w, f"/api/trucking-orders/{order.id}/events/{event.id}/void", json={"reason": "bam nham nut"})


@sample("POST", "/api/trucking-orders/{order_id}/events/{event_id}/retime")
def _(w):
    order, event = _started_event(w)
    return _post(w, f"/api/trucking-orders/{order.id}/events/{event.id}/retime",
                 json={"occurred_at": (NOW - timedelta(hours=1)).isoformat(), "reason": "ghi nham gio chay"})


# --- giao nội địa ---
def _lot(w):
    return w.make_shipment(status="AT_WAREHOUSE", delivery_mode="VIA_WAREHOUSE")


@sample("POST", "/api/shipments/{shipment_id}/last-mile-orders")
def _(w):
    order = {"recipient_name": "Nguyễn Văn An", "recipient_phone": "0901234567", "address": "12 Lê Lợi, Quận 1",
             "packages": 2, "planned_date": NOW.date().isoformat()}
    return _post(w, f"/api/shipments/{_lot(w).id}/last-mile-orders", json={"orders": [order]})


@sample("POST", "/api/last-mile-orders/{order_id}/assign")
def _(w):
    order = w.make_last_mile_order(_lot(w), events=("CREATED",))
    return _post(w, f"/api/last-mile-orders/{order.id}/assign",
                 json={"driver_id": w.make_driver().team.driver.id, "planned_date": NOW.date().isoformat()})


@sample("POST", "/api/last-mile-orders/{order_id}/reassign")
def _(w):
    order = w.make_last_mile_order(_lot(w), events=("CREATED", "ASSIGNED"))
    return _post(w, f"/api/last-mile-orders/{order.id}/reassign",
                 json={"driver_id": w.make_driver().team.driver.id, "reason": "tai xe nghi om"})


@sample("POST", "/api/last-mile-orders/{order_id}/cancel")
def _(w):
    order = w.make_last_mile_order(_lot(w), events=("CREATED",))
    return _post(w, f"/api/last-mile-orders/{order.id}/cancel", json={"reason": "khach huy nhan hang"})


@sample("POST", "/api/last-mile-orders/{order_id}/return")
def _(w):
    order = w.make_last_mile_order(_lot(w), events=("CREATED", "ASSIGNED", "PICKED_UP", "FAILED"))
    return _post(w, f"/api/last-mile-orders/{order.id}/return", json={"reason": "nhan lai hang ve kho"})


@sample("POST", "/api/last-mile-orders/{order_id}/events/{event_id}/void")
def _(w):
    order = w.make_last_mile_order(_lot(w), events=("CREATED", "ASSIGNED", "PICKED_UP", "DELIVERED"))
    event = w.db.scalars(select(LastMileEvent).where(LastMileEvent.order_id == order.id,
                                                     LastMileEvent.kind == "DELIVERED")).one()
    return _post(w, f"/api/last-mile-orders/{order.id}/events/{event.id}/void", json={"reason": "bam nham nut giao"})


# --- tài chính ---
def _charge(w):
    shipment = w.make_shipment()
    charge = w.client.post(f"/api/shipments/{shipment.id}/charges", json=USD_CHARGE).json()["data"]
    return shipment, charge


@sample("POST", "/api/shipments/{shipment_id}/charges")
def _(w):
    return _post(w, f"/api/shipments/{w.make_shipment().id}/charges", json=USD_CHARGE)


@sample("PATCH", "/api/shipments/{shipment_id}/charges/{charge_id}")
def _(w):
    shipment, charge = _charge(w)
    return lambda: w.client.patch(f"/api/shipments/{shipment.id}/charges/{charge['id']}", json={"note": "ghi chu moi"})


@sample("DELETE", "/api/shipments/{shipment_id}/charges/{charge_id}")
def _(w):
    shipment, charge = _charge(w)
    return lambda: w.client.delete(f"/api/shipments/{shipment.id}/charges/{charge['id']}")


# --- bộ kiểm ---
WRITE_ROUTES = sorted({(m, p) for m, p, _ in ROUTES if m in ("POST", "PUT", "PATCH", "DELETE")} - EXCLUDED)


@pytest.fixture
def world(client, db, login_as, make_user, make_shipment, make_container, make_document, make_extraction,
          make_trucker, make_trucking_order, make_driver, make_last_mile_order):
    admin = login_as("ADMIN")
    return SimpleNamespace(client=client, db=db, admin=admin, make_user=make_user, make_shipment=make_shipment,
                           make_container=make_container, make_document=make_document, make_extraction=make_extraction,
                           make_trucker=make_trucker, make_trucking_order=make_trucking_order, make_driver=make_driver,
                           make_last_mile_order=make_last_mile_order)


def test_every_write_route_is_sampled_or_documented():
    handled = set(WRITE_SAMPLES) | set(COVERED_ELSEWHERE)
    assert set(WRITE_ROUTES) - handled == set(), "route ghi chưa có mẫu audit hoặc chưa được phân loại"
    assert handled - set(WRITE_ROUTES) == set(), "mẫu audit trỏ tới route không còn tồn tại"


@pytest.mark.parametrize(("method", "path"), sorted(COVERED_ELSEWHERE))
def test_routes_covered_elsewhere_have_an_audit_assertion(method, path):
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / COVERED_ELSEWHERE[(method, path)]
    assert source.exists() and "AuditLog" in source.read_text(encoding="utf-8")


@pytest.mark.parametrize(("method", "path"), sorted(WRITE_SAMPLES), ids=lambda v: v)
def test_every_write_route_records_audit(world, method, path):
    call = WRITE_SAMPLES[(method, path)](world)
    world.db.flush()
    before = world.db.scalar(select(func.count()).select_from(AuditLog))
    response = call()
    assert response.status_code < 400, f"{method} {path}: {response.status_code} {response.text[:200]}"
    after = world.db.scalar(select(func.count()).select_from(AuditLog))
    assert after > before, f"{method} {path} thành công nhưng không ghi dòng audit nào"


def test_audit_has_no_secrets(world):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import TEST_PASSWORD

    world.make_user("DOCS", email="an@x.vn")
    with TestClient(app, base_url="https://testserver") as other:  # phiên riêng để lấy token đăng nhập
        login = other.post("/api/auth/login", json={"identifier": "an@x.vn", "password": TEST_PASSWORD})
        assert login.status_code == 200
        token = other.cookies.get("__Host-sid") or ""
    WRITE_SAMPLES[("POST", "/api/users")](world)()
    WRITE_SAMPLES[("POST", "/api/users/{user_id}/reset-password")](world)()
    world.db.flush()
    dump = " ".join(str(row.before) + str(row.after) for row in world.db.scalars(select(AuditLog)))
    for secret in ("$argon2", "Mat-khau-hop-le-1", "Mat-khau-moi-123", TEST_PASSWORD):
        assert secret not in dump, f"audit lộ bí mật: {secret}"
    # Đổi mật khẩu chỉ ghi dấu "<changed>" cho cột password_hash (code thắng plan, plan cấm cả tên cột); giá trị không lộ
    assert dump.count("password_hash") == dump.count("'password_hash': '<changed>'")
    assert token and token not in dump
