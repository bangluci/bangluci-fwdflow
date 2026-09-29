"""Quy tắc free time theo phiên bản, override theo lô và danh sách đồng hồ (view dùng chung với email, AI #3)."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import record_audit, register_audit_fields, snapshot
from app.auth.models import User
from app.catalog.models import Carrier, Port
from app.documents.models import Document
from app.envelope import AppError
from app.freetime.models import FreeTimeRule, FreeTimeTier, ShipmentFreeTimeOverride
from app.freetime.schemas import OverrideIn, RuleVersionIn
from app.freetime.tiers import TierIn, validate_fee_type_set, validate_tiers
from app.shipments.iso6346 import normalize_container_no
from app.shipments.service import assert_open, lock_shipment

RULE_FIELDS = ("carrier_id", "port_id", "container_type", "fee_type", "free_days", "effective_from")
TIER_FIELDS = ("rule_id", "from_day", "to_day", "rate_amount", "currency")
OVERRIDE_FIELDS = ("shipment_id", "fee_type", "free_days", "source", "document_id")
register_audit_fields("free_time_rule", RULE_FIELDS)
register_audit_fields("free_time_tier", TIER_FIELDS)
register_audit_fields("shipment_free_time_override", OVERRIDE_FIELDS)

SOURCE_DOC_TYPE = {"ARRIVAL_NOTICE": "ARRIVAL_NOTICE", "DO": "DO", "CONTRACT": "OTHER"}


def _today(db: Session) -> date:
    return db.scalar(text("SELECT nlq_today()"))


def _active_reference(db: Session, model: type, ref_id: int, label: str) -> None:
    ref = db.get(model, ref_id)
    if ref is None or not ref.active:
        raise AppError("INACTIVE_REFERENCE", f"{label} không tồn tại hoặc đã ngừng dùng", 400)


def _version_filter(carrier_id: int, port_id: int, container_type: str, effective_from: date) -> tuple:
    return (FreeTimeRule.carrier_id == carrier_id, FreeTimeRule.port_id == port_id,
            FreeTimeRule.container_type == container_type, FreeTimeRule.effective_from == effective_from)


def create_rule_version(db: Session, data: RuleVersionIn, actor: User) -> list[FreeTimeRule]:
    _active_reference(db, Carrier, data.carrier_id, "Hãng tàu")
    _active_reference(db, Port, data.port_id, "Cảng")
    validate_fee_type_set(rule.fee_type for rule in data.rules)
    for rule in data.rules:
        validate_tiers(rule.free_days, [TierIn(t.from_day, t.to_day, t.rate_amount, t.currency) for t in rule.tiers])
    key = _version_filter(data.carrier_id, data.port_id, data.container_type, data.effective_from)
    if db.scalar(select(FreeTimeRule.id).where(*key).limit(1)) is not None:
        raise AppError("RULE_VERSION_EXISTS", "Đã có phiên bản quy tắc cùng hãng tàu, cảng, loại container và ngày "
                       "hiệu lực; muốn đổi hãy thêm phiên bản với ngày hiệu lực mới", 409)
    made = []
    try:
        for body in data.rules:
            rule = FreeTimeRule(carrier_id=data.carrier_id, port_id=data.port_id, container_type=data.container_type,
                                fee_type=body.fee_type, free_days=body.free_days, effective_from=data.effective_from,
                                created_by=actor.id)
            db.add(rule)
            db.flush()
            record_audit(db, actor.id, "CREATE", "free_time_rule", rule.id, after=snapshot(rule, RULE_FIELDS))
            for tier in body.tiers:
                row = FreeTimeTier(rule_id=rule.id, **tier.model_dump())
                db.add(row)
                db.flush()
                record_audit(db, actor.id, "CREATE", "free_time_tier", row.id, after=snapshot(row, TIER_FIELDS))
            made.append(rule)
    except IntegrityError as exc:
        db.rollback()
        raise AppError("RULE_VERSION_EXISTS", "Phiên bản quy tắc này đã tồn tại", 409) from exc
    return made


def _tiers_of(db: Session, rule_ids: list[int]) -> dict[int, list[dict]]:
    tiers: dict[int, list[dict]] = {rule_id: [] for rule_id in rule_ids}
    for tier in db.scalars(select(FreeTimeTier).where(FreeTimeTier.rule_id.in_(rule_ids)).order_by(
            FreeTimeTier.rule_id, FreeTimeTier.from_day)):
        tiers[tier.rule_id].append({"from_day": tier.from_day, "to_day": tier.to_day,
                                    "rate_amount": tier.rate_amount, "currency": tier.currency})
    return tiers


def list_rule_versions(db: Session, carrier_id: int | None, port_id: int | None,
                       container_type: str | None) -> list[dict[str, Any]]:
    stmt = (select(FreeTimeRule, Carrier.name, Port.code).join(Carrier, Carrier.id == FreeTimeRule.carrier_id)
            .join(Port, Port.id == FreeTimeRule.port_id)
            .order_by(Carrier.name, Port.code, FreeTimeRule.container_type, FreeTimeRule.effective_from.desc(),
                      FreeTimeRule.fee_type))
    for column, value in ((FreeTimeRule.carrier_id, carrier_id), (FreeTimeRule.port_id, port_id),
                          (FreeTimeRule.container_type, container_type)):
        if value is not None:
            stmt = stmt.where(column == value)
    rows = db.execute(stmt).all()
    tiers = _tiers_of(db, [rule.id for rule, _, _ in rows])
    today, versions = _today(db), {}
    for rule, carrier_name, port_code in rows:
        key = (rule.carrier_id, rule.port_id, rule.container_type, rule.effective_from)
        version = versions.setdefault(key, {
            "carrier_id": rule.carrier_id, "carrier_name": carrier_name, "port_id": rule.port_id,
            "port_code": port_code, "container_type": rule.container_type, "effective_from": rule.effective_from,
            "editable": rule.effective_from > today, "rules": []})
        version["rules"].append({"id": rule.id, "fee_type": rule.fee_type, "free_days": rule.free_days,
                                 "tiers": tiers[rule.id]})
    return list(versions.values())


def delete_rule_version(db: Session, rule_id: int, actor: User) -> None:
    rule = db.get(FreeTimeRule, rule_id)
    if rule is None:
        raise AppError("NOT_FOUND", "Không tìm thấy quy tắc", 404)
    if rule.effective_from <= _today(db):
        raise AppError("RULE_ALREADY_EFFECTIVE", "Phiên bản đã hiệu lực, không xoá được; hãy thêm phiên bản mới", 409)
    siblings = db.scalars(select(FreeTimeRule).where(*_version_filter(
        rule.carrier_id, rule.port_id, rule.container_type, rule.effective_from))).all()
    for sibling in siblings:
        before = snapshot(sibling, RULE_FIELDS)
        db.delete(sibling)
        db.flush()
        record_audit(db, actor.id, "DELETE", "free_time_rule", sibling.id, before=before)


def list_overrides(db: Session, shipment_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(ShipmentFreeTimeOverride).where(ShipmentFreeTimeOverride.shipment_id == shipment_id)
                      .order_by(ShipmentFreeTimeOverride.fee_type))
    return [{"fee_type": r.fee_type, "free_days": r.free_days, "source": r.source, "document_id": r.document_id,
             "updated_at": r.updated_at} for r in rows]


def _check_override_document(db: Session, shipment_id: int, data: OverrideIn) -> None:
    if data.document_id is None:
        return
    document = db.get(Document, data.document_id)
    if (document is None or document.shipment_id != shipment_id or document.superseded_by_id is not None
            or document.doc_type != SOURCE_DOC_TYPE[data.source]):
        raise AppError("INVALID_DOCUMENT", "Chứng từ phải thuộc lô, còn hiệu lực và đúng loại với nguồn đã chọn", 400)


def put_override(db: Session, shipment_id: int, data: OverrideIn, actor: User) -> ShipmentFreeTimeOverride:
    assert_open(lock_shipment(db, shipment_id))
    others = set(db.scalars(select(ShipmentFreeTimeOverride.fee_type).where(
        ShipmentFreeTimeOverride.shipment_id == shipment_id, ShipmentFreeTimeOverride.fee_type != data.fee_type)))
    if (data.fee_type == "COMBINED" and others) or (data.fee_type != "COMBINED" and "COMBINED" in others):
        raise AppError("INVALID_OVERRIDE_SET", "COMBINED không dùng chung với DEM / DET trên cùng một lô", 400)
    _check_override_document(db, shipment_id, data)
    row = db.scalar(select(ShipmentFreeTimeOverride).where(ShipmentFreeTimeOverride.shipment_id == shipment_id,
                                                           ShipmentFreeTimeOverride.fee_type == data.fee_type))
    before = None if row is None else snapshot(row, OVERRIDE_FIELDS)
    if row is None:
        row = ShipmentFreeTimeOverride(shipment_id=shipment_id, fee_type=data.fee_type, created_by=actor.id)
        db.add(row)
    row.free_days, row.source, row.document_id = data.free_days, data.source, data.document_id
    db.flush()
    record_audit(db, actor.id, "CREATE" if before is None else "UPDATE", "shipment_free_time_override", row.id,
                 before=before, after=snapshot(row, OVERRIDE_FIELDS))
    return row


def delete_override(db: Session, shipment_id: int, fee_type: str, actor: User) -> None:
    assert_open(lock_shipment(db, shipment_id))
    row = db.scalar(select(ShipmentFreeTimeOverride).where(ShipmentFreeTimeOverride.shipment_id == shipment_id,
                                                           ShipmentFreeTimeOverride.fee_type == fee_type))
    if row is None:
        raise AppError("NOT_FOUND", "Không có override này", 404)
    before = snapshot(row, OVERRIDE_FIELDS)
    db.delete(row)
    db.flush()
    record_audit(db, actor.id, "DELETE", "shipment_free_time_override", row.id, before=before)


@dataclass
class ClockFilters:
    levels: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    fee_types: list[str] = field(default_factory=list)
    shipment_id: int | None = None
    customer_id: int | None = None
    carrier_id: int | None = None
    q: str | None = None
    include_cancelled: bool = False
    page: int = 1
    limit: int = 50


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_freetime_containers(db: Session, f: ClockFilters) -> tuple[list[dict[str, Any]], int]:
    """Một dòng mỗi đồng hồ, đọc từ `nlq.v_container_freetime` (cùng logic với email nhắc hạn và AI #3)."""
    where, params = ["TRUE"], {"limit": f.limit, "offset": (f.page - 1) * f.limit}
    for column, values, name in (("v.level", f.levels, "levels"), ("v.status", f.statuses, "statuses"),
                                 ("v.fee_type", f.fee_types, "fee_types")):
        if values:
            where.append(f"{column} = ANY(:{name})")
            params[name] = values
    for column, value, name in (("v.shipment_id", f.shipment_id, "shipment_id"), ("s.customer_id", f.customer_id,
                                                                                  "customer_id"),
                                ("s.carrier_id", f.carrier_id, "carrier_id")):
        if value is not None:
            where.append(f"{column} = :{name}")
            params[name] = value
    if f.q and f.q.strip():
        where.append("(v.shipment_code ILIKE :q ESCAPE '\\' OR v.container_no LIKE :cq ESCAPE '\\')")
        params["q"], params["cq"] = _like(f.q.strip()), _like(normalize_container_no(f.q.strip()))
    if not f.include_cancelled:
        where.append("v.shipment_status <> 'CANCELLED'")
    clause = " AND ".join(where)
    source = "FROM nlq.v_container_freetime v JOIN shipments s ON s.id = v.shipment_id WHERE " + clause
    total = db.scalar(text(f"SELECT count(*) {source}"), params)  # noqa: S608 - chỉ ghép cột cố định, giá trị là tham số
    rows = db.execute(text(
        f"SELECT v.* {source} ORDER BY freetime_level_rank(v.container_level) DESC NULLS LAST, "  # noqa: S608
        "v.due_date ASC NULLS LAST, v.container_no, v.fee_type LIMIT :limit OFFSET :offset"), params).mappings().all()
    return [dict(row) for row in rows], int(total)
