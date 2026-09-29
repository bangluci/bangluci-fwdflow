"use client";

import { useQuery } from "@tanstack/react-query";
import { FileClock, Package, ScanSearch, Truck, TriangleAlert, OctagonAlert, PackageX, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { formatDate, formatVnd } from "@/lib/format";
import { cn } from "@/lib/utils";

type Dashboard = {
  as_of: string;
  active_shipments: number;
  containers_yellow: number;
  containers_red: number;
  extractions_review: number;
  extractions_failed: number;
  trucking_unassigned: number;
  last_mile_failed: number;
  do_expiring: { shipment_id: number; code: string; do_valid_until: string }[];
  month_revenue_vnd?: number;
  month_profit_vnd?: number;
};

type Tone = "neutral" | "warning" | "danger";
const TONE: Record<Tone, string> = { neutral: "text-foreground", warning: "text-warning-ink", danger: "text-danger-ink" };

function Stat({ label, value, href, icon: Icon, tone = "neutral", hint }: { label: string; value: number; href: string; icon: LucideIcon; tone?: Tone; hint?: string }) {
  const alert = tone !== "neutral" && value > 0;
  return (
    <Link href={href} className={cn("group rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40", alert && tone === "danger" && "border-danger/30", alert && tone === "warning" && "border-warning/40")}>
      <p className="flex items-center gap-1.5 text-[13px] text-muted-foreground"><Icon aria-hidden className="size-4" />{label}</p>
      <p className={cn("mt-2 text-3xl font-semibold tabular-nums", alert ? TONE[tone] : "text-foreground")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Link>
  );
}

export function DashboardView() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => apiFetch<Dashboard>("/api/reports/dashboard"), refetchOnWindowFocus: true });
  if (query.error) {
    return <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">{query.error.message}</p>;
  }
  const d = query.data;
  if (!d) return <p className="text-muted-foreground">Đang tải…</p>;
  return (
    <div className="space-y-5">
      <p className="text-[13px] text-muted-foreground">Số liệu tính tới ngày {formatDate(d.as_of)}. Bấm vào ô để mở danh sách tương ứng.</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Lô đang xử lý" value={d.active_shipments} href="/shipments" icon={Package} />
        <Stat label="Container quá hạn free" value={d.containers_red} href="/freetime?level=RED" icon={OctagonAlert} tone="danger" />
        <Stat label="Container sắp hạn free" value={d.containers_yellow} href="/freetime?level=YELLOW" icon={TriangleAlert} tone="warning" hint="Còn 0 đến 2 ngày" />
        <Stat label="D/O sắp hết hạn" value={d.do_expiring.length} href="/shipments" icon={FileClock} tone="warning" hint="Hết hạn trong 1 ngày tới" />
        <Stat label="AI đọc xong, chờ duyệt" value={d.extractions_review} href="/shipments" icon={ScanSearch} tone="warning" />
        <Stat label="AI đọc lỗi" value={d.extractions_failed} href="/shipments" icon={ScanSearch} tone="danger" />
        <Stat label="Lệnh xe chưa gán" value={d.trucking_unassigned} href="/trucking" icon={Truck} tone="warning" />
        <Stat label="Đơn giao thất bại" value={d.last_mile_failed} href="/last-mile?status=FAILED" icon={PackageX} tone="danger" />
      </div>
      {d.month_revenue_vnd !== undefined && d.month_profit_vnd !== undefined && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-[13px] text-muted-foreground">Doanh thu tháng này</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{formatVnd(d.month_revenue_vnd)}</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-[13px] text-muted-foreground">Lợi nhuận tháng này</p>
            <p className={cn("mt-2 text-2xl font-semibold tabular-nums", d.month_profit_vnd < 0 && "text-danger-ink")}>{formatVnd(d.month_profit_vnd)}</p>
          </div>
        </div>
      )}
      <section className="rounded-lg border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold">Lô có D/O sắp hết hạn</h2>
        {d.do_expiring.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Không có lô nào.</p>
        ) : (
          <ul className="divide-y text-[13px]">
            {d.do_expiring.map((s) => (
              <li key={s.shipment_id} className="flex items-center justify-between py-2">
                <Link href={`/shipments/${s.shipment_id}`} className="font-mono font-semibold text-primary hover:underline">{s.code}</Link>
                <span className="text-muted-foreground">hết hạn {formatDate(s.do_valid_until)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
