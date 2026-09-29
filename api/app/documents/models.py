from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models_base import Base


class DocType(StrEnum):
    MBL = "MBL"
    HBL = "HBL"
    INVOICE = "INVOICE"
    PACKING_LIST = "PACKING_LIST"
    CUSTOMS_DECLARATION = "CUSTOMS_DECLARATION"
    DO = "DO"
    ARRIVAL_NOTICE = "ARRIVAL_NOTICE"
    ORIGIN_PROOF = "ORIGIN_PROOF"
    SPECIALIZED_INSPECTION = "SPECIALIZED_INSPECTION"
    OTHER = "OTHER"


# Mặc định khách xem được; các loại còn lại (MBL, D/O, thông báo hàng đến...) là nội bộ.
DEFAULT_VISIBLE_TYPES = frozenset({DocType.HBL, DocType.INVOICE, DocType.PACKING_LIST, DocType.CUSTOMS_DECLARATION,
                                   DocType.ORIGIN_PROOF})

DOC_TYPE_LABELS = {
    DocType.MBL: "MBL", DocType.HBL: "HBL", DocType.INVOICE: "Hoá đơn", DocType.PACKING_LIST: "Packing list",
    DocType.CUSTOMS_DECLARATION: "Tờ khai", DocType.DO: "D/O", DocType.ARRIVAL_NOTICE: "Thông báo hàng đến",
    DocType.ORIGIN_PROOF: "Chứng nhận xuất xứ", DocType.SPECIALIZED_INSPECTION: "Kiểm tra chuyên ngành",
    DocType.OTHER: "Khác",
}


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    doc_type: Mapped[str] = mapped_column(String)
    file_sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    pages: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str | None] = mapped_column(String)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    visible_to_customer: Mapped[bool] = mapped_column(Boolean)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequiredDocRule(Base):
    __tablename__ = "required_doc_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    load_type: Mapped[str] = mapped_column(String)
    claims_fta: Mapped[bool | None] = mapped_column(Boolean)
    doc_type: Mapped[str] = mapped_column(String)
    required_from_status: Mapped[str] = mapped_column(String)
