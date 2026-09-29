"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ShipmentStatusBadge } from "@/components/shipment-status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

export type PortalShipment = { id: number; code: string; load_type: string; status: string; hbl_no: string | null; vessel: string | null; voyage: string | null; etd: string | null; eta: string | null; total_packages: number | null; pol: string | null; pod: string | null };

export default function PortalHome() {
  const list = useQuery({ queryKey: ["portal-shipments"], queryFn: () => apiFetch<PortalShipment[]>("/api/portal/shipments") });
  if (list.error) return <p role="alert" className="rounded-lg border bg-card p-8 text-center text-sm">{list.error.message}</p>;
  if (!list.data) return <p className="text-muted-foreground">Đang tải…</p>;
  if (list.data.length === 0) return <p className="rounded-lg border bg-card p-10 text-center text-sm text-muted-foreground">Bạn chưa có lô hàng nào.</p>;
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold">Lô hàng của bạn ({list.data.length})</h1>
      <div className="hidden overflow-hidden rounded-lg border bg-card md:block">
        <Table className="text-[13px]">
          <TableHeader className="bg-muted/90">
            <TableRow className="h-9">{["Mã lô", "Trạng thái", "Loại", "HBL", "Tàu / chuyến", "Tuyến", "ETD", "ETA", "Số kiện"].map((h) => <TableHead key={h} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{h}</TableHead>)}</TableRow>
          </TableHeader>
          <TableBody>
            {list.data.map((s) => (
              <TableRow key={s.id} className="h-10">
                <TableCell><Link href={`/portal/shipments/${s.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">{s.code}</Link></TableCell>
                <TableCell><ShipmentStatusBadge status={s.status} /></TableCell>
                <TableCell>{s.load_type}</TableCell>
                <TableCell className="font-mono text-xs">{s.hbl_no}</TableCell>
                <TableCell>{[s.vessel, s.voyage].filter(Boolean).join(" / ")}</TableCell>
                <TableCell className="font-mono text-xs">{s.pol} → {s.pod}</TableCell>
                <TableCell>{formatDate(s.etd)}</TableCell>
                <TableCell>{formatDate(s.eta)}</TableCell>
                <TableCell className="tabular-nums">{s.total_packages}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="space-y-2 md:hidden">
        {list.data.map((s) => (
          <li key={s.id}>
            <Link href={`/portal/shipments/${s.id}`} className="block space-y-1.5 rounded-lg border bg-card p-4 active:bg-accent/50">
              <div className="flex items-center justify-between gap-2"><span className="font-mono text-sm font-semibold">{s.code}</span><ShipmentStatusBadge status={s.status} /></div>
              <p className="text-[13px] text-muted-foreground">{s.pol} → {s.pod} · {s.load_type}{s.total_packages ? ` · ${s.total_packages} kiện` : ""}</p>
              <p className="text-[13px] text-muted-foreground">ETA {formatDate(s.eta) || "chưa có"}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
