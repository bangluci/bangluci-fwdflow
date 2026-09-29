"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus } from "lucide-react";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import type { ContainerDetail, ShipmentDetail } from "@/lib/shipment-types";

const TYPES = ["20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH"];
const MILESTONES = [
  { kind: "DISCHARGED", label: "Dỡ khỏi tàu" },
  { kind: "GATE_OUT_FULL", label: "Lấy cont ra khỏi cảng" },
  { kind: "EMPTY_RETURNED", label: "Trả vỏ rỗng" },
];
const DISCHARGE_STATUSES = ["ARRIVED", "CUSTOMS_CLEARING", "CLEARED"];
const helper = columnHelper<ContainerDetail>();

function ContainerDialog({ shipmentId, item, onClose }: { shipmentId: number; item?: ContainerDetail; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ container_no: item?.container_no ?? "", container_type: item?.container_type ?? "40HC", seal_no: item?.seal_no ?? "", gross_weight_kg: item?.gross_weight_kg?.toString() ?? "" });
  const save = useMutation({
    mutationFn: () => {
      const body = { container_no: form.container_no.trim(), container_type: form.container_type, seal_no: form.seal_no.trim() || null, gross_weight_kg: form.gross_weight_kg || null };
      return item
        ? apiFetch(`/api/shipments/${shipmentId}/containers/${item.id}`, { method: "PATCH", json: body })
        : apiFetch(`/api/shipments/${shipmentId}/containers`, { method: "POST", json: body });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipment", shipmentId] });
      onClose();
    },
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((c) => ({ ...c, [key]: e.target.value }));
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{item ? "Sửa container" : "Thêm container"}</DialogTitle>
          <DialogDescription>Số container theo ISO 6346 (4 chữ cái + 7 số, số cuối là số kiểm tra).</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} noValidate className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Số container" htmlFor="c-no" required><Input id="c-no" className="font-mono" placeholder="CSQU3054383" value={form.container_no} onChange={set("container_no")} /></Field>
            <Field label="Loại" htmlFor="c-type">
              <Select value={form.container_type} onValueChange={(v) => setForm((c) => ({ ...c, container_type: v }))}>
                <SelectTrigger id="c-type" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Số seal" htmlFor="c-seal"><Input id="c-seal" className="font-mono" value={form.seal_no} onChange={set("seal_no")} /></Field>
            <Field label="Khối lượng (kg)" htmlFor="c-kg"><Input id="c-kg" inputMode="decimal" value={form.gross_weight_kg} onChange={set("gross_weight_kg")} /></Field>
          </div>
          <ErrorBanner error={save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Huỷ</Button>
            <Button type="submit" disabled={save.isPending}>{save.isPending ? "Đang lưu…" : "Lưu"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MilestoneDialog({ container, mode, onClose }: { container: ContainerDetail; mode: "discharge" | "retime"; onClose: () => void }) {
  const queryClient = useQueryClient();
  const present = MILESTONES.filter((m) => container.milestones[m.kind]);
  const [kind, setKind] = useState(present[0]?.kind ?? "DISCHARGED");
  const [when, setWhen] = useState(mode === "retime" ? toLocalInput(container.milestones[kind]?.occurred_at) : "");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => mode === "discharge"
      ? apiFetch(`/api/containers/${container.id}/events`, { method: "POST", json: { kind: "DISCHARGED", occurred_at: fromLocalInput(when) } })
      : apiFetch(`/api/containers/${container.id}/events`, { method: "POST", json: { kind: "RETIME", adjusts_event_id: container.milestones[kind].event_id, occurred_at: fromLocalInput(when), reason: reason.trim() } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipment"] });
      queryClient.invalidateQueries({ queryKey: ["shipment-side"] });
      onClose();
    },
  });
  const ready = when && (mode === "discharge" || reason.trim().length >= 3);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{mode === "discharge" ? "Nhập giờ dỡ khỏi tàu" : "Chỉnh giờ mốc container"}</DialogTitle>
          <DialogDescription>{container.container_no} · giờ Việt Nam</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {mode === "retime" && (
            <Field label="Mốc cần chỉnh" htmlFor="m-kind">
              <Select value={kind} onValueChange={(v) => { setKind(v); setWhen(toLocalInput(container.milestones[v]?.occurred_at)); }}>
                <SelectTrigger id="m-kind" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{present.map((m) => <SelectItem key={m.kind} value={m.kind}>{m.label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          )}
          <Field label={mode === "discharge" ? "Dỡ lúc" : "Giờ mới"} htmlFor="m-when" required><Input id="m-when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
          {mode === "retime" && (
            <Field label="Lý do" htmlFor="m-reason" required hint="Ví dụ: theo phiếu EIR. Giờ cũ vẫn được lưu trong timeline.">
              <Textarea id="m-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          )}
          <ErrorBanner error={save.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!ready || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Đang lưu…" : "Lưu"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ContainersTab({ shipment, canWrite, canMilestone }: { shipment: ShipmentDetail; canWrite: boolean; canMilestone: boolean }) {
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<{ kind: "edit"; item?: ContainerDetail } | { kind: "discharge" | "retime"; item: ContainerDetail } | null>(null);
  const remove = useMutation({
    mutationFn: (item: ContainerDetail) => apiFetch(`/api/shipments/${shipment.id}/containers/${item.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] }),
  });
  const open = shipment.status !== "CANCELLED";
  const canDischarge = DISCHARGE_STATUSES.includes(shipment.status);
  const milestone = (kind: string) => (row: ContainerDetail) => row.milestones[kind]?.occurred_at ?? "";
  const columns = [
    helper.accessor("container_no", { header: "Số container", cell: (ctx) => <span className="font-mono text-xs font-semibold">{ctx.getValue()}</span> }),
    helper.accessor("container_type", { header: "Loại" }),
    helper.accessor((row) => row.seal_no ?? "", { id: "seal", header: "Seal", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
    helper.accessor((row) => row.gross_weight_kg ?? "", { id: "kg", header: "KL (kg)", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.getValue()}</span> }),
    ...MILESTONES.map((m) => helper.accessor(milestone(m.kind), { id: m.kind, header: m.label, cell: (ctx) => ctx.getValue() ? formatDateTime(ctx.getValue()) : <span className="text-muted-foreground">Chưa có</span> })),
    ...(open && (canWrite || canMilestone)
      ? [helper.display({
          id: "actions", header: () => <span className="sr-only">Thao tác</span>,
          cell: (ctx) => {
            const row = ctx.row.original;
            return (
              <div className="flex justify-end">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal /></Button></DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {canMilestone && canDischarge && !row.milestones.DISCHARGED && <DropdownMenuItem onSelect={() => setDialog({ kind: "discharge", item: row })}>Nhập giờ dỡ tàu</DropdownMenuItem>}
                    {canMilestone && Object.keys(row.milestones).length > 0 && <DropdownMenuItem onSelect={() => setDialog({ kind: "retime", item: row })}>Chỉnh giờ mốc</DropdownMenuItem>}
                    {canWrite && <DropdownMenuItem onSelect={() => setDialog({ kind: "edit", item: row })}>Sửa thông tin</DropdownMenuItem>}
                    {canWrite && <DropdownMenuItem variant="destructive" onSelect={() => remove.mutate(row)}>Xoá</DropdownMenuItem>}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            );
          },
        })]
      : []),
  ];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Container ({shipment.containers.length})</h2>
        {canWrite && open && <Button size="sm" onClick={() => setDialog({ kind: "edit" })}><Plus />Thêm container</Button>}
      </div>
      <p className="text-[13px] text-muted-foreground">Mốc lấy cont và trả vỏ do tài xế ghi khi thao tác trên điện thoại; ở đây chỉ chỉnh giờ khi ghi sai.</p>
      <ErrorBanner error={remove.error} />
      <DataTable columns={columns} data={shipment.containers} getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có container" }, filtered: { title: "Không có kết quả" } }} />
      {dialog?.kind === "edit" && <ContainerDialog shipmentId={shipment.id} item={dialog.item} onClose={() => setDialog(null)} />}
      {(dialog?.kind === "discharge" || dialog?.kind === "retime") && <MilestoneDialog container={dialog.item} mode={dialog.kind} onClose={() => setDialog(null)} />}
    </div>
  );
}
