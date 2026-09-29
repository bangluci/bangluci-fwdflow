"""Fixture tạo lô hàng / container cho test, ghi thẳng qua ORM (đăng ký trong conftest bằng pytest_plugins)."""

import secrets
from datetime import UTC, datetime, timedelta

import pytest

from app.catalog.models import Carrier, Customer, Port
from app.documents.models import DEFAULT_VISIBLE_TYPES, DocType, Document
from app.shipments.iso6346 import container_check_digit
from app.shipments.models import Container, ContainerEvent, Shipment, ShipmentEvent

MAIN_PATH = ["CREATED", "IN_TRANSIT", "ARRIVED", "CUSTOMS_CLEARING", "CLEARED", "AT_WAREHOUSE", "DELIVERING",
             "COMPLETED"]


def _get_or_create(db, model, code, **fields):
    obj = db.query(model).filter_by(code=code).one_or_none()
    if obj is None:
        obj = model(code=code, **fields)
        db.add(obj)
        db.flush()
    return obj


@pytest.fixture
def make_shipment(db, make_user):
    """Lô đã điền đủ thông tin; ghi chuỗi TRANSITION theo đường chính tới `status` (CANCELLED đi từ CREATED)."""

    def _make(status: str = "CREATED", load_type: str = "FCL", delivery_mode: str = "VIA_WAREHOUSE",
              customer: Customer | None = None, **fields) -> Shipment:
        if customer is None:
            customer = Customer(name="KH Test")
            db.add(customer)
            db.flush()
        defaults = {
            "staff_id": fields.pop("staff_id", None) or make_user("DOCS").id,
            "carrier_id": _get_or_create(db, Carrier, "MAEU", name="Maersk").id,
            "pol_port_id": _get_or_create(db, Port, "CNSHA", name="Shanghai").id,
            "pod_port_id": _get_or_create(db, Port, "VNSGN", name="Cat Lai").id,
            "mbl_no": "MAEU000001",
            "eta": datetime.now(UTC).date() + timedelta(days=10),
            "total_packages": 100,
        }
        shipment = Shipment(load_type=load_type, delivery_mode=delivery_mode, customer_id=customer.id,
                            **{**defaults, **fields})
        db.add(shipment)
        db.flush()
        path = ["CREATED", "CANCELLED"] if status == "CANCELLED" else MAIN_PATH[: MAIN_PATH.index(status) + 1]
        for previous, current in zip([None, *path], path, strict=False):
            db.add(ShipmentEvent(shipment_id=shipment.id, kind="TRANSITION", from_status=previous, to_status=current,
                                 occurred_at=datetime.now(UTC)))
        shipment.status = status
        db.flush()
        return shipment

    return _make


@pytest.fixture
def make_container(db):
    """Container hợp lệ ISO 6346; `milestones={kind: datetime}` ghi các mốc theo thứ tự truyền vào."""
    counter = iter(range(1, 1_000_000))

    def _make(shipment: Shipment, container_no: str | None = None, container_type: str = "40HC",
              milestones: dict[str, datetime] | None = None, **fields) -> Container:
        if container_no is None:
            prefix = f"TSTU{next(counter):06d}"
            container_no = prefix + str(container_check_digit(prefix))
        container = Container(shipment_id=shipment.id, container_no=container_no, container_type=container_type,
                              **fields)
        db.add(container)
        db.flush()
        for kind, occurred_at in (milestones or {}).items():
            db.add(ContainerEvent(container_id=container.id, kind=kind, occurred_at=occurred_at))
            container.status = kind
        db.flush()
        return container

    return _make


@pytest.fixture
def make_document(db, make_user):
    """Chứng từ đã lưu metadata (không có file trên đĩa); sha256 ngẫu nhiên, duy nhất."""

    def _make(shipment: Shipment, doc_type: str = "INVOICE", superseded_by: Document | None = None,
              **fields) -> Document:
        document = Document(shipment_id=shipment.id, doc_type=doc_type, file_sha256=secrets.token_hex(32),
                            mime="application/pdf", size_bytes=1000, pages=1,
                            visible_to_customer=DocType(doc_type) in DEFAULT_VISIBLE_TYPES,
                            uploaded_by=fields.pop("uploaded_by", None) or make_user("DOCS").id, **fields)
        db.add(document)
        db.flush()
        if superseded_by is not None:
            raise ValueError("Dùng make_document(old) rồi gán old.superseded_by_id = new.id")
        return document

    return _make


@pytest.fixture
def make_required_documents(make_document):
    """Tạo đủ chứng từ bắt buộc cho một lô FCL không FTA tới mốc CLEARED."""

    def _make(shipment: Shipment) -> list[Document]:
        types = ["MBL", "HBL", "INVOICE", "PACKING_LIST", "ARRIVAL_NOTICE", "CUSTOMS_DECLARATION", "DO"]
        return [make_document(shipment, doc_type) for doc_type in types]

    return _make
