from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.auth.models import User
from app.auth.scope import scope_trucking
from app.db import get_db
from app.driver import handlers  # noqa: F401  đăng ký HANDLERS
from app.driver.actions import ACTION_LIST, requires_for
from app.driver.process import parse_form, process_driver_action
from app.envelope import ok
from app.shipments.models import Container, Shipment
from app.shipments.state import ShipmentStatus
from app.trucking.models import TruckingOrder
from app.trucking.queries import PLANNED_DAY_VN

router = APIRouter(tags=["driver"])
Db = Annotated[Session, Depends(get_db)]
DriverUser = Annotated[User, Depends(require("driver.act"))]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
TITLES = {"PICKUP_FULL": "Lấy cont", "RETURN_EMPTY": "Trả vỏ rỗng"}


def _item(order: TruckingOrder, shipment: Shipment, container: Container) -> dict:
    actions = [{"action": a.code, "label": a.label, "requires": requires_for(a, shipment)}
               for a in ACTION_LIST if a.order_kind == order.kind and a.from_status == order.status]
    return {"kind": "TRUCKING", "id": order.id, "order_kind": order.kind, "title": TITLES[order.kind],
            "status": order.status, "planned_at": order.planned_at.astimezone(VN).isoformat(),
            "shipment_code": shipment.code, "container_no": container.container_no,
            "container_type": container.container_type, "seal_no": container.seal_no,
            "pickup_location": order.pickup_location, "drop_location": order.drop_location,
            "delivery_mode": shipment.delivery_mode, "actions": actions}


@router.get("/driver/tasks")
def list_tasks(db: Db, user: DriverUser) -> dict:
    """Việc của tài xế: lệnh đã phân công cho hôm nay, cộng lệnh đang chạy dở bất kể ngày."""
    today: date = db.scalar(text("SELECT nlq_today()"))
    stmt = (select(TruckingOrder, Shipment, Container)
            .join(Shipment, Shipment.id == TruckingOrder.shipment_id)
            .join(Container, Container.id == TruckingOrder.container_id)
            .where(Shipment.status != ShipmentStatus.CANCELLED,
                   or_(and_(TruckingOrder.status == "ASSIGNED", PLANNED_DAY_VN == today),
                       TruckingOrder.status == "STARTED"))
            .order_by(TruckingOrder.planned_at, TruckingOrder.id))
    return ok([_item(*row) for row in db.execute(scope_trucking(stmt, user))])


@router.post("/driver/actions")
def post_action(db: Db, user: DriverUser, client_request_id: Annotated[str, Form()], action: Annotated[str, Form()],
                target_id: Annotated[str, Form()], photo: Annotated[UploadFile | None, File()] = None,
                lat: Annotated[str | None, Form()] = None, lng: Annotated[str | None, Form()] = None,
                device_time: Annotated[str | None, Form()] = None, signer_name: Annotated[str | None, Form()] = None,
                reason: Annotated[str | None, Form()] = None) -> dict:
    form = parse_form(client_request_id, action, target_id, lat, lng, device_time, signer_name, reason)
    result = process_driver_action(db, user, form, photo)
    db.commit()
    return ok({"event_id": result.event_id, "target_kind": result.target_kind, "target_id": result.target_id,
               "status": result.status, "occurred_at": result.occurred_at}, meta={"replayed": result.replayed})
