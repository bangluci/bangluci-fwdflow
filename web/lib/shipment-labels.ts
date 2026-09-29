// Nhãn tiếng Việt và cách vẽ trạng thái của lô, đơn giao, lệnh xe. Khớp enum trong api/app/*/state.py.

import {
  Anchor,
  Ban,
  BadgeCheck,
  CircleCheck,
  ClipboardCheck,
  CircleDashed,
  FilePlus2,
  PackageCheck,
  Ship,
  Truck,
  Warehouse,
  type LucideIcon,
} from "lucide-react";
import type { Tone } from "@/components/status-badge";

export const SHIPMENT_STATUSES = [
  "CREATED",
  "IN_TRANSIT",
  "ARRIVED",
  "CUSTOMS_CLEARING",
  "CLEARED",
  "AT_WAREHOUSE",
  "DELIVERING",
  "COMPLETED",
  "CANCELLED",
] as const;
export type ShipmentStatus = (typeof SHIPMENT_STATUSES)[number];
export const ACTIVE_SHIPMENT_STATUSES = SHIPMENT_STATUSES.filter((s) => s !== "COMPLETED" && s !== "CANCELLED");

export const STATUS_LABEL: Record<ShipmentStatus, string> = {
  CREATED: "Mới tạo",
  IN_TRANSIT: "Đang vận chuyển",
  ARRIVED: "Đã đến cảng",
  CUSTOMS_CLEARING: "Đang làm thủ tục HQ",
  CLEARED: "Đã thông quan",
  AT_WAREHOUSE: "Đã về kho",
  DELIVERING: "Đang giao",
  COMPLETED: "Hoàn tất",
  CANCELLED: "Đã huỷ",
};

// Trạng thái quy trình dùng màu trung tính / xanh dương + biểu tượng riêng; đỏ dành cho free time quá hạn và thất bại.
export const STATUS_STYLE: Record<ShipmentStatus, { tone: Tone; icon: LucideIcon }> = {
  CREATED: { tone: "pending", icon: FilePlus2 },
  IN_TRANSIT: { tone: "info", icon: Ship },
  ARRIVED: { tone: "info", icon: Anchor },
  CUSTOMS_CLEARING: { tone: "info", icon: ClipboardCheck },
  CLEARED: { tone: "info", icon: BadgeCheck },
  AT_WAREHOUSE: { tone: "info", icon: Warehouse },
  DELIVERING: { tone: "info", icon: Truck },
  COMPLETED: { tone: "success", icon: CircleCheck },
  CANCELLED: { tone: "neutral", icon: Ban },
};

export const LOAD_TYPE_LABEL = { FCL: "FCL", LCL: "LCL" } as const;
export const DELIVERY_MODE_LABEL = { VIA_WAREHOUSE: "Qua kho", CONTAINER_TO_DOOR: "Container tới cửa" } as const;

export const TRUCKING_STATUS_LABEL: Record<string, string> = {
  PLANNED: "Chưa gán",
  ASSIGNED: "Đã phân công",
  STARTED: "Đang chạy",
  COMPLETED: "Hoàn tất",
  CANCELLED: "Đã huỷ",
};
export const TRUCKING_STATUS_STYLE: Record<string, { tone: Tone; icon: LucideIcon }> = {
  PLANNED: { tone: "pending", icon: CircleDashed },
  ASSIGNED: { tone: "info", icon: Truck },
  STARTED: { tone: "info", icon: Truck },
  COMPLETED: { tone: "success", icon: CircleCheck },
  CANCELLED: { tone: "neutral", icon: Ban },
};
export const TRUCKING_KIND_LABEL: Record<string, string> = { PICKUP_FULL: "Lấy cont", RETURN_EMPTY: "Trả vỏ rỗng" };

export const LAST_MILE_STATUS_LABEL: Record<string, string> = {
  CREATED: "Chờ phân công",
  ASSIGNED: "Chờ giao",
  PICKED_UP: "Đang giao",
  DELIVERED: "Đã giao",
  FAILED: "Giao thất bại",
  RETURNED: "Đã hoàn về kho",
  CANCELLED: "Đã huỷ",
};
export const LAST_MILE_STATUS_STYLE: Record<string, { tone: Tone; icon: LucideIcon }> = {
  CREATED: { tone: "pending", icon: CircleDashed },
  ASSIGNED: { tone: "info", icon: Truck },
  PICKED_UP: { tone: "info", icon: PackageCheck },
  DELIVERED: { tone: "success", icon: CircleCheck },
  FAILED: { tone: "danger", icon: Ban },
  RETURNED: { tone: "neutral", icon: Warehouse },
  CANCELLED: { tone: "neutral", icon: Ban },
};

export const DOC_TYPE_LABEL: Record<string, string> = {
  MBL: "MBL",
  HBL: "HBL",
  INVOICE: "Hoá đơn",
  PACKING_LIST: "Packing list",
  CUSTOMS_DECLARATION: "Tờ khai",
  DO: "D/O",
  ARRIVAL_NOTICE: "Thông báo hàng đến",
  ORIGIN_PROOF: "Chứng nhận xuất xứ",
  SPECIALIZED_INSPECTION: "Kiểm tra chuyên ngành",
  OTHER: "Khác",
};

export const LANE_LABEL: Record<string, string> = { GREEN: "Luồng xanh", YELLOW: "Luồng vàng", RED: "Luồng đỏ" };
