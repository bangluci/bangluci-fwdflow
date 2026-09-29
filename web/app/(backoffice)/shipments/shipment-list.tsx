"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { Pager } from "@/components/pager";
import { ShipmentStatusBadge } from "@/components/shipment-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, apiFetchPage } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { formatDate } from "@/lib/format";
import { LEVEL_FILTER_LABEL } from "@/lib/freetime";
import { ACTIVE_SHIPMENT_STATUSES, DELIVERY_MODE_LABEL, SHIPMENT_STATUSES, STATUS_LABEL, type ShipmentStatus } from "@/lib/shipment-labels";
import { useDebounce } from "@/lib/use-debounce";
import { useMe } from "@/lib/use-me";
import { useUrlFilters } from "@/lib/use-url-filters";
import { cn } from "@/lib/utils";

export type ShipmentRow = {
  id: number;
  code: string;
  load_type: "FCL" | "LCL";
  delivery_mode: keyof typeof DELIVERY_MODE_LABEL;
  status: string;
  customer_id: number;
  customer_name: string;
  carrier_code: string | null;
  mbl_no: string | null;
  hbl_no: string | null;
  pod_code: string | null;
  eta: string | null;
  do_valid_until: string | null;
  staff_name: string;
  container_count: number;
};

const DEFAULTS = { q: "", status: "", customer: "", carrier: "", level: "", eta_from: "", eta_to: "", all: "", page: "1" };
const ANY = "__any__";
const helper = columnHelper<ShipmentRow>();

