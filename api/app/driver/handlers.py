"""Đăng ký handler cho từng thao tác trong bảng `ACTIONS`."""

from app.driver.actions import HANDLERS
from app.lastmile.service import deliver_order, fail_order, pick_up_order
from app.trucking.service import complete_order, start_order

HANDLERS.update({"TRUCK_START": start_order, "RETURN_START": start_order, "TRUCK_COMPLETE": complete_order,
                 "RETURN_COMPLETE": complete_order, "LM_PICK_UP": pick_up_order, "LM_DELIVER": deliver_order,
                 "LM_FAIL": fail_order})
