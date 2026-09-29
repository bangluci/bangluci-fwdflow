"""Hộp thư Mailpit thật (dev: docker compose up -d mailpit; CI: service mailpit) và dữ liệu chung của test nhắc hạn."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.catalog.models import Customer
from app.config import get_settings

VN = timezone(timedelta(hours=7))


def at(day: str, hh: int = 0, mm: int = 0) -> datetime:
    """Thời điểm có múi giờ +07:00."""
    return datetime.fromisoformat(day).replace(hour=hh, minute=mm, tzinfo=VN)


class Mailbox:
    def __init__(self, client: httpx.Client):
        self.client = client

    def search(self, query: str) -> list[dict]:
        return self.client.get("/api/v1/search", params={"query": query}).json()["messages"]

    def message(self, message_id: str) -> dict:
        return self.client.get(f"/api/v1/message/{message_id}").json()

    def count(self) -> int:
        return self.client.get("/api/v1/messages").json()["total"]

    def to(self, address: str) -> list[dict]:
        return [self.message(m["ID"]) for m in self.search(f"to:{address}")]


@pytest.fixture
def mailpit():
    client = httpx.Client(base_url=get_settings().mailpit_api_url, timeout=5)
    try:
        client.delete("/api/v1/messages").raise_for_status()
    except httpx.HTTPError:
        pytest.fail("Mailpit chưa chạy: docker compose up -d mailpit")
    yield Mailbox(client)
    client.close()


@pytest.fixture
def reminder_world(db, ft, make_user):
    """Ngày nhắc 2026-11-25, bộ quy tắc R1: khách A `RED` (dỡ 11-17), khách B `YELLOW` (dỡ 11-22), cùng một nhân viên."""
    ft.standard_rules()
    staff = make_user("DOCS", email="staff@example.test")
    customers = [Customer(name=name, email=email) for name, email in (("Khach A", "a@example.test"),
                                                                       ("Khach B", "b@example.test"))]
    db.add_all(customers)
    db.flush()
    a, b = customers
    container_a = ft.container(customer=a, staff_id=staff.id, milestones={"DISCHARGED": "2026-11-17"})
    container_b = ft.container(customer=b, staff_id=staff.id, milestones={"DISCHARGED": "2026-11-22"})
    return SimpleNamespace(staff=staff, a=a, b=b, container_a=container_a, container_b=container_b)
