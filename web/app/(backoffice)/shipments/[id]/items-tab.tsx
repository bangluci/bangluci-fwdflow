"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus } from "lucide-react";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatNumber } from "@/lib/format";
import { fromMinorUnits, toMinorUnits } from "@/lib/money";
import type { ShipmentDetail, ShipmentItem } from "@/lib/shipment-types";
import { useMe } from "@/lib/use-me";
import { HsSuggest } from "./hs-suggest";

type Draft = {
  description: string; quantity: string; unit: string; packages: string; gross_weight_kg: string; value: string; currency: string;
  hs_code: string; hs_source: "manual" | "ai_accepted"; hs_log_id: number | null;
};
const EMPTY: Draft = { description: "", quantity: "", unit: "", packages: "", gross_weight_kg: "", value: "", currency: "USD", hs_code: "", hs_source: "manual", hs_log_id: null };
const helper = columnHelper<ShipmentItem>();

function fromItem(item: ShipmentItem): Draft {
  const currency = item.value_currency ?? "USD";
  const value = fromMinorUnits(item.value_amount, currency);
  return {
    description: item.description, quantity: String(item.quantity), unit: item.unit ?? "", packages: item.packages?.toString() ?? "",
    gross_weight_kg: item.gross_weight_kg == null ? "" : String(item.gross_weight_kg), value, currency, hs_code: item.hs_code ?? "",
    hs_source: item.hs_source === "ai_accepted" ? "ai_accepted" : "manual", hs_log_id: null,
  };
}

function ItemDialog({ shipmentId, item, onClose }: { shipmentId: number; item?: ShipmentItem; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => (item ? fromItem(item) : EMPTY));
  const [problem, setProblem] = useState("");
  const { data: me } = useMe();
  const canSuggest = !!me?.permissions.includes("hs.suggest");
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        description: draft.description.trim(), quantity: draft.quantity, unit: draft.unit.trim() || null,
        packages: draft.packages ? Number(draft.packages) : null, gross_weight_kg: draft.gross_weight_kg || null,
        value_amount: toMinorUnits(draft.value, draft.currency), value_currency: draft.value ? draft.currency : null,
        hs_code: draft.hs_code.trim() || null, hs_source: draft.hs_code.trim() ? draft.hs_source : null,
      };
      return item
        ? apiFetch(`/api/shipments/${shipmentId}/items/${item.id}`, { method: "PATCH", json: body })
        : apiFetch(`/api/shipments/${shipmentId}/items`, { method: "POST", json: body });
    },
    onSuccess: async () => {
      if (draft.hs_source === "ai_accepted" && draft.hs_log_id !== null) {
        // Chỉ để thống kê tỷ lệ chấp nhận; lỗi ở đây không được làm mất dòng hàng đã lưu.
        await apiFetch(`/api/hs/suggestions/${draft.hs_log_id}/choice`, { method: "POST", json: { code: draft.hs_code.trim() } }).catch(() => undefined);
      }
      await queryClient.invalidateQueries({ queryKey: ["shipment", shipmentId] });
      onClose();
    },
  });
  const set = (key: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement>) => setDraft((c) => ({ ...c, [key]: e.target.value }));
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.description.trim()) return setProblem("Nhập mô tả hàng");
    if (!(Number(draft.quantity) > 0)) return setProblem("Số lượng phải lớn hơn 0");
    if (draft.hs_code.trim() && !/^\d{8}$/.test(draft.hs_code.trim())) return setProblem("Mã HS gồm đúng 8 chữ số");
    setProblem("");
    save.mutate();
  }
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item ? `Sửa dòng ${item.line_no}` : "Thêm dòng hàng"}</DialogTitle>
          <DialogDescription>Trường có dấu * là bắt buộc.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          <Field label="Mô tả hàng" htmlFor="i-desc" required><Input id="i-desc" value={draft.description} onChange={set("description")} /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Số lượng" htmlFor="i-qty" required><Input id="i-qty" inputMode="decimal" value={draft.quantity} onChange={set("quantity")} /></Field>
            <Field label="Đơn vị" htmlFor="i-unit"><Input id="i-unit" value={draft.unit} onChange={set("unit")} /></Field>
            <Field label="Số kiện" htmlFor="i-pk"><Input id="i-pk" type="number" min={0} value={draft.packages} onChange={set("packages")} /></Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Khối lượng (kg)" htmlFor="i-kg"><Input id="i-kg" inputMode="decimal" value={draft.gross_weight_kg} onChange={set("gross_weight_kg")} /></Field>
            <Field label="Trị giá" htmlFor="i-val" hint={draft.currency === "VND" ? "Nhập số nguyên đồng" : "Tối đa 2 chữ số thập phân"}><Input id="i-val" inputMode="decimal" value={draft.value} onChange={set("value")} /></Field>
            <Field label="Tiền tệ" htmlFor="i-cur"><Input id="i-cur" maxLength={3} value={draft.currency} onChange={(e) => setDraft((c) => ({ ...c, currency: e.target.value.toUpperCase() }))} /></Field>
          </div>
          <Field label="Mã HS (8 số)" htmlFor="i-hs" hint={draft.hs_source === "ai_accepted" ? "Mã do AI gợi ý; sửa tay sẽ đổi nguồn về Nhập tay" : "Nhập tay hoặc dùng gợi ý AI"}>
            <Input id="i-hs" className="font-mono" value={draft.hs_code} onChange={(e) => setDraft((c) => ({ ...c, hs_code: e.target.value, hs_source: "manual", hs_log_id: null }))} />
          </Field>
          {canSuggest && <HsSuggest description={draft.description} onPick={(code, logId) => setDraft((c) => ({ ...c, hs_code: code, hs_source: "ai_accepted", hs_log_id: logId }))} />}
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

