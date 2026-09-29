"""Nhắc hạn free time: gom nội dung theo người nhận (qua hàm scope), dựng email, gửi có thử lại và cảnh báo kẹt."""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, exists, select, text, update
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.audit.service import record_audit
from app.auth.models import Role, User
from app.auth.scope import scope_shipments
from app.catalog.models import Carrier, Customer
from app.config import get_settings
from app.notifications.mailer import MailerError, send_email
from app.notifications.models import NotificationLog, NotificationStatus
from app.shipments.models import Shipment

log = logging.getLogger("fwdflow.reminder")

STAFF_LEVELS = ("YELLOW", "RED", "NO_RULE", "MISSING_DATA")
CUSTOMER_LEVELS = ("YELLOW", "RED")
DO_EXPIRING = "DO_EXPIRING"
LEVEL_RANK = {"RED": 5, "YELLOW": 4, "NO_RULE": 3, "MISSING_DATA": 2, DO_EXPIRING: 1}
LEVEL_LABELS = {"RED": "Quá hạn", "YELLOW": "Sắp hạn", "NO_RULE": "Chưa có quy tắc",
                "MISSING_DATA": "Thiếu ngày dỡ hàng", DO_EXPIRING: "DO sắp hết hạn"}

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
REMINDER_HOUR_VN = 7
RETRY_AFTER = timedelta(minutes=15)
STUCK_AFTER = timedelta(minutes=10)
ERROR_MAX_CHARS = 500

_CLOCK_ROWS = """
SELECT DISTINCT ON (f.container_id) f.shipment_id, f.shipment_code, f.customer_name, f.carrier_name, f.container_no,
       f.level, f.fee_type, f.due_date, f.days_left, f.days_over, f.fee_amount, f.fee_currency,
       s.staff_id, s.customer_id
FROM container_freetime(:as_of) f JOIN shipments s ON s.id = f.shipment_id
WHERE f.container_level IS NOT NULL AND f.level = f.container_level
  AND f.shipment_status NOT IN ('CANCELLED', 'COMPLETED')
ORDER BY f.container_id, f.due_date NULLS LAST, f.fee_type
"""
_DO_IDS = """
SELECT s.id FROM shipments s
WHERE s.load_type = 'FCL' AND s.status NOT IN ('CANCELLED', 'COMPLETED')
  AND s.do_valid_until IS NOT NULL AND s.do_valid_until <= :as_of + 1
  AND EXISTS (SELECT 1 FROM containers c WHERE c.shipment_id = s.id AND NOT EXISTS (
      SELECT 1 FROM effective_container_milestones m WHERE m.container_id = c.id AND m.kind = 'GATE_OUT_FULL'))
"""


def do_expiring_shipments(db: Session, as_of: date) -> list[Shipment]:
    """Lô FCL còn hiệu lực có D/O hết hạn trong vòng 1 ngày (hoặc đã hết) mà còn container chưa lấy ra khỏi cảng."""
    ids = db.scalars(text(_DO_IDS), {"as_of": as_of}).all()
    return list(db.scalars(select(Shipment).where(Shipment.id.in_(ids)).order_by(Shipment.do_valid_until,
                                                                                 Shipment.id)))


@dataclass
class ReminderItem:
    shipment_id: int
    shipment_code: str
    customer_name: str
    carrier_name: str | None
    container_no: str | None
    level: str
    fee_type: str | None = None
    due_date: date | None = None
    days_left: int | None = None
    days_over: int | None = None
    fee_amount: int | None = None
    fee_currency: str | None = None
    do_valid_until: date | None = None


@dataclass
class ReminderPayload:
    email: str
    staff_items: list[ReminderItem] = field(default_factory=list)
    customer_items: list[ReminderItem] = field(default_factory=list)


@dataclass
class SendSummary:
    sent: int = 0
    failed: int = 0
    stuck: int = 0


def _sort_key(item: ReminderItem) -> tuple:
    return (item.container_no is None, -LEVEL_RANK.get(item.level, 0), item.due_date is None,
            item.due_date or date.min, item.container_no or "")


