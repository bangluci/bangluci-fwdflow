"""Phân quyền theo dòng dữ liệu: khách chỉ thấy lô của mình, tài xế không thấy lô. Không thuộc về mình → 404."""

from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from app.auth.models import Role, User
from app.envelope import AppError
from app.shipments.models import Container, Shipment


def scope_shipments(stmt: Select, user: User) -> Select:
    if user.role == Role.CUSTOMER:
        return stmt.where(Shipment.customer_id == user.customer_id)
    if user.role == Role.DRIVER:
        return stmt.where(false())
    return stmt


def get_scoped_or_404(db: Session, model: type[Shipment] | type[Container], obj_id: int, user: User):
    """`Shipment` hoặc `Container` (qua lô của nó). Id không tồn tại và id của người khác trả lỗi giống hệt nhau."""
    if model is Shipment:
        stmt = select(Shipment).where(Shipment.id == obj_id)
    elif model is Container:
        stmt = select(Container).join(Shipment, Shipment.id == Container.shipment_id).where(Container.id == obj_id)
    else:
        raise TypeError(f"Chưa hỗ trợ scope cho {model.__name__}")
    obj = db.scalar(scope_shipments(stmt, user))
    if obj is None:
        raise AppError("NOT_FOUND", "Không tìm thấy", 404)
    return obj
