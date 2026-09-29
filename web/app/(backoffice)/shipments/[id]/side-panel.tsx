"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleDashed, ListChecks, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { ErrorBanner } from "@/components/form-field";
import { FreeTimeChip } from "@/components/freetime-chip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, apiFetchPage } from "@/lib/api";
import type { FreeTimeRow } from "@/lib/freetime";
import { DOC_TYPE_LABEL } from "@/lib/shipment-labels";
import { IN_TRANSIT_FIELD_LABEL, type Checklist, type ShipmentDetail } from "@/lib/shipment-types";
import { cn } from "@/lib/utils";
import type { ExtractionSummary } from "./documents-tab";

export type TabKey = "info" | "items" | "declarations" | "containers" | "documents" | "freetime" | "charges" | "timeline";

type Discrepancy = { key: string; kind: string; level: "BLOCK" | "WARN" | string; field: string; values: Record<string, unknown>; ack: { reason: string } | null };
type Crosscheck = { status: string; discrepancies: Discrepancy[] };

const FIELD_LABEL: Record<string, string> = {
  container_no: "Số container", seal_no: "Số seal", mbl_no: "Số MBL", hbl_no: "Số HBL", consignee: "Người nhận", gross_weight_kg: "Tổng khối lượng",
  total_packages: "Tổng số kiện", total_value: "Tổng trị giá", vessel: "Tàu", voyage: "Chuyến", pol: "Cảng xếp", pod: "Cảng dỡ",
};

function Card({ title, icon: Icon, children }: { title: string; icon: typeof ListChecks; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-4">
      <h3 className="mb-2.5 flex items-center gap-1.5 text-[13px] font-semibold">
        <Icon aria-hidden className="size-4 text-muted-foreground" />
        {title}
      </h3>
      {children}
    </section>
  );
}

function DiscrepancyRow({ item, shipmentId, canAck }: { item: Discrepancy; shipmentId: number; canAck: boolean }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const ack = useMutation({
    mutationFn: () => apiFetch(`/api/shipments/${shipmentId}/discrepancy-acks`, { method: "POST", json: { discrepancy_key: item.key, reason: reason.trim() } }),
    onSuccess: () => { setOpen(false); queryClient.invalidateQueries({ queryKey: ["shipment-side", shipmentId] }); },
  });
  return (
    <li className="space-y-1.5 rounded-md border p-2.5 text-[13px]">
      <p className="flex items-center gap-1.5 font-medium">
        <TriangleAlert aria-hidden className={cn("size-3.5", item.level === "BLOCK" ? "text-danger" : "text-warning")} />
        {FIELD_LABEL[item.field] ?? item.field}
        <span className="text-xs font-normal text-muted-foreground">{item.level === "BLOCK" ? "chặn thông quan" : "cần xem"}</span>
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-xs">
        {Object.entries(item.values).map(([doc, value]) => (
          <div key={doc} className="contents">
            <dt className="text-muted-foreground">{DOC_TYPE_LABEL[doc] ?? doc}</dt>
            <dd className="font-mono break-all">{value == null ? "—" : String(value)}</dd>
          </div>
        ))}
      </dl>
      {item.ack ? (
        <p className="flex items-center gap-1 text-xs text-success-ink"><CircleCheck className="size-3.5" aria-hidden />Đã xác nhận: {item.ack.reason}</p>
      ) : canAck && (open ? (
        <div className="space-y-1.5">
          <Textarea aria-label="Lý do xác nhận" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Vì sao chấp nhận sai lệch này (tối thiểu 5 ký tự)" />
          <ErrorBanner error={ack.error} />
          <div className="flex gap-2">
            <Button size="xs" disabled={reason.trim().length < 5 || ack.isPending} onClick={() => ack.mutate()}>Xác nhận đã biết</Button>
            <Button size="xs" variant="ghost" onClick={() => setOpen(false)}>Đóng</Button>
          </div>
        </div>
      ) : (
        <Button size="xs" variant="outline" onClick={() => setOpen(true)}>Xác nhận đã biết…</Button>
      ))}
    </li>
  );
}

