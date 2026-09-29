"""Ma trận vai trò × endpoint sinh từ PERMISSIONS: mọi route dưới /api hoặc có `require(action)` hoặc nằm trong danh
sách công khai / có luật riêng; vai trò không có quyền phải nhận 403, có quyền thì không được 401 / 403."""

import pytest
from fastapi.routing import APIRoute

from app.auth.models import Role
from app.auth.permissions import PERMISSIONS, can
from app.main import app

ROLES = [role.value for role in Role]
# Route không gắn `require(action)`: công khai, chỉ cần đăng nhập, hoặc kiểm quyền theo loại danh mục ở trong hàm
PUBLIC_ROUTES = {
    ("GET", "/api/health"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/me"),
    ("GET", "/api/public/track/{code}"),
}
CATALOG_PREFIX = "/api/catalog/{kind}"
DUMMY_ID = "999999"  # không tồn tại: request được phép chỉ ra 404 / 422, không ghi gì


def _actions(dependant) -> list[str]:
    found: list[str] = []
    for sub in dependant.dependencies:
        action = getattr(sub.call, "action", None)
        if action:
            found.append(action)
        found += _actions(sub)
    return found


def all_routes() -> list[tuple[str, str, APIRoute]]:
    """(method, đường dẫn đầy đủ, route) cho mọi route của app, kể cả router được include."""
    out = []
    for wrapper in app.routes:
        if type(wrapper).__name__ != "_IncludedRouter":
            continue
        for route in wrapper.original_router.routes:
            if isinstance(route, APIRoute):
                for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                    out.append((method, wrapper.include_context.prefix + route.path, route))
    return out


ROUTES = all_routes()
ACTION_ROUTES = [(m, p, _actions(r.dependant)[0]) for m, p, r in ROUTES if _actions(r.dependant)]


def _fill(path: str) -> str:
    out = path
    while "{" in out:
        start, end = out.index("{"), out.index("}")
        out = out[:start] + DUMMY_ID + out[end + 1:]
    return out


def test_route_discovery_finds_the_api():
    assert len(ROUTES) >= 80 and len(ACTION_ROUTES) >= 70


def test_every_route_has_action_or_public():
    unclassified = [(m, p) for m, p, r in ROUTES
                    if not _actions(r.dependant) and (m, p) not in PUBLIC_ROUTES and not p.startswith(CATALOG_PREFIX)]
    assert unclassified == [], f"route thiếu require(action) và không nằm trong danh sách công khai: {unclassified}"


def test_every_action_used_by_a_route_exists_in_permissions():
    unknown = {a for _, _, a in ACTION_ROUTES} - set(PERMISSIONS)
    assert unknown == set()


def test_every_permission_is_used_by_some_route_or_documented():
    """Quyền không route nào dùng là quyền chết hoặc route đang thiếu bảo vệ: phải nằm trong danh sách đã biết."""
    used = {a for _, _, a in ACTION_ROUTES}
    known_unused = {"catalog.read", "catalog.commercial.write", "catalog.transport.write",  # kiểm theo loại danh mục
                    "container.milestone",  # dùng qua route container (đã tính) hoặc gọi trực tiếp trong service
                    "dashboard.finance", "assistant.finance_views"}  # kiểm trong hàm theo dữ liệu trả về
    assert set(PERMISSIONS) - used <= known_unused | {"transport.read"}, set(PERMISSIONS) - used - known_unused


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(("method", "path", "action"), ACTION_ROUTES, ids=lambda v: v if isinstance(v, str) else None)
def test_role_endpoint_matrix(client, login_as, role, method, path, action):
    login_as(role)
    response = client.request(method, _fill(path))
    if can(role, action):
        assert response.status_code not in (401, 403), f"{role} có quyền {action} nhưng nhận {response.status_code}"
    else:
        assert response.status_code == 403, f"{role} không có quyền {action} nhưng nhận {response.status_code}"
        assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(("method", "path", "action"), ACTION_ROUTES, ids=lambda v: v if isinstance(v, str) else None)
def test_unauthenticated_is_401(client, method, path, action):
    assert client.request(method, _fill(path)).status_code == 401


def test_matrix_covers_at_least_six_cases_per_route():
    assert len(ACTION_ROUTES) * len(ROLES) >= 6 * len(ACTION_ROUTES)


@pytest.mark.parametrize("role", [r for r in ROLES if r != "DRIVER"])
def test_driver_endpoints_refuse_other_roles(client, login_as, role):
    login_as(role)
    assert client.get("/api/driver/tasks").status_code == 403
    assert client.post("/api/driver/actions", data={"client_request_id": "x", "action": "TRUCK_START",
                                                    "target_id": "1"}).status_code == 403


@pytest.mark.parametrize("role", ROLES)
def test_catalog_read_and_write_follow_permissions(client, login_as, role):
    login_as(role)
    read = client.get("/api/catalog/customers")
    assert (read.status_code == 403) == (not can(role, "catalog.read"))
    write = client.post("/api/catalog/customers", json={})
    if not can(role, "catalog.commercial.write"):
        assert write.status_code == 403
    else:
        assert write.status_code not in (401, 403)
    transport = client.post("/api/catalog/truckers", json={})
    assert (transport.status_code == 403) == (not can(role, "catalog.transport.write"))


# --- Truy cập chéo: cùng vai trò nhưng dữ liệu của người khác phải là 404 ---

def _hidden_document(db, make_document, shipment):
    document = make_document(shipment, "DO")
    document.visible_to_customer = False
    db.flush()
    return document


def test_customer_cannot_open_another_customers_shipment_or_documents(client, db, login_as, make_shipment,
                                                                      make_document):
    owner = login_as("CUSTOMER")
    other_shipment = make_shipment(status="CLEARED")  # khách khác (make_shipment tạo khách riêng)
    hidden = _hidden_document(db, make_document, other_shipment)
    assert client.get(f"/api/portal/shipments/{other_shipment.id}").status_code == 404
    assert client.get(f"/api/portal/documents/{hidden.id}/file").status_code == 404
    assert owner.customer_id != other_shipment.customer_id


def test_customer_cannot_download_a_hidden_document_of_own_shipment(client, db, login_as, make_shipment, make_document):
    from app.catalog.models import Customer

    customer_user = login_as("CUSTOMER")
    own = make_shipment(status="CLEARED", customer=db.get(Customer, customer_user.customer_id))
    hidden = _hidden_document(db, make_document, own)
    assert client.get(f"/api/portal/shipments/{own.id}").status_code == 200
    assert client.get(f"/api/portal/documents/{hidden.id}/file").status_code == 404


def test_driver_cannot_act_on_another_drivers_order(client, driver, make_driver, make_shipment, make_container,
                                                    make_trucking_order, send):
    from tests.driver_factories import discharged_at

    other = make_driver()
    shipment = make_shipment(status="CLEARED")
    container = make_container(shipment, milestones={"DISCHARGED": discharged_at()})
    order = make_trucking_order(container, "PICKUP_FULL", events=("ASSIGNED",), team=other.team)
    assert send("TRUCK_START", order.id).status_code == 404
    tasks = client.get("/api/driver/tasks").json()["data"]
    assert all(task["id"] != order.id for task in tasks)


def test_driver_cannot_act_on_another_drivers_last_mile_order(driver, make_driver, make_shipment,
                                                              make_last_mile_order, send):
    other = make_driver()
    shipment = make_shipment(status="AT_WAREHOUSE", delivery_mode="VIA_WAREHOUSE")
    order = make_last_mile_order(shipment, events=("CREATED", "ASSIGNED"), driver=other)
    assert send("LM_PICK_UP", order.id).status_code == 404
