"use client";

import { useQuery } from "@tanstack/react-query";
import { columnHelper, DataTable } from "@/components/data-table";
import { Pager } from "@/components/pager";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch, apiFetchPage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useUrlFilters } from "@/lib/use-url-filters";

type AuditRow = { id: number; at: string; actor_id: number | null; actor_name: string | null; action: string; entity: string; entity_id: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null };
type UserRow = { id: number; full_name: string };

const DEFAULTS = { entity: "", actor: "", from: "", to: "", page: "1" };
const ANY = "__any__";
const helper = columnHelper<AuditRow>();
const show = (value: unknown) => (value === null || value === undefined ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value));

/** Thay đổi dạng văn bản thuần `cột: cũ → mới` (chỉ cột có đổi; tạo mới thì chỉ có giá trị mới). */
export function describeChange(row: Pick<AuditRow, "before" | "after">): string {
  const before = row.before ?? {};
  const after = row.after ?? {};
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return keys
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .map((key) => (row.before ? `${key}: ${show(before[key])} → ${show(after[key])}` : `${key}: ${show(after[key])}`))
    .join("; ");
}

const columns = [
  helper.accessor((row) => formatDateTime(row.at), { id: "at", header: "Thời điểm", enableSorting: false }),
  helper.accessor((row) => row.actor_name ?? "Hệ thống", { id: "actor", header: "Người thao tác" }),
  helper.accessor("action", { header: "Thao tác", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor("entity", { header: "Thực thể", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.accessor((row) => row.entity_id ?? "", { id: "entity_id", header: "Id", cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
  helper.display({ id: "change", header: "Thay đổi", cell: (ctx) => <span className="block max-w-[34rem] truncate text-xs" title={describeChange(ctx.row.original)}>{describeChange(ctx.row.original)}</span> }),
];

export function AuditView() {
  const [filters, setFilters] = useUrlFilters(DEFAULTS);
  const entities = useQuery({ queryKey: ["audit-entities"], queryFn: () => apiFetch<string[]>("/api/audit/entities") });
  const users = useQuery({ queryKey: ["users", ""], queryFn: () => apiFetch<UserRow[]>("/api/users") });
  const list = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => {
      const params = new URLSearchParams({ page: filters.page, page_size: "50" });
      if (filters.entity) params.set("entity", filters.entity);
      if (filters.actor) params.set("actor_id", filters.actor);
      if (filters.from) params.set("date_from", filters.from);
      if (filters.to) params.set("date_to", filters.to);
      return apiFetchPage<AuditRow>(`/api/audit?${params}`);
    },
    placeholderData: (previous) => previous,
    retry: false,
  });
  if (list.error instanceof ApiError && list.error.status === 403) {
    return <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">Bạn không có quyền xem nhật ký</p>;
  }
  const hasFilter = !!(filters.entity || filters.actor || filters.from || filters.to);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={filters.entity || ANY} onValueChange={(v) => setFilters({ entity: v === ANY ? "" : v })}>
          <SelectTrigger aria-label="Lọc theo thực thể" className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Thực thể: tất cả</SelectItem>
            {(entities.data ?? []).map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filters.actor || ANY} onValueChange={(v) => setFilters({ actor: v === ANY ? "" : v })}>
          <SelectTrigger aria-label="Lọc theo người thao tác" className="w-52"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Người thao tác: tất cả</SelectItem>
            {(users.data ?? []).map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.full_name}</SelectItem>)}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
          Từ ngày
          <Input type="date" aria-label="Từ ngày" className="h-8 w-40" value={filters.from} onChange={(e) => setFilters({ from: e.target.value })} />
          đến
          <Input type="date" aria-label="Đến ngày" className="h-8 w-40" value={filters.to} onChange={(e) => setFilters({ to: e.target.value })} />
        </label>
      </div>
      <DataTable columns={columns} data={list.data?.data ?? []} loading={list.isPending} error={list.error} onRetry={() => list.refetch()} filtered={hasFilter}
        getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có nhật ký nào" }, filtered: { title: "Không có dòng nhật ký nào khớp", hint: "Thử đổi khoảng ngày hoặc bỏ bộ lọc." } }} />
      <Pager meta={list.data?.meta} onPage={(page) => setFilters({ page: String(page) })} />
    </div>
  );
}
