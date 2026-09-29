"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { FreeTimeChip } from "@/components/freetime-chip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, apiFetchPage } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { FEE_TYPE_LABEL, type FreeTimeRow } from "@/lib/freetime";

type Override = { fee_type: "DEM" | "DET" | "COMBINED"; free_days: number; source: string; document_id: number | null };
const SOURCE_LABEL: Record<string, string> = { ARRIVAL_NOTICE: "Thông báo hàng đến", DO: "D/O", CONTRACT: "Hợp đồng" };
const helper = columnHelper<FreeTimeRow>();

const columns = [
  helper.accessor("container_no", { header: "Container", cell: (ctx) => <span className="font-mono text-xs font-semibold">{ctx.getValue()}</span> }),
  helper.accessor("fee_type", { header: "Đồng hồ", cell: (ctx) => FEE_TYPE_LABEL[ctx.getValue()] }),
  helper.display({ id: "chip", header: "Tình trạng", cell: (ctx) => <FreeTimeChip row={ctx.row.original} /> }),
  helper.accessor((row) => `${formatDate(row.start_date)}${row.end_date ? ` → ${formatDate(row.end_date)}` : row.start_date ? " → nay" : ""}`, { id: "range", header: "Khoảng tính" }),
  helper.accessor((row) => row.free_days ?? -1, { id: "free", header: "Free", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.free_days ?? ""}</span> }),
  helper.accessor((row) => row.days_used ?? -1, { id: "used", header: "Đã dùng", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.days_used ?? ""}</span> }),
  helper.accessor((row) => formatDate(row.due_date), { id: "due", header: "Hạn cuối free" }),
  helper.accessor((row) => (row.rule_source === "OVERRIDE" ? "Ghi đè" : row.rule_source === "RULE" ? "Quy tắc hãng tàu" : "Chưa có"), { id: "source", header: "Nguồn số ngày" }),
  helper.accessor((row) => row.fee_amount ?? 0, { id: "fee", header: "Phí ước tính", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.fee_amount ? formatMoney(ctx.row.original.fee_amount, ctx.row.original.fee_currency) : ""}</span> }),
];

function OverridePanel({ shipmentId, canWrite }: { shipmentId: number; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ fee_type: "DEM", free_days: "", source: "DO" });
  const overrides = useQuery({ queryKey: ["freetime-overrides", shipmentId], queryFn: () => apiFetch<Override[]>(`/api/shipments/${shipmentId}/freetime-overrides`) });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["freetime-overrides", shipmentId] });
    queryClient.invalidateQueries({ queryKey: ["freetime-shipment", shipmentId] });
    queryClient.invalidateQueries({ queryKey: ["shipment-side", shipmentId] });
  };
  const save = useMutation({
    mutationFn: () => apiFetch(`/api/shipments/${shipmentId}/freetime-overrides`, { method: "PUT", json: { fee_type: form.fee_type, free_days: Number(form.free_days), source: form.source } }),
    onSuccess: () => { setForm((c) => ({ ...c, free_days: "" })); refresh(); },
  });
  const remove = useMutation({
    mutationFn: (feeType: string) => apiFetch(`/api/shipments/${shipmentId}/freetime-overrides/${feeType}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return (
    <section className="space-y-3 rounded-lg border bg-card p-4">
      <div>
        <h3 className="text-sm font-semibold">Số ngày free ghi riêng cho lô</h3>
        <p className="text-xs text-muted-foreground">Dùng khi thông báo hàng đến, D/O hoặc hợp đồng ghi số ngày khác quy tắc chung của hãng tàu.</p>
      </div>
      <ul className="space-y-1.5">
        {(overrides.data ?? []).map((o) => (
          <li key={o.fee_type} className="flex items-center justify-between rounded-md bg-muted/60 px-3 py-1.5 text-[13px]">
            <span><span className="font-medium">{FEE_TYPE_LABEL[o.fee_type]}</span>: {o.free_days} ngày · theo {SOURCE_LABEL[o.source] ?? o.source}</span>
            {canWrite && <Button variant="ghost" size="icon-sm" aria-label={`Bỏ ghi đè ${o.fee_type}`} onClick={() => remove.mutate(o.fee_type)}><Trash2 /></Button>}
          </li>
        ))}
        {overrides.data?.length === 0 && <li className="text-[13px] text-muted-foreground">Chưa ghi đè: đang dùng quy tắc chung của hãng tàu.</li>}
      </ul>
      {canWrite && (
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); if (form.free_days !== "") save.mutate(); }}>
          <Field label="Đồng hồ" htmlFor="o-fee">
            <Select value={form.fee_type} onValueChange={(v) => setForm((c) => ({ ...c, fee_type: v }))}>
              <SelectTrigger id="o-fee" className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(FEE_TYPE_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Số ngày free" htmlFor="o-days"><Input id="o-days" type="number" min={0} max={365} className="w-28" value={form.free_days} onChange={(e) => setForm((c) => ({ ...c, free_days: e.target.value }))} /></Field>
          <Field label="Nguồn" htmlFor="o-src">
            <Select value={form.source} onValueChange={(v) => setForm((c) => ({ ...c, source: v }))}>
              <SelectTrigger id="o-src" className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(SOURCE_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Button type="submit" disabled={save.isPending || form.free_days === ""}>Lưu ghi đè</Button>
        </form>
      )}
      <ErrorBanner error={save.error ?? remove.error} />
    </section>
  );
}

export function FreeTimeTab({ shipmentId, canWrite }: { shipmentId: number; canWrite: boolean }) {
  const clocks = useQuery({
    queryKey: ["freetime-shipment", shipmentId],
    queryFn: () => apiFetchPage<FreeTimeRow>(`/api/freetime/containers?shipment_id=${shipmentId}&limit=200&include_cancelled=true`),
  });
  return (
    <div className="space-y-4">
      <DataTable columns={columns} data={clocks.data?.data ?? []} loading={clocks.isPending} error={clocks.error} onRetry={() => clocks.refetch()}
        getRowId={(r) => `${r.container_id}-${r.fee_type}`}
        empty={{ none: { title: "Chưa có đồng hồ free time", hint: "Cần container và ngày dỡ khỏi tàu; lô LCL không tính free time." }, filtered: { title: "Không có kết quả" } }} />
      <OverridePanel shipmentId={shipmentId} canWrite={canWrite} />
    </div>
  );
}