def _email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def _clock_items(db: Session, as_of: date) -> list[tuple[ReminderItem, int, int]]:
    """(mục nhắc, staff_id, customer_id): mỗi container một dòng, là đồng hồ xấu nhất."""
    rows = db.execute(text(_CLOCK_ROWS), {"as_of": as_of}).mappings()
    return [(ReminderItem(**{k: v for k, v in row.items() if k not in ("staff_id", "customer_id")}),
             row["staff_id"], row["customer_id"]) for row in rows]


def _do_items(db: Session, as_of: date) -> list[tuple[ReminderItem, int]]:
    items = []
    for shipment in do_expiring_shipments(db, as_of):
        carrier = db.get(Carrier, shipment.carrier_id) if shipment.carrier_id else None
        items.append((ReminderItem(shipment_id=shipment.id, shipment_code=shipment.code,
                                   customer_name=db.get(Customer, shipment.customer_id).name,
                                   carrier_name=carrier.name if carrier else None, container_no=None,
                                   level=DO_EXPIRING, do_valid_until=shipment.do_valid_until), shipment.staff_id))
    return items


def collect_reminders(db: Session, as_of: date) -> dict[str, ReminderPayload]:
    """Email (đã chuẩn hoá) → nội dung nhắc; người không có mục nào thì không có trong kết quả."""
    clocks, dos = _clock_items(db, as_of), _do_items(db, as_of)
    payloads: dict[str, ReminderPayload] = {}

    def add(email: str | None, kind: str, item: ReminderItem) -> None:
        if email:
            getattr(payloads.setdefault(email, ReminderPayload(email)), kind).append(item)

    staff_email = {u.id: _email(u.email) for u in db.scalars(select(User).where(User.is_active))}
    for item, staff_id, _ in clocks:
        if item.level in STAFF_LEVELS:
            add(staff_email.get(staff_id), "staff_items", item)
    for item, staff_id in dos:
        add(staff_email.get(staff_id), "staff_items", item)

    customer_ids = {cid for item, _, cid in clocks if item.level in CUSTOMER_LEVELS}
    for customer in db.scalars(select(Customer).where(Customer.active, Customer.id.in_(customer_ids))):
        owner = SimpleNamespace(role=Role.CUSTOMER, customer_id=customer.id)
        own = set(db.scalars(scope_shipments(select(Shipment.id), owner)))
        for item, _, _ in clocks:
            if item.level in CUSTOMER_LEVELS and item.shipment_id in own:
                add(_email(customer.email), "customer_items", item)

    for payload in payloads.values():
        payload.staff_items.sort(key=_sort_key)
        payload.customer_items.sort(key=_sort_key)
    return payloads


def _money(amount: int | None, currency: str | None) -> str:
    if amount is None or currency is None:
        return "—"
    if currency == "USD":
        return f"{amount / 100:,.2f} USD"
    return f"{amount:,} {currency}".replace(",", ".")


def _date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _days_text(item: ReminderItem) -> str:
    if item.level == DO_EXPIRING:
        return "—"
    if item.days_over:
        return f"quá {item.days_over} ngày"
    return "—" if item.days_left is None else f"còn {item.days_left} ngày"


def _cell(value: object) -> str:
    return f"<td>{escape(str(value))}</td>"


def _table(items: list[ReminderItem], *, staff: bool, base_url: str) -> str:
    head = ["Lô", "Container", "Mức", "Hạn free", "Số ngày"] + (["Phí ước tính"] if staff else [])
    rows = []
    for item in items:
        code = escape(item.shipment_code)
        link = f'<a href="{escape(f"{base_url}/shipments/{item.shipment_id}")}">{code}</a>' if staff else code
        cells = [f"<td>{link}</td>", _cell(item.container_no or "—"), _cell(LEVEL_LABELS.get(item.level, item.level)),
                 _cell(_date(item.do_valid_until if item.level == DO_EXPIRING else item.due_date)),
                 _cell(_days_text(item))]
        if staff:
            cells.append(_cell(_money(item.fee_amount, item.fee_currency)))
        rows.append(f"<tr>{''.join(cells)}</tr>")
    header = "".join(f"<th>{h}</th>" for h in head)
    return f'<table border="1" cellpadding="6" cellspacing="0"><tr>{header}</tr>{"".join(rows)}</table>'


