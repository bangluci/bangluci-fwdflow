"use client";

import { useQuery } from "@tanstack/react-query";
import { Flag } from "lucide-react";
import Link from "next/link";
import { ErrorBanner } from "@/components/form-field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { formatNumber, formatVnd, todayVn } from "@/lib/format";
import { useUrlFilters } from "@/lib/use-url-filters";
import { cn } from "@/lib/utils";

type Row = { key: string | number | null; label: string; shipments: number; estimate_vnd: number; actual_vnd: number; deviation_pct: number | null; flagged_shipments: number };
type Report = { from_month: string; to_month: string; group_by: string; fx_usd_vnd: number; rows: Row[]; totals: { estimate_vnd: number; actual_vnd: number; flagged_shipments: number } };

const GROUPS: Record<string, string> = { shipment: "Lô", month: "Tháng", customer: "Khách", carrier: "Hãng tàu" };
const thisMonth = todayVn().slice(0, 7);
const DEFAULTS = { from: thisMonth, to: thisMonth, group: "shipment" };
const num = "text-right tabular-nums";

export function ReportsView() {
  const [filters, setFilters] = useUrlFilters(DEFAULTS);
  const report = useQuery({
    queryKey: ["report-demdet", filters],
    queryFn: () => apiFetch<Report>(`/api/reports/demdet?from_month=${filters.from}&to_month=${filters.to}&group_by=${filters.group}`),
    retry: false,
    placeholderData: (previous) => previous,
  });
  const data = report.data;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          Từ tháng
          <Input type="month" aria-label="Từ tháng" className="h-8 w-40" value={filters.from} onChange={(e) => e.target.value && setFilters({ from: e.target.value })} />
        </label>
        <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          Đến tháng
          <Input type="month" aria-label="Đến tháng" className="h-8 w-40" value={filters.to} onChange={(e) => e.target.value && setFilters({ to: e.target.value })} />
        </label>
        <Select value={filters.group} onValueChange={(v) => setFilters({ group: v })}>
          <SelectTrigger aria-label="Nhóm theo" className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>{Object.entries(GROUPS).map(([k, l]) => <SelectItem key={k} value={k}>Nhóm theo: {l}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <ErrorBanner error={report.error} />
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table className="text-[13px]">
          <TableHeader className="bg-muted/90">
            <TableRow className="h-9">
              {[GROUPS[filters.group], "Số lô", "Ước tính (VND)", "Thực tế (VND)", "Lệch", "Lô gắn cờ"].map((h, i) => (
                <TableHead key={h} className={cn("text-[11px] font-medium uppercase tracking-wide text-muted-foreground", i > 0 && "text-right")}>{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.rows ?? []).map((row) => (
              <TableRow key={String(row.key)} className={cn("h-10", row.flagged_shipments > 0 && "bg-danger-soft/40")}>
                <TableCell className="font-medium">
                  {data?.group_by === "shipment" ? <Link className="font-mono text-xs font-semibold text-primary hover:underline" href={`/shipments/${row.key}`}>{row.label}</Link> : row.label}
                  {row.flagged_shipments > 0 && <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-danger-ink"><Flag className="size-3 fill-current" aria-hidden />Lệch &gt; 20%</span>}
                </TableCell>
                <TableCell className={num}>{row.shipments}</TableCell>
                <TableCell className={num}>{formatVnd(row.estimate_vnd)}</TableCell>
                <TableCell className={num}>{formatVnd(row.actual_vnd)}</TableCell>
                <TableCell className={num}>{row.deviation_pct === null ? "—" : `${row.deviation_pct > 0 ? "+" : ""}${formatNumber(row.deviation_pct)}%`}</TableCell>
                <TableCell className={num}>{row.flagged_shipments}</TableCell>
              </TableRow>
            ))}
          </TableBody>
          {data && data.rows.length > 0 && (
            <TableFooter>
              <TableRow className="h-10 font-semibold">
                <TableCell>Tổng</TableCell>
                <TableCell className={num}>{data.rows.reduce((n, r) => n + r.shipments, 0)}</TableCell>
                <TableCell className={num}>{formatVnd(data.totals.estimate_vnd)}</TableCell>
                <TableCell className={num}>{formatVnd(data.totals.actual_vnd)}</TableCell>
                <TableCell />
                <TableCell className={num}>{data.totals.flagged_shipments}</TableCell>
              </TableRow>
            </TableFooter>
          )}
        </Table>
        {report.isPending && <p className="px-6 py-10 text-center text-sm text-muted-foreground">Đang tải…</p>}
        {data && data.rows.length === 0 && <p className="px-6 py-12 text-center text-sm text-muted-foreground">Không có lô FCL nào đã dỡ hàng trong khoảng tháng này.</p>}
      </div>
      {data && <p className="text-xs text-muted-foreground">Tỷ giá tham chiếu USD/VND: {formatNumber(data.fx_usd_vnd)}. Ước tính lấy từ đồng hồ free time theo bậc phí; thực tế là chi phí DEM / DET / gộp đã nhập ở tab Tài chính của lô.</p>}
    </div>
  );
}
