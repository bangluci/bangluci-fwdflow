"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { TruckingStatusBadge } from "@/components/shipment-status";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import { TRUCKING_KIND_LABEL } from "@/lib/shipment-labels";
import type { TruckingOrderRow } from "./week-calendar";

type OrderEvent = { id: number; kind: string; occurred_at: string; recorded_at: string; actor_id: number | null; reason: string | null; truck_id: number | null; driver_id: number | null; voided: boolean };
type OrderDetail = TruckingOrderRow & { events: OrderEvent[] };
type Mode = "assign" | "reassign" | "cancel" | { type: "void" | "retime"; event: OrderEvent } | null;

const EVENT_LABEL: Record<string, string> = { ASSIGNED: "Phân công", REASSIGNED: "Đổi xe / tài xế", STARTED: "Bắt đầu chạy", COMPLETED: "Hoàn tất", CANCELLED: "Huỷ lệnh", RETIME: "Chỉnh giờ", VOID: "Huỷ event" };
const MIN_REASON = 5;

function useTeam(truckerId: number) {
  const trucks = useQuery({ queryKey: ["catalog", "trucks", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/trucks?active=true") });
  const drivers = useQuery({ queryKey: ["catalog", "drivers", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/drivers?active=true") });
  return {
    trucks: (trucks.data ?? []).filter((t) => t.trucker_id === truckerId),
    drivers: (drivers.data ?? []).filter((d) => d.trucker_id === truckerId),
  };
}

function TeamForm({ order, withReason, onDone }: { order: TruckingOrderRow; withReason: boolean; onDone: () => void }) {
  const { trucks, drivers } = useTeam(order.trucker_id);
  const [truck, setTruck] = useState(order.truck_id ? String(order.truck_id) : "");
  const [driver, setDriver] = useState(order.driver_id ? String(order.driver_id) : "");
  const [reason, setReason] = useState("");
  const send = useMutation({
    mutationFn: () => apiFetch(`/api/trucking-orders/${order.id}/${withReason ? "reassign" : "assign"}`, { method: "POST", json: { truck_id: Number(truck), driver_id: Number(driver), ...(withReason ? { reason: reason.trim() } : {}) } }),
    onSuccess: onDone,
  });
  const ready = truck && driver && (!withReason || reason.trim().length >= MIN_REASON);
  return (
    <div className="space-y-3 rounded-md border bg-muted/40 p-3">
      <p className="text-[13px] font-medium">{withReason ? "Đổi xe / tài xế" : "Phân công xe và tài xế"} <span className="font-normal text-muted-foreground">(nhà xe {order.trucker_name})</span></p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Xe" htmlFor="t-truck">
          <Select value={truck} onValueChange={setTruck}>
            <SelectTrigger id="t-truck" className="w-full"><SelectValue placeholder="Chọn xe" /></SelectTrigger>
            <SelectContent>{trucks.map((t) => <SelectItem key={t.id} value={String(t.id)}>{String(t.plate_no)}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
        <Field label="Tài xế" htmlFor="t-driver">
          <Select value={driver} onValueChange={setDriver}>
            <SelectTrigger id="t-driver" className="w-full"><SelectValue placeholder="Chọn tài xế" /></SelectTrigger>
            <SelectContent>{drivers.map((d) => <SelectItem key={d.id} value={String(d.id)}>{String(d.full_name)}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
      </div>
      {withReason && <Field label="Lý do đổi" htmlFor="t-reason" required><Textarea id="t-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
      <ErrorBanner error={send.error} />
      <Button size="sm" disabled={!ready || send.isPending} onClick={() => send.mutate()}>{send.isPending ? "Đang lưu…" : withReason ? "Đổi" : "Phân công"}</Button>
    </div>
  );
}

function ReasonForm({ order, mode, onDone }: { order: TruckingOrderRow; mode: "cancel" | { type: "void" | "retime"; event: OrderEvent }; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [when, setWhen] = useState(typeof mode === "object" && mode.type === "retime" ? toLocalInput(mode.event.occurred_at) : "");
  const send = useMutation({
    mutationFn: () => {
      if (mode === "cancel") return apiFetch(`/api/trucking-orders/${order.id}/cancel`, { method: "POST", json: { reason: reason.trim() } });
      const base = `/api/trucking-orders/${order.id}/events/${mode.event.id}`;
      return mode.type === "void"
        ? apiFetch(`${base}/void`, { method: "POST", json: { reason: reason.trim() } })
        : apiFetch(`${base}/retime`, { method: "POST", json: { occurred_at: fromLocalInput(when), reason: reason.trim() } });
    },
    onSuccess: onDone,
  });
  const title = mode === "cancel" ? "Huỷ lệnh xe" : mode.type === "void" ? `Huỷ event "${EVENT_LABEL[mode.event.kind]}"` : `Chỉnh giờ "${EVENT_LABEL[mode.event.kind]}"`;
  const ready = reason.trim().length >= MIN_REASON && (typeof mode !== "object" || mode.type !== "retime" || when);
  return (
    <div className="space-y-3 rounded-md border bg-muted/40 p-3">
      <p className="text-[13px] font-medium">{title}</p>
      {typeof mode === "object" && mode.type === "retime" && <Field label="Giờ mới (giờ Việt Nam)" htmlFor="r-when" required><Input id="r-when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>}
      <Field label="Lý do" htmlFor="r-reason" required hint="Tối thiểu 5 ký tự; lưu vào nhật ký."><Textarea id="r-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <ErrorBanner error={send.error} />
      <Button size="sm" variant={mode === "cancel" || (typeof mode === "object" && mode.type === "void") ? "destructive" : "default"} disabled={!ready || send.isPending} onClick={() => send.mutate()}>Xác nhận</Button>
    </div>
  );
}

export function OrderDialog({ order, canWrite, canVoid, canRetime, onClose }: { order: TruckingOrderRow; canWrite: boolean; canVoid: boolean; canRetime: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>(null);
  const detail = useQuery({ queryKey: ["trucking-order", order.id], queryFn: () => apiFetch<OrderDetail>(`/api/trucking-orders/${order.id}`) });
  const current = detail.data ?? { ...order, events: [] };
  const done = () => {
    setMode(null);
    queryClient.invalidateQueries({ queryKey: ["trucking-order", order.id] });
    queryClient.invalidateQueries({ queryKey: ["trucking-orders"] });
    queryClient.invalidateQueries({ queryKey: ["shipment"] });
  };
  const effective = current.events.filter((e) => !e.voided && e.kind !== "RETIME" && e.kind !== "VOID");
  const latest = effective[effective.length - 1];
  const open = !["COMPLETED", "CANCELLED"].includes(current.status);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">{TRUCKING_KIND_LABEL[current.kind]} · <span className="font-mono">{current.container_no}</span><TruckingStatusBadge status={current.status} /></DialogTitle>
          <DialogDescription>Lô <Link className="font-mono font-semibold text-primary hover:underline" href={`/shipments/${current.shipment_id}`}>{current.shipment_code}</Link> · dự kiến {formatDateTime(current.planned_at)}</DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
          <div><dt className="text-xs text-muted-foreground">Nhà xe</dt><dd>{current.trucker_name}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Xe / tài xế</dt><dd>{current.plate_no ? `${current.plate_no} · ${current.driver_name}` : "Chưa gán"}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Điểm lấy</dt><dd>{current.pickup_location}</dd></div>
          <div><dt className="text-xs text-muted-foreground">Điểm trả</dt><dd>{current.drop_location}</dd></div>
        </dl>
        {canWrite && open && !mode && (
          <div className="flex flex-wrap gap-2">
            {current.status === "PLANNED" && <Button size="sm" onClick={() => setMode("assign")}>Phân công</Button>}
            {(current.status === "ASSIGNED" || current.status === "STARTED") && <Button size="sm" variant="outline" onClick={() => setMode("reassign")}>Đổi xe / tài xế</Button>}
            {(current.status === "PLANNED" || current.status === "ASSIGNED") && <Button size="sm" variant="outline" className="text-destructive" onClick={() => setMode("cancel")}>Huỷ lệnh</Button>}
          </div>
        )}
        {mode === "assign" && <TeamForm order={current} withReason={false} onDone={done} />}
        {mode === "reassign" && <TeamForm order={current} withReason onDone={done} />}
        {(mode === "cancel" || (mode && typeof mode === "object")) && <ReasonForm order={current} mode={mode as "cancel"} onDone={done} />}
        {mode && <Button variant="ghost" size="sm" onClick={() => setMode(null)}>Đóng biểu mẫu</Button>}
        <div>
          <h3 className="mb-2 text-[13px] font-semibold">Diễn biến</h3>
          <ol className="space-y-2 text-[13px]">
            {current.events.map((e) => {
              const adjustable = !e.voided && (e.kind === "STARTED" || e.kind === "COMPLETED");
              return (
                <li key={e.id} className="flex items-start justify-between gap-2">
                  <div className={e.voided ? "text-muted-foreground line-through" : undefined}>
                    <p>{EVENT_LABEL[e.kind] ?? e.kind} · {formatDateTime(e.kind === "RETIME" ? e.recorded_at : e.occurred_at)}</p>
                    {(e.reason || e.actor_id == null) && <p className="text-xs text-muted-foreground">{e.actor_id == null ? "hệ thống" : ""}{e.reason ? ` ${e.reason}` : ""}</p>}
                  </div>
                  {adjustable && !mode && (
                    <div className="flex shrink-0 gap-1">
                      {canRetime && <Button size="xs" variant="outline" onClick={() => setMode({ type: "retime", event: e })}>Chỉnh giờ</Button>}
                      {canVoid && latest?.id === e.id && <Button size="xs" variant="outline" onClick={() => setMode({ type: "void", event: e })}>Huỷ event</Button>}
                    </div>
                  )}
                </li>
              );
            })}
            {current.events.length === 0 && <li className="text-muted-foreground">Chưa có diễn biến</li>}
          </ol>
        </div>
      </DialogContent>
    </Dialog>
  );
}