def render_reminder(payload: ReminderPayload, as_of: date, base_url: str) -> tuple[str, str]:
    """(subject, html). Email khách không có phí, tên nhân viên hay tên khách khác."""
    count = len(payload.staff_items) + len(payload.customer_items)
    subject = f"[FwdFlow] Nhắc hạn free time ngày {_date(as_of)}: {count} mục"
    parts = [f"<p>Nhắc hạn free time ngày {_date(as_of)}.</p>"]
    if payload.staff_items:
        parts += ["<h3>Lô bạn phụ trách</h3>", _table(payload.staff_items, staff=True, base_url=base_url)]
    if payload.customer_items:
        parts += ["<h3>Lô của công ty bạn</h3>", _table(payload.customer_items, staff=False, base_url=base_url)]
    return subject, "\n".join(parts)


def _alert_stuck(db: Session, now: datetime) -> int:
    """PENDING quá 10 phút (worker chết lúc gửi): cảnh báo Admin đúng một lần, không gửi lại vì có thể đã gửi."""
    already = exists().where(AuditLog.action == "REMINDER_STUCK", AuditLog.entity == "notification_log",
                             AuditLog.entity_id == cast(NotificationLog.id, String))
    rows = db.scalars(select(NotificationLog).where(
        NotificationLog.status == NotificationStatus.PENDING, NotificationLog.last_attempt_at < now - STUCK_AFTER,
        ~already)).all()
    for row in rows:
        record_audit(db, None, "REMINDER_STUCK", "notification_log", row.id, None,
                     {"day": row.day, "status": row.status, "attempts": row.attempts})
        log.error("Email nhắc hạn %s kẹt PENDING từ %s, không gửi lại", row.id, row.last_attempt_at)
    db.commit()
    return len(rows)


def _claim(db: Session, payload: ReminderPayload, now: datetime, day: date) -> int | None:
    """Chèn dòng mới hoặc nhận lại dòng FAILED đủ 15 phút; None nếu tiến trình khác đã lấy hoặc chưa tới lượt."""
    items = [{"shipment_code": i.shipment_code, "container_no": i.container_no, "level": i.level}
             for i in payload.staff_items + payload.customer_items]
    row = db.execute(text(
        "INSERT INTO notification_logs (recipient, day, status, attempts, last_attempt_at, items) "
        "VALUES (:r, :d, 'PENDING', 1, :now, CAST(:items AS jsonb)) ON CONFLICT (recipient, day) DO NOTHING "
        "RETURNING id"), {"r": payload.email, "d": day, "now": now, "items": json.dumps(items)}).first()
    if row is None:
        row = db.execute(update(NotificationLog).where(
            NotificationLog.recipient == payload.email, NotificationLog.day == day,
            NotificationLog.status == NotificationStatus.FAILED, NotificationLog.last_attempt_at <= now - RETRY_AFTER,
        ).values(status=NotificationStatus.PENDING, attempts=NotificationLog.attempts + 1, last_attempt_at=now,
                 error=None).returning(NotificationLog.id)).first()
    db.commit()
    return row[0] if row else None


def send_due_reminders(db: Session, now: datetime) -> SendSummary:
    """Gửi email nhắc hạn của ngày VN hiện tại (sau 07:00), mỗi người nhận một email, có thử lại khi SMTP lỗi."""
    if now.tzinfo is None:
        raise ValueError("`now` phải có múi giờ")
    now_vn = now.astimezone(VN_TZ)
    summary = SendSummary(stuck=_alert_stuck(db, now))
    if now_vn.hour < REMINDER_HOUR_VN:
        return summary
    day, base_url = now_vn.date(), get_settings().public_base_url.rstrip("/")
    payloads = collect_reminders(db, day)
    for email in sorted(payloads):
        log_id = _claim(db, payloads[email], now, day)
        if log_id is None:
            continue
        subject, html = render_reminder(payloads[email], day, base_url)
        try:
            send_email(email, subject, html)
            values, key = {"status": NotificationStatus.SENT, "sent_at": now}, "sent"
        except MailerError as error:
            values, key = {"status": NotificationStatus.FAILED, "error": str(error)[:ERROR_MAX_CHARS]}, "failed"
            log.warning("Gửi email nhắc hạn %s lỗi: %s", log_id, error)
        db.execute(update(NotificationLog).where(NotificationLog.id == log_id).values(**values))
        db.commit()
        setattr(summary, key, getattr(summary, key) + 1)
    return summary