export function ItemsTab({ shipment, canWrite }: { shipment: ShipmentDetail; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<ShipmentItem | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (item: ShipmentItem) => apiFetch(`/api/shipments/${shipment.id}/items/${item.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] }),
  });
  const writable = canWrite && shipment.status !== "CANCELLED";
  const columns = [
    helper.accessor("line_no", { header: "STT", cell: (ctx) => <span className="tabular-nums">{ctx.getValue()}</span> }),
    helper.accessor("description", { header: "Mô tả" }),
    helper.accessor((row) => Number(row.quantity), { id: "quantity", header: "SL", cell: (ctx) => <span className="block text-right tabular-nums">{formatNumber(ctx.getValue())}</span> }),
    helper.accessor((row) => row.unit ?? "", { id: "unit", header: "ĐVT" }),
    helper.accessor((row) => row.packages ?? 0, { id: "packages", header: "Kiện", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.packages ?? ""}</span> }),
    helper.accessor((row) => Number(row.gross_weight_kg ?? 0), { id: "kg", header: "KL (kg)", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.gross_weight_kg == null ? "" : formatNumber(ctx.getValue())}</span> }),
    helper.accessor((row) => row.value_amount ?? 0, { id: "value", header: "Trị giá", cell: (ctx) => <span className="block text-right tabular-nums">{formatMoney(ctx.row.original.value_amount, ctx.row.original.value_currency)}</span> }),
    helper.accessor((row) => row.hs_code ?? "", { id: "hs", header: "Mã HS", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
    helper.accessor((row) => row.hs_source ?? "", { id: "hs_source", header: "Nguồn HS", cell: (ctx) => (ctx.getValue() ? <StatusBadge tone={ctx.getValue() === "ai_accepted" ? "info" : "neutral"}>{ctx.getValue() === "ai_accepted" ? "AI" : "Nhập tay"}</StatusBadge> : null) }),
    ...(writable
      ? [helper.display({
          id: "actions",
          header: () => <span className="sr-only">Thao tác</span>,
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
        <h2 className="text-sm font-semibold">Dòng hàng ({shipment.items.length})</h2>
        {writable && <Button size="sm" onClick={() => setEditing("new")}><Plus />Thêm dòng</Button>}
      </div>
      <ErrorBanner error={remove.error} />
      <DataTable columns={columns} data={shipment.items} getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có dòng hàng", hint: writable ? 'Bấm "Thêm dòng" hoặc duyệt kết quả AI đọc hoá đơn / packing list.' : undefined }, filtered: { title: "Không có kết quả" } }} />
      {editing && <ItemDialog shipmentId={shipment.id} item={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
