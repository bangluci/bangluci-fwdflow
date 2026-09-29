"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Flag, Lock, MoreHorizontal, Plus } from "lucide-react";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
import { LANE_LABEL } from "@/lib/shipment-labels";
import type { Declaration, ShipmentDetail } from "@/lib/shipment-types";
import { cn } from "@/lib/utils";

const LOCKED_STATUSES = ["CLEARED", "AT_WAREHOUSE", "DELIVERING", "COMPLETED"];
const LANE_TEXT: Record<string, string> = { GREEN: "text-success-ink", YELLOW: "text-warning-ink", RED: "text-danger-ink" };
const NONE = "__none__";
const helper = columnHelper<Declaration>();

// Luồng hải quan (xanh / vàng / đỏ) là mức kiểm tra, không phải mức khẩn: vẽ bằng cờ + chữ, tách hẳn hệ free time.
function LaneFlag({ lane }: { lane: Declaration["lane"] }) {
  if (!lane) return <span className="text-muted-foreground">Chưa phân luồng</span>;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", LANE_TEXT[lane])}>
      <Flag aria-hidden className="size-3.5 fill-current" />
      {LANE_LABEL[lane]}
    </span>
  );
}

function DeclarationDialog({ shipmentId, item, onClose }: { shipmentId: number; item?: Declaration; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    declaration_no: item?.declaration_no ?? "", type_code: item?.type_code ?? "", registered_at: toLocalInput(item?.registered_at),
    lane: item?.lane ?? "", cleared_at: toLocalInput(item?.cleared_at),
  });
  const [problem, setProblem] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const body = {
        declaration_no: form.declaration_no.trim(), type_code: form.type_code.trim().toUpperCase(),
        registered_at: fromLocalInput(form.registered_at), lane: form.lane || null,
        cleared_at: form.cleared_at ? fromLocalInput(form.cleared_at) : null,
      };
      return item
        ? apiFetch(`/api/shipments/${shipmentId}/customs-declarations/${item.id}`, { method: "PATCH", json: body })
        : apiFetch(`/api/shipments/${shipmentId}/customs-declarations`, { method: "POST", json: body });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipment", shipmentId] });
      onClose();
    },
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((c) => ({ ...c, [key]: e.target.value }));
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!/^\d{12}$/.test(form.declaration_no.trim())) return setProblem("Số tờ khai gồm đúng 12 chữ số");
    if (!/^[A-Z]\d{2}$/.test(form.type_code.trim().toUpperCase())) return setProblem("Loại hình gồm 1 chữ cái và 2 chữ số, ví dụ A11");
    if (!form.registered_at) return setProblem("Nhập ngày giờ đăng ký");
    if (form.cleared_at && form.cleared_at < form.registered_at) return setProblem("Ngày thông quan không được trước ngày đăng ký");
    setProblem("");
    save.mutate();
  }
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{item ? "Sửa tờ khai" : "Thêm tờ khai"}</DialogTitle>
          <DialogDescription>Ngày giờ hiểu theo giờ Việt Nam.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Số tờ khai" htmlFor="d-no" required><Input id="d-no" inputMode="numeric" className="font-mono" value={form.declaration_no} onChange={set("declaration_no")} /></Field>
            <Field label="Loại hình" htmlFor="d-type" required><Input id="d-type" className="font-mono" placeholder="A11" value={form.type_code} onChange={set("type_code")} /></Field>
          </div>
          <Field label="Đăng ký lúc" htmlFor="d-reg" required><Input id="d-reg" type="datetime-local" value={form.registered_at} onChange={set("registered_at")} /></Field>
          <Field label="Luồng" htmlFor="d-lane">
            <Select value={form.lane || NONE} onValueChange={(v) => setForm((c) => ({ ...c, lane: v === NONE ? "" : v }))}>
              <SelectTrigger id="d-lane" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Chưa phân luồng</SelectItem>
                {Object.entries(LANE_LABEL).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Thông quan lúc" htmlFor="d-clr"><Input id="d-clr" type="datetime-local" value={form.cleared_at} onChange={set("cleared_at")} /></Field>
          <ErrorBanner error={problem || save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Huỷ</Button>
            <Button type="submit" disabled={save.isPending}>{save.isPending ? "Đang lưu…" : "Lưu"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function DeclarationsTab({ shipment, canWrite }: { shipment: ShipmentDetail; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Declaration | "new" | null>(null);
  const locked = LOCKED_STATUSES.includes(shipment.status);
  const writable = canWrite && !locked && shipment.status !== "CANCELLED";
  const remove = useMutation({
    mutationFn: (item: Declaration) => apiFetch(`/api/shipments/${shipment.id}/customs-declarations/${item.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] }),
  });
  const columns = [
    helper.accessor("declaration_no", { header: "Số tờ khai", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
    helper.accessor("type_code", { header: "Loại hình", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
    helper.accessor((row) => formatDateTime(row.registered_at), { id: "registered_at", header: "Ngày đăng ký" }),
    helper.accessor((row) => row.lane ?? "", { id: "lane", header: "Luồng", cell: (ctx) => <LaneFlag lane={ctx.row.original.lane} /> }),
    helper.accessor((row) => formatDateTime(row.cleared_at), { id: "cleared_at", header: "Ngày thông quan", cell: (ctx) => ctx.getValue() || <span className="text-muted-foreground">Chưa thông quan</span> }),
    ...(writable
      ? [helper.display({
          id: "actions", header: () => <span className="sr-only">Thao tác</span>,
          cell: (ctx) => (
            <div className="flex justify-end">
              <DropdownMenu>
                <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal /></Button></DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setEditing(ctx.row.original)}>Sửa</DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onSelect={() => remove.mutate(ctx.row.original)}>Xoá</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ),
        })]
      : []),
  ];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Tờ khai hải quan ({shipment.declarations.length})</h2>
        {writable && <Button size="sm" onClick={() => setEditing("new")}><Plus />Thêm tờ khai</Button>}
      </div>
      {locked && <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><Lock className="size-3.5" aria-hidden />Tờ khai đã khoá sau thông quan.</p>}
      <ErrorBanner error={remove.error} />
      <DataTable columns={columns} data={shipment.declarations} getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có tờ khai", hint: "Cần ít nhất một tờ khai đã có ngày thông quan trước khi chuyển sang Đã thông quan." }, filtered: { title: "Không có kết quả" } }} />
      {editing && <DeclarationDialog shipmentId={shipment.id} item={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
