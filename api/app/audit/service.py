"""Audit log: chỉ ghi cột được phép; cột bí mật ghi "<changed>"; cột PII ghi dạng che."""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.audit.models import AuditLog

SECRET_FIELDS = frozenset({"password_hash", "token_hash"})
PII_FIELDS = frozenset({"phone", "email", "address", "recipient_phone", "recipient_address", "lat", "lng",
                        "tax_code"})

# entity -> các cột được phép vào audit (ngoài SECRET/PII được xử lý riêng)
AUDIT_FIELDS: dict[str, frozenset[str]] = {}


def register_audit_fields(entity: str, fields: Iterable[str]) -> None:
    AUDIT_FIELDS[entity] = frozenset(fields)


def mask(field: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if field in ("email",) and "@" in text:
        name, _, domain = text.partition("@")
        return f"{name[:1]}***@{domain}"
    if field in ("phone", "recipient_phone", "tax_code"):
        return text[:2] + "*" * max(len(text) - 4, 2) + text[-2:]
    return "***"


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return "<bytes>"
    return value


def _clean(entity: str, data: dict | None, other: dict | None) -> dict | None:
    if data is None:
        return None
    if entity not in AUDIT_FIELDS:
        raise ValueError(f"Entity '{entity}' chưa đăng ký AUDIT_FIELDS")
    allowed = AUDIT_FIELDS[entity]
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in SECRET_FIELDS:
            if other is None or other.get(key) != value:
                out[key] = "<changed>"
        elif key in PII_FIELDS and key in allowed:
            out[key] = mask(key, value)
        elif key in allowed:
            out[key] = _jsonable(value)
    return out


def snapshot(obj: Any, fields: Iterable[str]) -> dict:
    return {f: getattr(obj, f) for f in fields}


def record_audit(
    db: DbSession,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: Any,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
) -> None:
    """Thêm dòng audit vào cùng transaction (không commit)."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            before=_clean(entity, before, after),
            after=_clean(entity, after, before),
            ip=ip or db.info.get("ip"),
        )
    )


register_audit_fields("user", {"email", "phone", "full_name", "role", "customer_id", "driver_id", "is_active"})
register_audit_fields("login", {"identifier", "result"})
