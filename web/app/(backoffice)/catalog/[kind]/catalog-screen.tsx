"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { StatusBadge } from "@/components/status-badge";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch, errorText } from "@/lib/api";
import { CATALOG_KIND_KEYS, CATALOG_KINDS, type CatalogItem, type CatalogKind } from "@/lib/catalog-kinds";
import { useDebounce } from "@/lib/use-debounce";
import { useMe } from "@/lib/use-me";
import { cn } from "@/lib/utils";
import { CatalogFormDialog } from "./catalog-form-dialog";

const helper = columnHelper<CatalogItem>();
type ActiveFilter = "true" | "false" | "all";
const FILTER_LABELS: Record<ActiveFilter, string> = { true: "Đang dùng", false: "Ngừng dùng", all: "Tất cả" };

function useRefOptions(kind: CatalogKind): Partial<Record<CatalogKind, CatalogItem[]>> {
  const refKinds = [...new Set(CATALOG_KINDS[kind].fields.flatMap((f) => (f.refKind ? [f.refKind] : [])))];
  const results = useQueries({
    queries: refKinds.map((refKind) => ({
      queryKey: ["catalog", refKind, "options"],
      queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${refKind}?active=true`),
    })),
  });
  return Object.fromEntries(refKinds.map((refKind, i) => [refKind, results[i].data ?? []]));
}

export function CatalogScreen({ kind }: { kind: CatalogKind }) {
  const config = CATALOG_KINDS[kind];
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canWrite = !!me?.permissions.includes(config.writeAction);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState<ActiveFilter>("true");
  const [editing, setEditing] = useState<CatalogItem | "new" | null>(null);
  const [deleting, setDeleting] = useState<CatalogItem | null>(null);
  const [notice, setNotice] = useState("");
  const q = useDebounce(search.trim());
  const refOptions = useRefOptions(kind);

  const list = useQuery({
    queryKey: ["catalog", kind, q, active],
    queryFn: () => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (active !== "all") params.set("active", active);
      return apiFetch<CatalogItem[]>(`/api/catalog/${kind}?${params}`);
    },
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["catalog", kind] });
  const toggle = useMutation({
    mutationFn: (item: CatalogItem) => apiFetch(`/api/catalog/${kind}/${item.id}`, { method: "PATCH", json: { active: !item.active } }),
    onSuccess: async (_, item) => {
      await refresh();
      setNotice(item.active ? "Đã ngừng dùng." : "Đã dùng lại.");
    },
    onError: (error) => setNotice(errorText(error)),
  });
  const remove = useMutation({
    mutationFn: (item: CatalogItem) => apiFetch(`/api/catalog/${kind}/${item.id}`, { method: "DELETE" }),
    onSuccess: async () => {
      setDeleting(null);
      await refresh();
      setNotice("Đã xoá.");
    },
  });

  const columns = useMemo(() => {
    const label = (name: string) => config.fields.find((f) => f.name === name)?.label ?? name;
    const cell = (item: CatalogItem, name: string) => {
      const field = config.fields.find((f) => f.name === name);
      const value = item[name];
      if (field?.type === "ref") {
        const target = (refOptions[field.refKind!] ?? []).find((o) => o.id === value);
        return target ? String(target.name ?? target.full_name) : value ? `#${value}` : "";
      }
      return Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value);
    };
    const mono = new Set(["code", "plate_no", "tax_code"]);
    return [
      ...config.columns.map((name) =>
        helper.accessor((row) => cell(row, name), {
          id: name,
          header: label(name),
          cell: (ctx) => <span className={cn(mono.has(name) && "font-mono text-xs")}>{ctx.getValue() as string}</span>,
        }),
      ),
      helper.accessor((row) => (row.active ? "Đang dùng" : "Ngừng dùng"), {
        id: "active",
        header: "Trạng thái",
        cell: (ctx) => <StatusBadge tone={ctx.row.original.active ? "success" : "neutral"}>{ctx.getValue()}</StatusBadge>,
      }),
      ...(canWrite
        ? [
            helper.display({
              id: "actions",
              header: () => <span className="sr-only">Thao tác</span>,
              cell: (ctx) => (
                <div className="flex justify-end">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label="Thao tác">
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setEditing(ctx.row.original)}>Sửa</DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => toggle.mutate(ctx.row.original)}>
                        {ctx.row.original.active ? "Ngừng dùng" : "Dùng lại"}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(ctx.row.original)}>Xoá</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ),
            }),
          ]
        : []),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, refOptions, canWrite]);

  const forbidden = list.error instanceof ApiError && list.error.status === 403;
  return (
    <div className="space-y-4">
      <nav aria-label="Loại danh mục" className="flex gap-1 border-b">
        {CATALOG_KIND_KEYS.map((key) => (
          <Link key={key} href={`/catalog/${key}`} aria-current={key === kind ? "page" : undefined}
            className={cn("-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors",
              key === kind ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {CATALOG_KINDS[key].label}
          </Link>
        ))}
      </nav>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Tìm kiếm" placeholder={config.searchHint} className="pl-8" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={active} onValueChange={(value) => setActive(value as ActiveFilter)}>
          <SelectTrigger aria-label="Lọc theo trạng thái" className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(FILTER_LABELS) as ActiveFilter[]).map((key) => (
              <SelectItem key={key} value={key}>{FILTER_LABELS[key]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p role="status" className="text-[13px] text-muted-foreground">{notice}</p>
        {canWrite && (
          <Button className="ml-auto" onClick={() => setEditing("new")}>
            <Plus />
            Thêm {config.singular}
          </Button>
        )}
      </div>
      {forbidden ? (
        <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">Bạn không có quyền xem trang này</p>
      ) : (
        <DataTable columns={columns} data={list.data ?? []} loading={list.isPending} error={list.error} onRetry={() => list.refetch()}
          filtered={!!q || active !== "true"} getRowId={(row) => String(row.id)}
          empty={{ none: { title: `Chưa có ${config.singular} nào`, hint: canWrite ? `Bấm "Thêm ${config.singular}" để tạo bản ghi đầu tiên.` : undefined },
            filtered: { title: "Không có kết quả khớp", hint: "Thử đổi từ khoá hoặc bộ lọc trạng thái." } }} />
      )}
      {editing && (
        <CatalogFormDialog kind={kind} config={config} item={editing === "new" ? undefined : editing}
          refOptions={refOptions} onClose={() => setEditing(null)} />
      )}
      <AlertDialog open={!!deleting} onOpenChange={(open) => { if (!open) { setDeleting(null); remove.reset(); } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá {config.singular} này?</AlertDialogTitle>
            <AlertDialogDescription>
              Chỉ xoá được khi chưa có dữ liệu nào tham chiếu tới. Nếu đang được dùng, hãy chọn &ldquo;Ngừng dùng&rdquo;.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {remove.error && (
            <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
              {errorText(remove.error)}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={remove.isPending}
              onClick={(event) => { event.preventDefault(); if (deleting) remove.mutate(deleting); }}>
              Xoá
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
