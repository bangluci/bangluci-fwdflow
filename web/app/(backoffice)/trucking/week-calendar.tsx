"use client";

import { TruckingStatusBadge } from "@/components/shipment-status";
import { formatTime } from "@/lib/format";
import { TRUCKING_KIND_LABEL } from "@/lib/shipment-labels";
import { shortDate, vnDay, weekdayLabel } from "@/lib/week";
import { cn } from "@/lib/utils";

export type TruckingOrderRow = {
  id: number;
  shipment_id: number;
  shipment_code: string;
  container_id: number;
  container_no: string;
  kind: "PICKUP_FULL" | "RETURN_EMPTY";
  trucker_id: number;
  trucker_name: string;
  truck_id: number | null;
  plate_no: string | null;
  driver_id: number | null;
  driver_name: string | null;
  pickup_location: string;
  drop_location: string;
  planned_at: string;
  status: string;
};

const UNASSIGNED = "__unassigned__";

/** Lưới tuần: hàng là biển số xe (thêm hàng "Chưa gán xe"), cột là ngày. Chỉ hiển thị, chọn thẻ thì báo ra ngoài. */
export function WeekCalendar({ days, orders, today, onSelect }: { days: string[]; orders: TruckingOrderRow[]; today: string; onSelect: (order: TruckingOrderRow) => void }) {
  const rows = new Map<string, { label: string; sub?: string }>();
  for (const order of orders) {
    const key = order.truck_id ? String(order.truck_id) : UNASSIGNED;
    if (!rows.has(key)) rows.set(key, order.truck_id ? { label: order.plate_no ?? `#${order.truck_id}`, sub: order.trucker_name } : { label: "Chưa gán xe" });
  }
  const keys = [...rows.keys()].sort((a, b) => (a === UNASSIGNED ? -1 : b === UNASSIGNED ? 1 : rows.get(a)!.label.localeCompare(rows.get(b)!.label)));
  const at = (key: string, day: string) => orders.filter((o) => (o.truck_id ? String(o.truck_id) : UNASSIGNED) === key && vnDay(o.planned_at) === day);
  const countOf = (day: string) => orders.filter((o) => vnDay(o.planned_at) === day && o.status !== "CANCELLED").length;
  return (
    <div className="overflow-auto rounded-lg border bg-card">
      <div className="grid min-w-[62rem]" style={{ gridTemplateColumns: "9.5rem repeat(7, minmax(0, 1fr))" }}>
        <div className="sticky left-0 z-[1] border-b bg-muted/90 px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Xe</div>
        {days.map((day) => (
          <div key={day} className={cn("border-b border-l bg-muted/90 px-2 py-2 text-center", day === today && "bg-accent")}>
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{weekdayLabel(day)} {shortDate(day)}</p>
            <p className="text-xs">{countOf(day)} lệnh</p>
          </div>
        ))}
        {keys.length === 0 && <p className="col-span-8 px-6 py-14 text-center text-sm text-muted-foreground">Tuần này chưa có lệnh xe nào</p>}
        {keys.map((key) => (
          <div key={key} className="contents">
            <div className="sticky left-0 z-[1] border-b bg-card px-3 py-2">
              <p className={cn("font-mono text-xs font-semibold", key === UNASSIGNED && "font-sans text-muted-foreground")}>{rows.get(key)!.label}</p>
              {rows.get(key)!.sub && <p className="text-[11px] text-muted-foreground">{rows.get(key)!.sub}</p>}
            </div>
            {days.map((day) => (
              <div key={day} className={cn("min-h-16 space-y-1 border-b border-l p-1", day === today && "bg-accent/30")}>
                {at(key, day).map((order) => (
                  <button
                    key={order.id}
                    type="button"
                    onClick={() => onSelect(order)}
                    className={cn(
                      "w-full rounded-md border-l-[3px] px-1.5 py-1 text-left text-[11px] leading-tight shadow-xs transition-colors hover:brightness-95",
                      order.kind === "PICKUP_FULL" ? "border-l-info bg-info-soft/60" : "border-l-muted-foreground bg-muted",
                      order.status === "CANCELLED" && "opacity-55 line-through",
                    )}
                  >
                    <span className="flex items-center justify-between gap-1">
                      <span className="font-semibold">{formatTime(order.planned_at)} · {TRUCKING_KIND_LABEL[order.kind]}</span>
                    </span>
                    <span className="block truncate font-mono">{order.container_no}</span>
                    <span className="mt-0.5 block"><TruckingStatusBadge status={order.status} /></span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
