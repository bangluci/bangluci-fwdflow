"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, MapPin } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { LastMileStatusBadge } from "@/components/shipment-status";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { formatDate, formatDateTime, todayVn } from "@/lib/format";
import { formatCode, type LastMileDetail, type LastMileOrderRow } from "./last-mile-types";

type Mode = "assign" | "reassign" | "cancel" | "return";
const MIN_REASON = 5;
const TITLE: Record<Mode, string> = { assign: "Phân công tài xế", reassign: "Đổi tài xế", cancel: "Huỷ đơn giao", return: "Nhận lại hàng về kho" };
const EVENT_LABEL: Record<string, string> = { CREATED: "Tạo đơn", ASSIGNED: "Phân công", REASSIGNED: "Đổi tài xế", PICKED_UP: "Đã lấy hàng", DELIVERED: "Đã giao", FAILED: "Giao thất bại", RETURNED: "Hoàn về kho", CANCELLED: "Huỷ đơn", VOID: "Huỷ event", RETIME: "Chỉnh giờ" };
const VOIDABLE = ["PICKED_UP", "DELIVERED", "FAILED"];

function ActionDialog({ order, mode, onClose }: { order: LastMileOrderRow; mode: Mode; onClose: () => void }) {
  const queryClient = useQueryClient();
  const drivers = useQuery({ queryKey: ["catalog", "drivers", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/drivers?active=true") });
  const [driver, setDriver] = useState(order.driver_id ? String(order.driver_id) : "");
  const [date, setDate] = useState(order.planned_date >= todayVn() ? order.planned_date : todayVn());
  const [reason, setReason] = useState("");
  const needsDriver = mode === "assign" || mode === "reassign";
  const needsReason = mode !== "assign";
  const send = useMutation({
    mutationFn: () => apiFetch(`/api/last-mile-orders/${order.id}/${mode}`, {
      method: "POST",
      json: {
        ...(needsDriver ? { driver_id: Number(driver), planned_date: date } : {}),
        ...(needsReason ? { reason: reason.trim() } : {}),
      },
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["last-mile"] });
      queryClient.invalidateQueries({ queryKey: ["shipment"] });
      onClose();
    },
  });
  const ready = (!needsDriver || (driver && date)) && (!needsReason || reason.trim().length >= MIN_REASON);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{TITLE[mode]}</DialogTitle>
          <DialogDescription><span className="font-mono">{formatCode(order.tracking_code)}</span> · {order.recipient_name} · {order.packages} kiện</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {needsDriver && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Tài xế" htmlFor="a-driver" required>
                <Select value={driver} onValueChange={setDriver}>
                  <SelectTrigger id="a-driver" className="w-full"><SelectValue placeholder="Chọn tài xế" /></SelectTrigger>
                  <SelectContent>{(drivers.data ?? []).map((d) => <SelectItem key={d.id} value={String(d.id)}>{String(d.full_name)}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="Ngày giao" htmlFor="a-date" required><Input id="a-date" type="date" min={todayVn()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            </div>
          )}
          {needsReason && <Field label="Lý do" htmlFor="a-reason" required hint="Tối thiểu 5 ký tự; lưu vào nhật ký."><Textarea id="a-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
          <ErrorBanner error={send.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Đóng</Button>
          <Button variant={mode === "cancel" ? "destructive" : "default"} disabled={!ready || send.isPending} onClick={() => send.mutate()}>Xác nhận</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Timeline({ orderId, canVoid }: { orderId: number; canVoid: boolean }) {
  const queryClient = useQueryClient();
  const [voiding, setVoiding] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const detail = useQuery({ queryKey: ["last-mile", "order", orderId], queryFn: () => apiFetch<LastMileDetail>(`/api/last-mile-orders/${orderId}`) });
  const void_ = useMutation({
    mutationFn: (eventId: number) => apiFetch(`/api/last-mile-orders/${orderId}/events/${eventId}/void`, { method: "POST", json: { reason: reason.trim() } }),
    onSuccess: async () => { setVoiding(null); setReason(""); await queryClient.invalidateQueries({ queryKey: ["last-mile"] }); queryClient.invalidateQueries({ queryKey: ["shipment"] }); },
  });
  const events = detail.data?.events ?? [];
  const live = events.filter((e) => !e.voided && e.kind !== "VOID" && e.kind !== "RETIME");
  const latest = live[live.length - 1];
  return (
    <ol className="space-y-2 text-[13px]">
      {events.map((e) => (
        <li key={e.id} className="flex flex-wrap items-start justify-between gap-2">
          <div className={e.voided ? "text-muted-foreground line-through" : undefined}>
            <p>{EVENT_LABEL[e.kind] ?? e.kind} · {formatDateTime(e.occurred_at)}</p>
            <p className="text-xs text-muted-foreground">
              {e.actor_name ?? (e.actor_id == null ? "hệ thống / tài xế" : "")}
              {e.reason ? ` · ${e.reason}` : ""}
              {e.lat && e.lng ? <span className="ml-2 inline-flex items-center gap-0.5"><MapPin className="size-3" aria-hidden />{Number(e.lat).toFixed(4)}, {Number(e.lng).toFixed(4)}</span> : null}
              {e.has_photo ? " · có ảnh" : ""}
            </p>
          </div>
          {canVoid && latest?.id === e.id && VOIDABLE.includes(e.kind) && voiding !== e.id && (
            <Button size="xs" variant="outline" onClick={() => setVoiding(e.id)}>Huỷ event</Button>
          )}
          {voiding === e.id && (
            <div className="w-full space-y-2 rounded-md border bg-muted/40 p-2.5">
              <Textarea aria-label="Lý do huỷ event" rows={2} placeholder="Lý do huỷ event (tối thiểu 5 ký tự)" value={reason} onChange={(ev) => setReason(ev.target.value)} />
              <ErrorBanner error={void_.error} />
              <div className="flex gap-2">
                <Button size="xs" variant="destructive" disabled={reason.trim().length < MIN_REASON || void_.isPending} onClick={() => void_.mutate(e.id)}>Xác nhận huỷ</Button>
                <Button size="xs" variant="ghost" onClick={() => setVoiding(null)}>Đóng</Button>
              </div>
            </div>
          )}
        </li>
      ))}
      {detail.isPending && <li className="text-muted-foreground">Đang tải…</li>}
    </ol>
  );
}

export function OrdersTable({ orders, loading, canManage, canVoid, showShipment }: { orders: LastMileOrderRow[]; loading: boolean; canManage: boolean; canVoid: boolean; showShipment: boolean }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [action, setAction] = useState<{ order: LastMileOrderRow; mode: Mode } | null>(null);
  const toggle = (id: number) => setOpen((c) => { const next = new Set(c); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const buttons = (o: LastMileOrderRow): [Mode, string][] =>
    !canManage ? [] : o.status === "CREATED" ? [["assign", "Phân công"], ["cancel", "Huỷ"]]
      : o.status === "ASSIGNED" ? [["reassign", "Đổi tài xế"], ["cancel", "Huỷ"]]
        : o.status === "FAILED" ? [["assign", "Giao lại"], ["return", "Nhận lại về kho"]] : [];
  const heads = ["", "Mã vận đơn", ...(showShipment ? ["Lô"] : []), "Người nhận", "SĐT", "Kiện", "Tài xế", "Ngày giao", "Trạng thái", ""];
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table className="text-[13px]">
        <TableHeader className="bg-muted/90">
          <TableRow className="h-9">{heads.map((h, i) => <TableHead key={i} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{h}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((o) => {
            const expanded = open.has(o.id);
            return (
              <Fragment key={o.id}>
                <TableRow className="h-10">
                  <TableCell className="w-8 py-0"><Button variant="ghost" size="icon-sm" aria-label={expanded ? "Thu gọn" : "Xem diễn biến"} aria-expanded={expanded} onClick={() => toggle(o.id)}>{expanded ? <ChevronDown /> : <ChevronRight />}</Button></TableCell>
                  <TableCell className="font-mono text-xs font-semibold">{formatCode(o.tracking_code)}</TableCell>
                  {showShipment && <TableCell><Link className="font-mono text-xs font-semibold text-primary hover:underline" href={`/shipments/${o.shipment_id}`}>{o.shipment_code}</Link></TableCell>}
                  <TableCell>{o.recipient_name}<p className="max-w-56 truncate text-xs text-muted-foreground" title={o.address}>{o.address}</p></TableCell>
                  <TableCell className="font-mono text-xs">{o.recipient_phone}</TableCell>
                  <TableCell className="tabular-nums">{o.packages}</TableCell>
                  <TableCell>{o.driver_name ?? <span className="text-muted-foreground">Chưa gán</span>}</TableCell>
                  <TableCell>{formatDate(o.planned_date)}</TableCell>
                  <TableCell><LastMileStatusBadge status={o.status} /></TableCell>
                  <TableCell className="text-right"><div className="flex justify-end gap-1">{buttons(o).map(([mode, label]) => <Button key={mode} size="xs" variant="outline" onClick={() => setAction({ order: o, mode })}>{label}</Button>)}</div></TableCell>
                </TableRow>
                {expanded && (
                  <TableRow className="bg-muted/30 hover:bg-muted/30">
                    <TableCell />
                    <TableCell colSpan={heads.length - 1} className="py-3"><Timeline orderId={o.id} canVoid={canVoid} /></TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
      {loading && <p className="px-6 py-10 text-center text-sm text-muted-foreground">Đang tải…</p>}
      {!loading && orders.length === 0 && <p className="px-6 py-10 text-center text-sm text-muted-foreground">Chưa có đơn giao nào khớp bộ lọc.</p>}
      {action && <ActionDialog order={action.order} mode={action.mode} onClose={() => setAction(null)} />}
    </div>
  );
}
