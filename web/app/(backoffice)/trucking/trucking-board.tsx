"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { todayVn } from "@/lib/format";
import { useMe } from "@/lib/use-me";
import { addDays, shortDate, startOfWeek, weekDays } from "@/lib/week";
import { CreateOrderDialog } from "./create-order-dialog";
import { OrderDialog } from "./order-dialog";
import { WeekCalendar, type TruckingOrderRow } from "./week-calendar";

export function TruckingBoard() {
  const { data: me } = useMe();
  const today = todayVn();
  const [start, setStart] = useState(() => startOfWeek(today));
  const [selected, setSelected] = useState<TruckingOrderRow | null>(null);
  const [creating, setCreating] = useState(false);
  const days = weekDays(start);
  const orders = useQuery({
    queryKey: ["trucking-orders", start],
    queryFn: () => apiFetch<TruckingOrderRow[]>(`/api/trucking-orders?date_from=${days[0]}&date_to=${days[6]}`),
  });
  const can = (action: string) => !!me?.permissions.includes(action);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" aria-label="Tuần trước" onClick={() => setStart(addDays(start, -7))}><ChevronLeft /></Button>
          <Button variant="outline" onClick={() => setStart(startOfWeek(today))}>Tuần này</Button>
          <Button variant="outline" size="icon" aria-label="Tuần sau" onClick={() => setStart(addDays(start, 7))}><ChevronRight /></Button>
        </div>
        <p className="text-sm font-medium">{shortDate(days[0])} – {shortDate(days[6])}/{days[6].slice(0, 4)}</p>
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="h-3 w-1 rounded-sm bg-info" aria-hidden />Lấy cont đầy</span>
          <span className="flex items-center gap-1"><span className="h-3 w-1 rounded-sm bg-muted-foreground" aria-hidden />Trả vỏ rỗng</span>
          {can("transport.write") && <Button onClick={() => setCreating(true)}><Plus />Tạo lệnh</Button>}
        </div>
      </div>
      {orders.error ? (
        <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border bg-card p-10 text-center">
          <p className="text-sm">{orders.error.message}</p>
          <Button variant="outline" size="sm" onClick={() => orders.refetch()}>Thử lại</Button>
        </div>
      ) : (
        <WeekCalendar days={days} orders={orders.data ?? []} today={today} onSelect={setSelected} />
      )}
      {selected && (
        <OrderDialog order={selected} canWrite={can("transport.write")} canVoid={can("transport.void_event")} canRetime={can("container.retime_event")} onClose={() => setSelected(null)} />
      )}
      {creating && <CreateOrderDialog defaultDay={days.includes(today) ? today : days[0]} onClose={() => setCreating(false)} />}
    </div>
  );
}
