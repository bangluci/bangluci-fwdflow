from datetime import date

from app.catalog.models import Customer
from app.notifications.reminder import DO_EXPIRING, collect_reminders, render_reminder

AS_OF = date(2026, 11, 25)


def _levels(payload):
    return sorted(item.level for item in payload.staff_items)


def test_staff_gets_own_active_containers_by_level(db, ft, make_user):
    ft.standard_rules()
    staff_a = make_user("DOCS", email="sa@example.test")
    staff_b = make_user("DOCS", email="sb@example.test")
    days = {"RED": "2026-11-17", "YELLOW": "2026-11-22", "GREEN": "2026-11-24"}
    for day in days.values():
        ft.container(staff_id=staff_a.id, milestones={"DISCHARGED": day})
    ft.container(staff_id=staff_a.id, carrier_code="MAEU", milestones={"DISCHARGED": "2026-11-20"})  # NO_RULE
    ft.container(staff_id=staff_a.id)  # ARRIVED nhưng chưa có ngày dỡ hàng: MISSING_DATA
    ft.container(staff_id=staff_b.id, milestones={"DISCHARGED": "2026-11-17"})
    payloads = collect_reminders(db, AS_OF)
    assert _levels(payloads["sa@example.test"]) == ["MISSING_DATA", "NO_RULE", "RED", "YELLOW"]
    assert _levels(payloads["sb@example.test"]) == ["RED"]


def test_customer_gets_only_own_yellow_red(db, reminder_world, ft):
    ft.container(customer=reminder_world.a, staff_id=reminder_world.staff.id, carrier_code="MAEU",
                 milestones={"DISCHARGED": "2026-11-20"})  # NO_RULE: khách không nhận
    payloads = collect_reminders(db, AS_OF)
    assert [i.container_no for i in payloads["a@example.test"].customer_items] == [
        reminder_world.container_a.container_no]
    assert [i.container_no for i in payloads["b@example.test"].customer_items] == [
        reminder_world.container_b.container_no]
    assert len(payloads["staff@example.test"].staff_items) == 3


def test_excluded_recipients_shipments_and_clocks(db, ft, make_user):
    ft.standard_rules()
    staff = make_user("DOCS", email="staff@example.test")
    silent = make_user("DOCS", email=None, phone="0900000001")
    locked = make_user("DOCS", email="locked@example.test", is_active=False)
    no_mail = Customer(name="Khong email")
    db.add(no_mail)
    db.flush()
    red = {"DISCHARGED": "2026-11-17"}
    ft.container(status="CANCELLED", staff_id=staff.id, milestones=red)
    ft.container(status="COMPLETED", staff_id=staff.id, milestones=red)
    ft.container(staff_id=staff.id, milestones={"DISCHARGED": "2026-11-17", "GATE_OUT_FULL": "2026-11-18",
                                                 "EMPTY_RETURNED": "2026-11-19"})  # mọi đồng hồ CLOSED
    ft.container(status="IN_TRANSIT", eta="2026-12-15", staff_id=staff.id)  # NOT_STARTED
    ft.container(staff_id=silent.id, customer=no_mail, milestones=red)
    ft.container(staff_id=locked.id, customer=no_mail, milestones=red)
    assert collect_reminders(db, AS_OF) == {}


def test_do_expiring_boundary(db, ft, make_user):
    staff = make_user("DOCS", email="staff@example.test")
    codes = {}
    for label, delta in (("edge", 26), ("beyond", 27), ("expired", 24)):
        container = ft.container(status="IN_TRANSIT", eta="2026-12-15", staff_id=staff.id,
                                 do_valid_until=date(2026, 11, delta))
        codes[label] = container.shipment_id
    gone = ft.container(status="IN_TRANSIT", eta="2026-12-15", staff_id=staff.id, do_valid_until=date(2026, 11, 25),
                        milestones={"GATE_OUT_FULL": "2026-11-24"})
    payloads = collect_reminders(db, AS_OF)
    flagged = {i.shipment_id for i in payloads["staff@example.test"].staff_items if i.level == DO_EXPIRING}
    assert flagged == {codes["edge"], codes["expired"]} and gone.shipment_id not in flagged


def test_render_escapes_html_and_hides_fees_from_customers(db, reminder_world):
    reminder_world.a.name = "<script>x</script>"
    db.flush()
    payloads = collect_reminders(db, AS_OF)
    _, staff_html = render_reminder(payloads["staff@example.test"], AS_OF, "https://fwd.test")
    subject, customer_html = render_reminder(payloads["a@example.test"], AS_OF, "https://fwd.test")
    assert subject == "[FwdFlow] Nhắc hạn free time ngày 25/11/2026: 1 mục"
    assert "<script>" not in staff_html
    item = payloads["staff@example.test"].staff_items[0]
    assert f"https://fwd.test/shipments/{item.shipment_id}" in staff_html and "Phí ước tính" in staff_html
    assert "Phí" not in customer_html and "/shipments/" not in customer_html and "Khach B" not in customer_html