export function SidePanel({ shipment, canReview, onGoto }: { shipment: ShipmentDetail; canReview: boolean; onGoto: (tab: TabKey) => void }) {
  const id = shipment.id;
  const checklist = useQuery({ queryKey: ["shipment-side", id, "checklist"], queryFn: () => apiFetch<Checklist>(`/api/shipments/${id}/doc-checklist`) });
  const cross = useQuery({ queryKey: ["shipment-side", id, "crosscheck"], queryFn: () => apiFetch<Crosscheck>(`/api/shipments/${id}/crosscheck`) });
  const clocks = useQuery({
    queryKey: ["freetime-shipment", id],
    queryFn: () => apiFetchPage<FreeTimeRow>(`/api/freetime/containers?shipment_id=${id}&limit=200&include_cancelled=true`),
  });
  const extractions = useQuery({ queryKey: ["extractions", id], queryFn: () => apiFetch<ExtractionSummary[]>(`/api/shipments/${id}/extractions`), enabled: canReview });

  const tasks: { text: string; tab: TabKey }[] = [];
  if (shipment.status === "CREATED" && shipment.in_transit_missing.length) {
    tasks.push({ text: `Bổ sung để đi tiếp: ${shipment.in_transit_missing.map((k) => IN_TRANSIT_FIELD_LABEL[k] ?? k).join(", ")}`, tab: "info" });
  }
  if (checklist.data?.missing.length) tasks.push({ text: `Thiếu chứng từ: ${checklist.data.missing.map((d) => DOC_TYPE_LABEL[d] ?? d).join(", ")}`, tab: "documents" });
  if (shipment.status === "CUSTOMS_CLEARING") {
    if (shipment.declarations.length === 0) tasks.push({ text: "Thêm tờ khai hải quan", tab: "declarations" });
    else if (shipment.declarations.some((d) => !d.cleared_at)) tasks.push({ text: "Còn tờ khai chưa có ngày thông quan", tab: "declarations" });
  }
  const unresolved = (cross.data?.discrepancies ?? []).filter((d) => d.level === "BLOCK" && !d.ack);
  if (unresolved.length) tasks.push({ text: `${unresolved.length} sai lệch chứng từ mức chặn chưa xác nhận`, tab: "documents" });
  const waiting = (extractions.data ?? []).filter((e) => e.status === "REVIEW").length;
  if (waiting) tasks.push({ text: `${waiting} chứng từ AI đã đọc xong, chờ duyệt`, tab: "documents" });
  const bad = (clocks.data?.data ?? []).filter((r) => r.status === "OPEN" && (r.level === "RED" || r.level === "YELLOW"));
  if (bad.length) tasks.push({ text: `${bad.length} đồng hồ free time sắp hoặc đã quá hạn`, tab: "freetime" });

  const worst = (clocks.data?.data ?? []).filter((r) => r.status !== "NOT_STARTED" && r.status !== "CLOSED").slice(0, 6);
  return (
    <aside className="space-y-3">
      <Card title="Việc cần làm tiếp theo" icon={ListChecks}>
        {tasks.length === 0 ? (
          <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><CircleCheck className="size-4 text-success" aria-hidden />Không có gì đang chặn lô này.</p>
        ) : (
          <ul className="space-y-1.5">
            {tasks.map((t) => (
              <li key={t.text}>
                <button type="button" onClick={() => onGoto(t.tab)} className="w-full rounded-md bg-warning-soft px-2.5 py-1.5 text-left text-[13px] text-warning-ink hover:brightness-95">
                  {t.text}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Chứng từ bắt buộc" icon={CircleDashed}>
        {checklist.data?.items.length ? (
          <ul className="space-y-1 text-[13px]">
            {checklist.data.items.map((item) => (
              <li key={item.doc_type} className="flex items-center gap-1.5">
                {item.present ? <CircleCheck className="size-3.5 text-success" aria-hidden /> : <CircleDashed className="size-3.5 text-muted-foreground" aria-hidden />}
                <span className={cn(!item.present && "text-muted-foreground")}>{item.label}</span>
                {!item.present && <span className="ml-auto text-xs text-warning-ink">thiếu</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted-foreground">Chưa có chứng từ bắt buộc ở trạng thái này.</p>
        )}
      </Card>
      {worst.length > 0 && (
        <Card title="Free time" icon={CircleDashed}>
          <ul className="space-y-1.5">
            {worst.map((row) => (
              <li key={`${row.container_id}-${row.fee_type}`} className="space-y-0.5">
                <p className="font-mono text-[11px] text-muted-foreground">{row.container_no}</p>
                <button type="button" onClick={() => onGoto("freetime")} className="text-left"><FreeTimeChip row={row} /></button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="Đối chiếu chứng từ" icon={TriangleAlert}>
        {cross.data?.status === "INSUFFICIENT" ? (
          <p className="text-[13px] text-muted-foreground">Chưa đủ chứng từ đã duyệt để đối chiếu (cần ít nhất hai loại).</p>
        ) : cross.data && cross.data.discrepancies.length === 0 ? (
          <p className="flex items-center gap-1.5 text-[13px]"><CircleCheck className="size-4 text-success" aria-hidden />Các chứng từ đã duyệt khớp nhau.</p>
        ) : (
          <ul className="space-y-2">
            {(cross.data?.discrepancies ?? []).map((d) => <DiscrepancyRow key={d.key} item={d} shipmentId={id} canAck={canReview} />)}
          </ul>
        )}
      </Card>
    </aside>
  );
}
