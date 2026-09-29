"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import { ShipmentStatusBadge } from "@/components/shipment-status";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { DOC_TYPE_LABEL, STATUS_LABEL, type ShipmentStatus } from "@/lib/shipment-labels";
import type { PortalShipment } from "../../page";

type Detail = PortalShipment & {
  containers: { container_no: string; container_type: string }[];
  timeline: { status: string; occurred_at: string }[];
  documents: { id: number; doc_type: string; created_at: string }[];
};

export function PortalShipmentView({ id }: { id: number }) {
  const query = useQuery({ queryKey: ["portal-shipment", id], queryFn: () => apiFetch<Detail>(`/api/portal/shipments/${id}`), retry: false });
  if (query.error instanceof ApiError && query.error.status === 404) {
    return (
      <div role="alert" className="mx-auto max-w-md space-y-3 rounded-lg border bg-card p-10 text-center">
        <p className="font-medium">Không tìm thấy lô</p>
        <Button asChild variant="outline"><Link href="/portal">Về danh sách lô</Link></Button>
      </div>
    );
  }
  if (query.error) return <p role="alert" className="rounded-lg border bg-card p-8 text-center text-sm">{query.error.message}</p>;
  const s = query.data;
  if (!s) return <p className="text-muted-foreground">Đang tải…</p>;
  const rows: [string, string][] = [
    ["Loại hàng", s.load_type], ["HBL", s.hbl_no ?? ""], ["Tàu / chuyến", [s.vessel, s.voyage].filter(Boolean).join(" / ")],
    ["Cảng xếp → dỡ", `${s.pol ?? "—"} → ${s.pod ?? "—"}`], ["ETD", formatDate(s.etd)], ["ETA", formatDate(s.eta)], ["Số kiện", s.total_packages?.toString() ?? ""],
  ];
  return (
    <div className="space-y-4">
      <Link href="/portal" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" aria-hidden />Lô hàng của bạn</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-xl font-semibold">{s.code}</h1>
        <ShipmentStatusBadge status={s.status} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Thông tin lô</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            {rows.map(([label, value]) => (
              <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd>{value || "—"}</dd></div>
            ))}
          </dl>
          {s.containers.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">Container</h3>
              <ul className="space-y-1 text-[13px]">{s.containers.map((c) => <li key={c.container_no}><span className="font-mono font-semibold">{c.container_no}</span> <span className="text-muted-foreground">{c.container_type}</span></li>)}</ul>
            </div>
          )}
        </section>
        <section className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold">Hành trình</h2>
          <ol className="relative space-y-3 pl-5 before:absolute before:top-1.5 before:bottom-1.5 before:left-[0.3rem] before:w-px before:bg-border">
            {[...s.timeline].reverse().map((e, index) => (
              <li key={`${e.status}-${e.occurred_at}`} className="relative">
                <span className={index === 0 ? "absolute top-1.5 -left-5 size-2.5 rounded-full bg-primary" : "absolute top-1.5 -left-5 size-2.5 rounded-full border-2 border-primary bg-card"} aria-hidden />
                <p className={index === 0 ? "text-sm font-semibold" : "text-sm"}>{STATUS_LABEL[e.status as ShipmentStatus] ?? e.status}</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(e.occurred_at)}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <section className="rounded-lg border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold">Chứng từ</h2>
        {s.documents.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Chưa có chứng từ nào được chia sẻ.</p>
        ) : (
          <ul className="divide-y text-[13px]">
            {s.documents.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2">
                <span><span className="font-medium">{DOC_TYPE_LABEL[d.doc_type] ?? d.doc_type}</span> <span className="text-muted-foreground">· {formatDate(d.created_at)}</span></span>
                <Button asChild variant="outline" size="sm"><a href={`/api/portal/documents/${d.id}/file`} download><Download />Tải về</a></Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
