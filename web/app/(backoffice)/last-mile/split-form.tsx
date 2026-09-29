"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { todayVn } from "@/lib/format";

type Row = { recipient_name: string; recipient_phone: string; address: string; packages: string; weight_kg: string; planned_date: string; driver_id: string };
const PHONE = /^(0|\+84)\d{9,10}$/;
const NONE = "__none__";
const blank = (): Row => ({ recipient_name: "", recipient_phone: "", address: "", packages: "", weight_kg: "", planned_date: todayVn(), driver_id: "" });

function check(row: Row): string | null {
  if (!row.recipient_name.trim() || row.recipient_name.trim().length > 200) return "Người nhận 1–200 ký tự";
  if (!PHONE.test(row.recipient_phone.replace(/[\s.]/g, ""))) return "Số điện thoại chưa đúng (0xxxxxxxxx hoặc +84xxxxxxxxx)";
  if (row.address.trim().length < 5 || row.address.trim().length > 500) return "Địa chỉ 5–500 ký tự";
  if (!(Number(row.packages) >= 1) || !Number.isInteger(Number(row.packages))) return "Số kiện phải là số nguyên từ 1";
  if (row.weight_kg && Number(row.weight_kg) < 0) return "Trọng lượng không được âm";
  if (row.planned_date < todayVn()) return "Ngày giao không được ở quá khứ";
  return null;
}

/** Tách quỹ kiện còn lại của lô thành các đơn giao (1–50 đơn một lần, tất cả hoặc không đơn nào). */
export function SplitForm({ shipmentId, available }: { shipmentId: number; available: number }) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<Row[]>([blank()]);
  const [problem, setProblem] = useState("");
  const drivers = useQuery({ queryKey: ["catalog", "drivers", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/drivers?active=true") });
  const total = rows.reduce((sum, r) => sum + (Number(r.packages) || 0), 0);
  const tooMany = total > available;
  const send = useMutation({
    mutationFn: () => apiFetch(`/api/shipments/${shipmentId}/last-mile-orders`, {
      method: "POST",
      json: { orders: rows.map((r) => ({
        recipient_name: r.recipient_name.trim(), recipient_phone: r.recipient_phone, address: r.address.trim(), packages: Number(r.packages),
        weight_kg: r.weight_kg || null, planned_date: r.planned_date, driver_id: r.driver_id ? Number(r.driver_id) : null,
      })) },
    }),
    onSuccess: async () => { setRows([blank()]); await queryClient.invalidateQueries({ queryKey: ["last-mile"] }); queryClient.invalidateQueries({ queryKey: ["shipment"] }); },
  });
  const set = (index: number, patch: Partial<Row>) => setRows((current) => current.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  function submit(event: React.FormEvent) {
    event.preventDefault();
    for (const [index, row] of rows.entries()) {
      const message = check(row);
      if (message) return setProblem(`Đơn ${index + 1}: ${message}`);
    }
    if (tooMany) return setProblem(`Vượt số kiện còn lại (${available})`);
    setProblem("");
    send.mutate();
  }
  const packagesExceeded = send.error instanceof ApiError && send.error.code === "PACKAGES_EXCEEDED";
  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">Tách đơn giao</h3>
        <p className={tooMany ? "text-xs font-medium text-danger-ink" : "text-xs text-muted-foreground"}>
          Đang tách {total} / còn {available} kiện{tooMany ? ` · Vượt số kiện còn lại (${available})` : ""}
        </p>
      </div>
      <div className="space-y-3">
        {rows.map((row, index) => (
          <div key={index} className="grid gap-2 rounded-md border p-3 sm:grid-cols-6">
            <Field label="Người nhận" htmlFor={`s-name-${index}`} className="sm:col-span-2"><Input id={`s-name-${index}`} value={row.recipient_name} onChange={(e) => set(index, { recipient_name: e.target.value })} /></Field>
            <Field label="Số điện thoại" htmlFor={`s-phone-${index}`}><Input id={`s-phone-${index}`} inputMode="tel" value={row.recipient_phone} onChange={(e) => set(index, { recipient_phone: e.target.value })} /></Field>
            <Field label="Số kiện" htmlFor={`s-pk-${index}`}><Input id={`s-pk-${index}`} type="number" min={1} value={row.packages} onChange={(e) => set(index, { packages: e.target.value })} /></Field>
            <Field label="Trọng lượng (kg)" htmlFor={`s-kg-${index}`}><Input id={`s-kg-${index}`} inputMode="decimal" value={row.weight_kg} onChange={(e) => set(index, { weight_kg: e.target.value })} /></Field>
            <Field label="Ngày giao" htmlFor={`s-date-${index}`}><Input id={`s-date-${index}`} type="date" min={todayVn()} value={row.planned_date} onChange={(e) => set(index, { planned_date: e.target.value })} /></Field>
            <Field label="Địa chỉ" htmlFor={`s-addr-${index}`} className="sm:col-span-3"><Input id={`s-addr-${index}`} value={row.address} onChange={(e) => set(index, { address: e.target.value })} /></Field>
            <Field label="Tài xế (tuỳ chọn)" htmlFor={`s-drv-${index}`} className="sm:col-span-2">
              <Select value={row.driver_id || NONE} onValueChange={(v) => set(index, { driver_id: v === NONE ? "" : v })}>
                <SelectTrigger id={`s-drv-${index}`} className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Phân công sau</SelectItem>
                  {(drivers.data ?? []).map((d) => <SelectItem key={d.id} value={String(d.id)}>{String(d.full_name)}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <div className="flex items-end justify-end">
              {rows.length > 1 && <Button type="button" variant="ghost" size="icon-sm" aria-label={`Xoá đơn ${index + 1}`} onClick={() => setRows((c) => c.filter((_, i) => i !== index))}><Trash2 /></Button>}
            </div>
          </div>
        ))}
      </div>
      <ErrorBanner error={problem || (packagesExceeded ? `Vượt số kiện còn lại (${available})` : send.error)} />
      <div className="flex items-center justify-between">
        <Button type="button" variant="outline" size="sm" disabled={rows.length >= 50} onClick={() => setRows((c) => [...c, blank()])}><Plus />Thêm đơn</Button>
        <Button type="submit" disabled={send.isPending || tooMany}>{send.isPending ? "Đang tách…" : `Tách ${rows.length} đơn`}</Button>
      </div>
    </form>
  );
}
