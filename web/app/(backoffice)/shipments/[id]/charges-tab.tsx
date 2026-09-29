"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus } from "lucide-react";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { StatusBadge } from "@/components/status-badge";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { formatDate, formatMoney, formatVnd, todayVn } from "@/lib/format";
import { fromMinorUnits, toMinorUnits } from "@/lib/money";
import { cn } from "@/lib/utils";

type Charge = { id: number; direction: "COST" | "REVENUE"; category: string; amount: number; currency: "VND" | "USD"; fx_rate: string; amount_vnd: number; charge_date: string; note: string | null };
type ChargeList = { items: Charge[]; profit: { revenue_vnd: number; cost_vnd: number; profit_vnd: number } };

const CATEGORY_LABEL: Record<string, string> = {
  OCEAN_FREIGHT: "Cước biển", THC: "THC", LOCAL_CHARGE: "Local charge", TRUCKING: "Vận tải nội địa", DEM: "DEM", DET: "DET",
  DND_COMBINED: "DEM/DET gộp", CUSTOMS: "Hải quan", LAST_MILE: "Giao nội địa", OTHER: "Khác",
};
const helper = columnHelper<Charge>();

function ChargeDialog({ shipmentId, item, onClose }: { shipmentId: number; item?: Charge; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    direction: item?.direction ?? "REVENUE", category: item?.category ?? "OCEAN_FREIGHT", currency: item?.currency ?? "VND",
    amount: item ? fromMinorUnits(item.amount, item.currency) : "", fx_rate: item && item.currency === "USD" ? String(Number(item.fx_rate)) : "",
    charge_date: item?.charge_date ?? todayVn(), note: item?.note ?? "",
  });
  const [problem, setProblem] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        direction: form.direction, category: form.category, currency: form.currency, amount: toMinorUnits(form.amount, form.currency),
        charge_date: form.charge_date, note: form.note.trim() || null,
      };
      if (form.currency === "USD") body.fx_rate = form.fx_rate;
      return item
        ? apiFetch(`/api/shipments/${shipmentId}/charges/${item.id}`, { method: "PATCH", json: body })
        : apiFetch(`/api/shipments/${shipmentId}/charges`, { method: "POST", json: body });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["charges", shipmentId] });
      onClose();
    },
  });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    const minor = toMinorUnits(form.amount, form.currency);
    if (!minor || minor <= 0 || Number.isNaN(minor)) return setProblem("Nhập số tiền lớn hơn 0");
    if (form.currency === "USD" && !(Number(form.fx_rate.replace(",", ".")) > 0)) return setProblem("Cần tỷ giá cho khoản USD");
    setProblem("");
    save.mutate();
  }
  const set = (key: keyof typeof form) => (value: string) => setForm((c) => ({ ...c, [key]: value }));
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{item ? "Sửa khoản thu chi" : "Thêm khoản thu chi"}</DialogTitle>
          <DialogDescription>VND nhập số nguyên đồng; USD tối đa 2 chữ số thập phân. Lợi nhuận của lô tính lại tự động.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Chiều" htmlFor="c-dir">
              <Select value={form.direction} onValueChange={set("direction")}>
                <SelectTrigger id="c-dir" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="REVENUE">Doanh thu</SelectItem><SelectItem value="COST">Chi phí</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Hạng mục" htmlFor="c-cat">
              <Select value={form.category} onValueChange={set("category")}>
                <SelectTrigger id="c-cat" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(CATEGORY_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Tiền tệ" htmlFor="c-cur">
              <Select value={form.currency} onValueChange={set("currency")}>
                <SelectTrigger id="c-cur" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="VND">VND</SelectItem><SelectItem value="USD">USD</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Số tiền" htmlFor="c-amt" required className="col-span-2"><Input id="c-amt" inputMode="decimal" value={form.amount} onChange={(e) => set("amount")(e.target.value)} /></Field>
          </div>
          {form.currency === "USD" && <Field label="Tỷ giá USD/VND" htmlFor="c-fx" required><Input id="c-fx" inputMode="decimal" placeholder="25400" value={form.fx_rate} onChange={(e) => set("fx_rate")(e.target.value)} /></Field>}
          <Field label="Ngày" htmlFor="c-date"><Input id="c-date" type="date" value={form.charge_date} onChange={(e) => set("charge_date")(e.target.value)} /></Field>
          <Field label="Ghi chú" htmlFor="c-note"><Input id="c-note" value={form.note} onChange={(e) => set("note")(e.target.value)} /></Field>
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

function Total({ label, value, negative }: { label: string; value: number; negative?: boolean }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-lg font-semibold tabular-nums", negative && "text-danger-ink")}>{formatVnd(value)}</p>
    </div>
  );
}

