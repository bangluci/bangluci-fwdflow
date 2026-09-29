"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, Settings2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { FreeTimeChip } from "@/components/freetime-chip";
import { Pager } from "@/components/pager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetchPage } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { FEE_TYPE_SHORT, LEVEL_FILTER_LABEL, type FreeTimeRow } from "@/lib/freetime";
import { useDebounce } from "@/lib/use-debounce";
import { useMe } from "@/lib/use-me";
import { useUrlFilters } from "@/lib/use-url-filters";
import { cn } from "@/lib/utils";

// Mặc định chỉ hiện đồng hồ đang chạy (đó là thứ cần theo dõi); chọn "tất cả" để xem cả đồng hồ đã đóng.
const DEFAULTS = { q: "", level: "", status: "OPEN", fee: "", cancelled: "", page: "1" };
const ALL = "ALL";
const STATUS_LABEL: Record<string, string> = { OPEN: "Đang chạy", CLOSED: "Đã đóng", NOT_STARTED: "Chưa bắt đầu", NO_RULE: "Chưa có quy tắc", MISSING_DATA: "Thiếu ngày dỡ" };
const ANY = "__any__";
const helper = columnHelper<FreeTimeRow>();

const columns = [
  helper.accessor("container_no", { header: "Container", cell: (ctx) => <span className="font-mono text-xs font-semibold">{ctx.getValue()}</span> }),
  helper.accessor("shipment_code", {
    header: "Lô",
    cell: (ctx) => (
      <Link href={`/shipments/${ctx.row.original.shipment_id}`} onClick={(e) => e.stopPropagation()} className="font-mono text-xs font-semibold text-primary hover:underline">
        {ctx.getValue()}
      </Link>
    ),
  }),
  helper.accessor("customer_name", { header: "Khách" }),
  helper.accessor((row) => row.carrier_name ?? "", { id: "carrier", header: "Hãng tàu" }),
  helper.accessor((row) => row.pod_code ?? "", { id: "pod", header: "Cảng dỡ", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor("fee_type", { header: "Loại phí", cell: (ctx) => FEE_TYPE_SHORT[ctx.getValue()] }),
  helper.display({ id: "chip", header: "Tình trạng", cell: (ctx) => <FreeTimeChip row={ctx.row.original} showFee={false} /> }),
  helper.accessor((row) => formatDate(row.start_date), { id: "start", header: "Bắt đầu" }),
  helper.accessor((row) => formatDate(row.due_date), { id: "due", header: "Hạn free" }),
  helper.accessor((row) => row.days_used ?? -1, { id: "used", header: "Đã dùng", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.days_used ?? ""}</span> }),
  helper.accessor((row) => row.fee_amount ?? 0, { id: "fee", header: "Phí ước tính", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.row.original.fee_amount ? formatMoney(ctx.row.original.fee_amount, ctx.row.original.fee_currency) : ""}</span> }),
];

export function FreeTimeBoard() {
  const router = useRouter();
  const { data: me } = useMe();
  const [filters, setFilters] = useUrlFilters(DEFAULTS);
  const [search, setSearch] = useState(filters.q);
  const q = useDebounce(search.trim());
  useEffect(() => {
    if (q !== filters.q) setFilters({ q });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);
  const levels = useMemo(() => (filters.level ? filters.level.split(",") : []), [filters.level]);
  const list = useQuery({
    queryKey: ["freetime-containers", filters],
    queryFn: () => {
      const params = new URLSearchParams({ page: filters.page, limit: "50" });
      if (filters.q) params.set("q", filters.q);
      levels.forEach((l) => params.append("level", l));
      if (filters.status && filters.status !== ALL) params.append("status", filters.status);
      if (filters.fee) params.append("fee_type", filters.fee);
      if (filters.cancelled) params.set("include_cancelled", "true");
      return apiFetchPage<FreeTimeRow>(`/api/freetime/containers?${params}`);
    },
    placeholderData: (previous) => previous,
  });
  const toggleLevel = (level: string) => setFilters({ level: (levels.includes(level) ? levels.filter((l) => l !== level) : [...levels, level]).join(",") });
  const hasFilter = !!(filters.q || levels.length || filters.status !== DEFAULTS.status || filters.fee);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Tìm kiếm" placeholder="Số container, mã lô, khách" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={filters.status || ALL} onValueChange={(v) => setFilters({ status: v })}>
          <SelectTrigger aria-label="Lọc theo trạng thái đồng hồ" className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Đồng hồ: tất cả</SelectItem>
            {Object.entries(STATUS_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.fee || ANY} onValueChange={(v) => setFilters({ fee: v === ANY ? "" : v })}>
          <SelectTrigger aria-label="Lọc theo loại phí" className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Loại phí: tất cả</SelectItem>
            {Object.entries(FEE_TYPE_SHORT).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          <input type="checkbox" className="size-3.5 accent-[var(--primary)]" checked={!!filters.cancelled} onChange={(e) => setFilters({ cancelled: e.target.checked ? "1" : "" })} />
          Hiện lô đã huỷ
        </label>
        {me?.permissions.includes("freetime.write") && (
          <Button variant="outline" className="ml-auto" asChild>
            <Link href="/freetime/rules"><Settings2 />Quy tắc và bậc phí</Link>
          </Button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Lọc theo mức">
        {Object.entries(LEVEL_FILTER_LABEL).map(([level, label]) => {
          const on = levels.includes(level);
          return (
            <button key={level} type="button" aria-pressed={on} onClick={() => toggleLevel(level)}
              className={cn("h-7 rounded-full border px-2.5 text-xs transition-colors", on ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>
              {label}
            </button>
          );
        })}
      </div>
      <DataTable
        columns={columns}
        data={list.data?.data ?? []}
        loading={list.isPending}
        error={list.error}
        onRetry={() => list.refetch()}
        filtered={hasFilter}
        getRowId={(r) => `${r.container_id}-${r.fee_type}`}
        onRowClick={(row) => router.push(`/shipments/${row.shipment_id}`)}
        rowClassName={(row) => (row.status === "OPEN" && row.level === "RED" ? "bg-danger-soft/40" : undefined)}
        empty={{ none: { title: "Chưa có đồng hồ free time", hint: "Đồng hồ xuất hiện khi lô FCL có container và ngày dỡ khỏi tàu." }, filtered: { title: "Không có đồng hồ nào khớp", hint: "Thử bỏ bớt bộ lọc." } }}
      />
      <Pager meta={list.data?.meta} onPage={(page) => setFilters({ page: String(page) })} />
    </div>
  );
}