const columns = [
  helper.accessor("code", {
    header: "Mã lô",
    cell: (ctx) => (
      <Link href={`/shipments/${ctx.row.original.id}`} className="font-mono text-xs font-semibold text-primary hover:underline">
        {ctx.getValue()}
      </Link>
    ),
  }),
  helper.accessor("status", { header: "Trạng thái", cell: (ctx) => <ShipmentStatusBadge status={ctx.getValue()} /> }),
  helper.accessor("load_type", { header: "Loại", cell: (ctx) => <span className="text-xs font-medium">{ctx.getValue()}</span> }),
  helper.accessor((row) => DELIVERY_MODE_LABEL[row.delivery_mode], { id: "delivery_mode", header: "Kiểu giao" }),
  helper.accessor("customer_name", { header: "Khách hàng", cell: (ctx) => <span className="font-medium">{ctx.getValue()}</span> }),
  helper.accessor((row) => row.carrier_code ?? "", { id: "carrier", header: "Hãng tàu", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor((row) => row.mbl_no ?? "", { id: "mbl_no", header: "MBL", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor((row) => row.hbl_no ?? "", { id: "hbl_no", header: "HBL", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor((row) => formatDate(row.eta), { id: "eta", header: "ETA" }),
  helper.accessor("container_count", { header: "Số cont", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.getValue()}</span> }),
];

function useOptions(kind: "customers" | "carriers") {
  return useQuery({ queryKey: ["catalog", kind, "options"], queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`) });
}

export function ShipmentList() {
  const router = useRouter();
  const { data: me } = useMe();
  const [filters, setFilters] = useUrlFilters(DEFAULTS);
  const [search, setSearch] = useState(filters.q);
  const q = useDebounce(search.trim());
  useEffect(() => {
    if (q !== filters.q) setFilters({ q });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ đẩy lên URL khi ô tìm kiếm ổn định
  }, [q]);

  const customers = useOptions("customers");
  const carriers = useOptions("carriers");
  const chosen = useMemo(() => (filters.status ? (filters.status.split(",") as ShipmentStatus[]) : []), [filters.status]);
  const statuses = chosen.length ? chosen : filters.all ? [] : [...ACTIVE_SHIPMENT_STATUSES];
  const hasFilter = !!(filters.q || chosen.length || filters.customer || filters.carrier || filters.level || filters.eta_from || filters.eta_to);

  const list = useQuery({
    queryKey: ["shipments", filters, statuses],
    queryFn: () => {
      const params = new URLSearchParams({ page: filters.page, limit: "50" });
      if (filters.q) params.set("q", filters.q);
      statuses.forEach((s) => params.append("status", s));
      if (filters.customer) params.set("customer_id", filters.customer);
      if (filters.carrier) params.set("carrier_id", filters.carrier);
      if (filters.level) params.append("freetime_level", filters.level);
      if (filters.eta_from) params.set("eta_from", filters.eta_from);
      if (filters.eta_to) params.set("eta_to", filters.eta_to);
      return apiFetchPage<ShipmentRow>(`/api/shipments?${params}`);
    },
    placeholderData: (previous) => previous,
  });

  const toggleStatus = (status: ShipmentStatus) =>
    setFilters({ status: (chosen.includes(status) ? chosen.filter((s) => s !== status) : [...chosen, status]).join(",") });
  const optionSelect = (label: string, value: string, key: "customer" | "carrier", rows: CatalogItem[] | undefined, width: string) => (
    <Select value={value || ANY} onValueChange={(v) => setFilters({ [key]: v === ANY ? "" : v })}>
      <SelectTrigger aria-label={label} className={width}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>{label}: tất cả</SelectItem>
        {(rows ?? []).map((row) => (
          <SelectItem key={row.id} value={String(row.id)}>
            {String(row.name ?? row.code)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-80">
          <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Tìm kiếm" placeholder="Số container, MBL/HBL, mã lô, tên khách" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {optionSelect("Khách", filters.customer, "customer", customers.data, "w-44")}
        {optionSelect("Hãng tàu", filters.carrier, "carrier", carriers.data, "w-40")}
        <Select value={filters.level || ANY} onValueChange={(v) => setFilters({ level: v === ANY ? "" : v })}>
          <SelectTrigger aria-label="Lọc theo free time" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Free time: tất cả</SelectItem>
            {Object.entries(LEVEL_FILTER_LABEL).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          ETA
          <Input type="date" aria-label="ETA từ" className="h-8 w-36" value={filters.eta_from} onChange={(e) => setFilters({ eta_from: e.target.value })} />
          –
          <Input type="date" aria-label="ETA đến" className="h-8 w-36" value={filters.eta_to} onChange={(e) => setFilters({ eta_to: e.target.value })} />
        </label>
        {me?.permissions.includes("shipment.write") && (
          <Button className="ml-auto" asChild>
            <Link href="/shipments/new">
              <Plus />
              Tạo lô
            </Link>
          </Button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Lọc theo trạng thái">
        {SHIPMENT_STATUSES.map((status) => {
          const on = chosen.includes(status);
          return (
            <button
              key={status}
              type="button"
              aria-pressed={on}
              onClick={() => toggleStatus(status)}
              className={cn(
                "h-7 rounded-full border px-2.5 text-xs transition-colors",
                on ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {STATUS_LABEL[status]}
            </button>
          );
        })}
        <label className="ml-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" className="size-3.5 accent-[var(--primary)]" checked={!!filters.all} onChange={(e) => setFilters({ all: e.target.checked ? "1" : "" })} />
          Hiện cả lô đã hoàn tất / đã huỷ
        </label>
      </div>
      <DataTable
        columns={columns}
        data={list.data?.data ?? []}
        loading={list.isPending}
        error={list.error}
        onRetry={() => list.refetch()}
        filtered={hasFilter}
        getRowId={(row) => String(row.id)}
        onRowClick={(row) => router.push(`/shipments/${row.id}`)}
        empty={{
          none: { title: "Chưa có lô hàng nào", hint: me?.permissions.includes("shipment.write") ? 'Bấm "Tạo lô" để tạo lô đầu tiên.' : undefined },
          filtered: { title: "Không có lô nào khớp", hint: "Thử bỏ bớt bộ lọc hoặc đổi từ khoá." },
        }}
      />
      <Pager meta={list.data?.meta} onPage={(page) => setFilters({ page: String(page) })} />
    </div>
  );
}