export function ChargesTab({ shipmentId }: { shipmentId: number }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Charge | "new" | null>(null);
  const [deleting, setDeleting] = useState<Charge | null>(null);
  const list = useQuery({ queryKey: ["charges", shipmentId], queryFn: () => apiFetch<ChargeList>(`/api/shipments/${shipmentId}/charges`) });
  const remove = useMutation({
    mutationFn: (item: Charge) => apiFetch(`/api/shipments/${shipmentId}/charges/${item.id}`, { method: "DELETE" }),
    onSuccess: async () => { setDeleting(null); await queryClient.invalidateQueries({ queryKey: ["charges", shipmentId] }); },
  });
  const columns = [
    helper.accessor((row) => formatDate(row.charge_date), { id: "date", header: "Ngày" }),
    helper.accessor("direction", { header: "Chiều", cell: (ctx) => <StatusBadge tone={ctx.getValue() === "REVENUE" ? "success" : "neutral"}>{ctx.getValue() === "REVENUE" ? "Doanh thu" : "Chi phí"}</StatusBadge> }),
    helper.accessor((row) => CATEGORY_LABEL[row.category] ?? row.category, { id: "category", header: "Hạng mục" }),
    helper.accessor("amount", { header: "Số tiền gốc", cell: (ctx) => <span className="block text-right tabular-nums">{formatMoney(ctx.getValue(), ctx.row.original.currency)}</span> }),
    helper.accessor((row) => (row.currency === "USD" ? Number(row.fx_rate) : 0), { id: "fx", header: "Tỷ giá", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.currency === "USD" ? Number(ctx.row.original.fx_rate).toLocaleString("vi-VN") : "—"}</span> }),
    helper.accessor("amount_vnd", { header: "Quy đổi VND", cell: (ctx) => <span className="block text-right font-medium tabular-nums">{formatVnd(ctx.getValue())}</span> }),
    helper.accessor((row) => row.note ?? "", { id: "note", header: "Ghi chú" }),
    helper.display({
      id: "actions", header: () => <span className="sr-only">Thao tác</span>,
      cell: (ctx) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setEditing(ctx.row.original)}>Sửa</DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => { remove.reset(); setDeleting(ctx.row.original); }}>Xoá</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    }),
  ];
  const profit = list.data?.profit;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Total label="Doanh thu" value={profit?.revenue_vnd ?? 0} />
        <Total label="Chi phí" value={profit?.cost_vnd ?? 0} />
        <Total label="Lợi nhuận" value={profit?.profit_vnd ?? 0} negative={(profit?.profit_vnd ?? 0) < 0} />
      </div>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Thu chi của lô</h2>
        <Button size="sm" onClick={() => setEditing("new")}><Plus />Thêm khoản</Button>
      </div>
      <DataTable columns={columns} data={list.data?.items ?? []} loading={list.isPending} error={list.error} onRetry={() => list.refetch()} getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có khoản thu chi", hint: 'Bấm "Thêm khoản" để nhập doanh thu hoặc chi phí đầu tiên.' }, filtered: { title: "Không có kết quả" } }} />
      {editing && <ChargeDialog shipmentId={shipmentId} item={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} />}
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá khoản này?</AlertDialogTitle>
            <AlertDialogDescription>{deleting && `${CATEGORY_LABEL[deleting.category]} · ${formatVnd(deleting.amount_vnd)}. Việc xoá được ghi vào nhật ký.`}</AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorBanner error={remove.error} />
          <AlertDialogFooter>
            <AlertDialogCancel>Giữ lại</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={remove.isPending} onClick={(e) => { e.preventDefault(); if (deleting) remove.mutate(deleting); }}>Xoá</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
