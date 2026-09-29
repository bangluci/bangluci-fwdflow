import { StatusBadge } from "@/components/status-badge";
import {
  LAST_MILE_STATUS_LABEL,
  LAST_MILE_STATUS_STYLE,
  STATUS_LABEL,
  STATUS_STYLE,
  TRUCKING_STATUS_LABEL,
  TRUCKING_STATUS_STYLE,
  type ShipmentStatus,
} from "@/lib/shipment-labels";

export function ShipmentStatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status as ShipmentStatus] ?? { tone: "neutral" as const, icon: undefined };
  return (
    <StatusBadge tone={style.tone} icon={style.icon}>
      {STATUS_LABEL[status as ShipmentStatus] ?? status}
    </StatusBadge>
  );
}

export function TruckingStatusBadge({ status }: { status: string }) {
  const style = TRUCKING_STATUS_STYLE[status] ?? { tone: "neutral" as const, icon: undefined };
  return (
    <StatusBadge tone={style.tone} icon={style.icon}>
      {TRUCKING_STATUS_LABEL[status] ?? status}
    </StatusBadge>
  );
}

export function LastMileStatusBadge({ status }: { status: string }) {
  const style = LAST_MILE_STATUS_STYLE[status] ?? { tone: "neutral" as const, icon: undefined };
  return (
    <StatusBadge tone={style.tone} icon={style.icon}>
      {LAST_MILE_STATUS_LABEL[status] ?? status}
    </StatusBadge>
  );
}
