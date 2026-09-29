"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";
import {
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import type { ColumnDef, RowData } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  rowPaginationFeature,
  paginatedRowModel: createPaginatedRowModel(),
});
export const columnHelper = <T extends RowData>() => createColumnHelper<typeof features, T>();
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- cột accessor mỗi cột một kiểu giá trị riêng
export type DataColumn<T extends RowData> = ColumnDef<typeof features, T, any>;

const PAGE_SIZE = 50;
const SKELETON_ROWS = 8;

type Empty = { title: string; hint?: string };

type Props<T extends RowData> = {
  columns: DataColumn<T>[];
  data: T[];
  loading?: boolean;
  error?: { message: string } | null;
  onRetry?: () => void;
  /** Hiện khi không có dữ liệu nào (chưa từng có) và khi có bộ lọc mà không khớp dòng nào. */
  empty: { none: Empty; filtered: Empty };
  filtered?: boolean;
  getRowId?: (row: T) => string;
};

const NO_DATA: never[] = [];

/** Bảng dày dùng chung: hàng 40px, tiêu đề dính đầu, sắp xếp theo cột, phân trang 50 dòng. */
export function DataTable<T extends RowData>({ columns, data, loading, error, onRetry, empty, filtered, getRowId }: Props<T>) {
  const table = useTable({
    features,
    columns,
    data: data ?? (NO_DATA as T[]),
    getRowId,
    initialState: { pagination: { pageIndex: 0, pageSize: PAGE_SIZE } },
  });
  const rows = table.getRowModel().rows;
  const pageCount = table.getPageCount();
  const pageIndex = table.store.state.pagination.pageIndex;

  if (error) {
    return (
      <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border bg-card p-10 text-center">
        <TriangleAlert className="size-6 text-danger" aria-hidden />
        <p className="text-sm">{error.message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Thử lại
          </Button>
        )}
      </div>
    );
  }

  const message = filtered ? empty.filtered : empty.none;
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="max-h-[calc(100vh-15rem)] overflow-auto">
        <Table className="text-[13px]">
          <TableHeader className="sticky top-0 z-[1] bg-muted/90 backdrop-blur">
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id} className="h-9 hover:bg-transparent">
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  const sortable = header.column.getCanSort();
                  return (
                    <TableHead
                      key={header.id}
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                      className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
                    >
                      {header.isPlaceholder ? null : sortable ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 uppercase hover:text-foreground"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          <table.FlexRender header={header} />
                          {sorted === "asc" && <ArrowUp className="size-3" aria-hidden />}
                          {sorted === "desc" && <ArrowDown className="size-3" aria-hidden />}
                        </button>
                      ) : (
                        <table.FlexRender header={header} />
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading
              ? Array.from({ length: SKELETON_ROWS }, (_, i) => (
                  <TableRow key={i} className="h-10 hover:bg-transparent">
                    {columns.map((_, c) => (
                      <TableCell key={c}>
                        <Skeleton className="h-4 w-4/5" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : rows.map((row) => (
                  <TableRow key={row.id} className="h-10 hover:bg-accent/60">
                    {row.getAllCells().map((cell) => (
                      <TableCell key={cell.id} className={cn("py-0")}>
                        <table.FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
        {!loading && rows.length === 0 && (
          <div className="px-6 py-14 text-center">
            <p className="text-sm font-medium">{message.title}</p>
            {message.hint && <p className="mt-1 text-[13px] text-muted-foreground">{message.hint}</p>}
          </div>
        )}
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
          <span>
            Trang {pageIndex + 1} / {pageCount}
          </span>
          <div className="flex gap-1">
            <Button variant="outline" size="icon-xs" aria-label="Trang trước" disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}>
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="icon-xs" aria-label="Trang sau" disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}>
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
