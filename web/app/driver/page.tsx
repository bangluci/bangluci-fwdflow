"use client";

import { useQuery } from "@tanstack/react-query";
import { MapPin, Phone, RefreshCw } from "lucide-react";
import Link from "next/link";
import { OutboxBar } from "@/components/outbox-bar";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { taskPath, type DriverTask } from "@/lib/driver-types";
import { formatDate, formatTime } from "@/lib/format";
import { LAST_MILE_STATUS_LABEL } from "@/lib/shipment-labels";
import { useOutbox } from "@/lib/use-outbox";

const mapsLink = (address: string) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;

function TaskCard({ task }: { task: DriverTask }) {
  const running = task.status === "STARTED" || task.status === "PICKED_UP";
  const badge = (
    <StatusBadge tone={running ? "info" : "pending"} className="h-6 px-2.5 text-[13px]">
      {task.kind === "TRUCKING" ? (running ? "Đang chạy" : "Chờ chạy") : (running ? "Đang giao" : LAST_MILE_STATUS_LABEL[task.status] ?? task.status)}
    </StatusBadge>
  );
  return (
    <div data-testid="task-card" className="rounded-xl border bg-card shadow-xs">
      <Link href={taskPath(task)} className="block space-y-2 p-4 active:bg-accent/60">
        {task.kind === "TRUCKING" ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <p className="text-xl font-semibold leading-tight">{task.title}</p>
              <p className="text-xl font-semibold tabular-nums">{formatTime(task.planned_at)}</p>
            </div>
            <p className="font-mono text-base font-semibold">{task.container_no} <span className="font-sans text-sm font-normal text-muted-foreground">{task.container_type}</span></p>
            <p className="text-[15px] text-muted-foreground">{task.pickup_location} → {task.drop_location}</p>
          </>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <p className="text-xl font-semibold leading-tight">Giao hàng</p>
              <p className="font-mono text-sm font-semibold">{task.tracking_code}</p>
            </div>
            <p className="text-base font-medium">{task.recipient_name} · {task.packages} kiện</p>
            <p className="text-[15px] text-muted-foreground">{task.address}</p>
          </>
        )}
        <div className="flex items-center gap-2">{badge}<span className="text-sm text-muted-foreground">{task.kind === "TRUCKING" ? task.shipment_code : `Giao ${formatDate(task.planned_date)}`}</span></div>
      </Link>
      {task.kind === "LAST_MILE" && (
        <div className="grid grid-cols-2 gap-2 border-t p-2">
          <Button asChild variant="outline" className="h-12 text-base"><a href={`tel:${task.recipient_phone}`}><Phone />Gọi người nhận</a></Button>
          <Button asChild variant="outline" className="h-12 text-base"><a href={mapsLink(task.address)} target="_blank" rel="noreferrer"><MapPin />Chỉ đường</a></Button>
        </div>
      )}
    </div>
  );
}

export default function DriverHome() {
  const outbox = useOutbox();
  const tasks = useQuery({ queryKey: ["driver-tasks"], queryFn: () => apiFetch<DriverTask[]>("/api/driver/tasks"), refetchOnWindowFocus: true });
  return (
    <div className="space-y-4">
      <OutboxBar items={outbox.items} sending={outbox.sending} onFlush={outbox.flush} onDiscard={outbox.discard} />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Việc hôm nay</h1>
        <Button variant="outline" className="h-11" onClick={() => tasks.refetch()} disabled={tasks.isFetching}>
          <RefreshCw className={tasks.isFetching ? "animate-spin" : undefined} />
          Làm mới
        </Button>
      </div>
      {tasks.isPending && <p className="py-10 text-center text-muted-foreground">Đang tải…</p>}
      {tasks.error && (
        <div role="alert" className="space-y-3 rounded-lg border bg-card p-6 text-center">
          <p>{tasks.error.message}</p>
          <Button className="h-12" variant="outline" onClick={() => tasks.refetch()}>Thử lại</Button>
        </div>
      )}
      {tasks.data?.length === 0 && <p className="py-10 text-center text-muted-foreground">Hôm nay không có việc nào</p>}
      <div className="space-y-3">{tasks.data?.map((task) => <TaskCard key={`${task.kind}-${task.id}`} task={task} />)}</div>
    </div>
  );
}
