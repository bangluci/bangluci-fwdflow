from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.finance.service import create_charge

URL = "/api/reports/dashboard"


@pytest.fixture(autouse=True)
def fixed_today(db):
    db.execute(text("SELECT set_config('app.as_of', '2026-11-30', true)"))


def test_dashboard_active_shipments_excludes_completed_cancelled(client, login_as, make_shipment):
    login_as("DOCS")
    for status in ("CREATED", "IN_TRANSIT", "DELIVERING", "COMPLETED", "CANCELLED"):
        make_shipment(status=status)
    data = client.get(URL).json()["data"]
    assert data["active_shipments"] == 3 and data["as_of"] == "2026-11-30"


def test_dashboard_yellow_red_only_active_fcl(client, login_as, ft):
    login_as("DOCS")
    ft.standard_rules()
    ft.container(status="ARRIVED", milestones={"DISCHARGED": "2026-11-17"})  # RED
    ft.container(status="ARRIVED", milestones={"DISCHARGED": "2026-11-27"})  # YELLOW (còn 1 ngày)
    ft.container(status="ARRIVED", milestones={"DISCHARGED": "2026-11-29"})  # GREEN
    ft.container(status="CANCELLED", milestones={"DISCHARGED": "2026-11-17"})
    ft.container(status="COMPLETED", milestones={"DISCHARGED": "2026-11-17"})
    data = client.get(URL).json()["data"]
    assert (data["containers_red"], data["containers_yellow"]) == (1, 1)


def test_dashboard_do_expiring_boundary(client, login_as, ft):
    login_as("DOCS")
    inside = ft.container(status="ARRIVED", do_valid_until=date(2026, 12, 1))
    ft.container(status="ARRIVED", do_valid_until=date(2026, 12, 2))
    ft.container(status="ARRIVED", do_valid_until=date(2026, 11, 29),
                 milestones={"DISCHARGED": "2026-11-20", "GATE_OUT_FULL": "2026-11-25"})
    data = client.get(URL).json()["data"]
    assert [d["shipment_id"] for d in data["do_expiring"]] == [inside.shipment_id]
    assert data["do_expiring"][0]["do_valid_until"] == "2026-12-01"


@pytest.mark.parametrize(("role", "has_finance"), [("DOCS", False), ("DISPATCH", False), ("ADMIN", True),
                                                   ("ACCOUNTANT", True)])
def test_dashboard_finance_keys_only_for_admin_accountant(client, login_as, role, has_finance):
    login_as(role)
    data = client.get(URL).json()["data"]
    assert ("month_revenue_vnd" in data) is has_finance and ("month_profit_vnd" in data) is has_finance


def test_dashboard_month_revenue_profit_match_fixture(client, db, login_as, make_shipment):
    actor = login_as("ACCOUNTANT")
    shipment = make_shipment()
    rows = [("REVENUE", 20_000_000, "VND", None, date(2026, 11, 3)), ("REVENUE", 50_000, "USD", "25400", date(2026, 11, 30)),
            ("COST", 11_000_000, "VND", None, date(2026, 11, 10)), ("REVENUE", 99_000_000, "VND", None, date(2026, 10, 31)),
            ("REVENUE", 7_000_000, "VND", None, date(2026, 12, 1))]
    for direction, amount, currency, fx, day in rows:
        create_charge(db, shipment.id, {"direction": direction, "category": "OTHER", "amount": amount,
                                        "currency": currency, "fx_rate": fx and Decimal(fx),
                                        "charge_date": day}, actor)
    data = client.get(URL).json()["data"]
    assert (data["month_revenue_vnd"], data["month_profit_vnd"]) == (32_700_000, 21_700_000)


@pytest.mark.parametrize("role", ["CUSTOMER", "DRIVER"])
def test_dashboard_forbidden_for_customer_driver(client, login_as, role):
    login_as(role)
    res = client.get(URL)
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


def test_dashboard_queue_counts(client, login_as, make_extraction, make_shipment, make_container, make_trucking_order,
                                make_last_mile_order):
    login_as("DOCS")
    make_extraction(status="REVIEW")
    make_extraction(status="FAILED")
    make_extraction(status="PENDING")
    shipment = make_shipment(status="DELIVERING", total_packages=10)
    make_trucking_order(make_container(make_shipment(status="CLEARED")))  # PLANNED chưa gán
    make_last_mile_order(shipment, 2, events=("CREATED", "ASSIGNED", "PICKED_UP", "FAILED"))
    data = client.get(URL).json()["data"]
    counts = ("extractions_review", "extractions_failed", "trucking_unassigned", "last_mile_failed")
    assert [data[k] for k in counts] == [1, 1, 1, 1]
