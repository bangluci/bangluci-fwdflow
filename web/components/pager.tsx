import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PageMeta } from "@/lib/api";

/** Phân trang phía server: dùng `meta` của envelope. */
export function Pager({ meta, onPage }: { meta: PageMeta | undefined; onPage: (page: number) => void }) {
  if (!meta || meta.total <= meta.limit) {
    return meta ? <p className="px-1 text-[13px] text-muted-foreground">{meta.total} dòng</p> : null;
  }
  const pages = Math.ceil(meta.total / meta.limit);
  const first = (meta.page - 1) * meta.limit + 1;
  const last = Math.min(meta.page * meta.limit, meta.total);
  return (
    <div className="flex items-center justify-between px-1 text-[13px] text-muted-foreground">
      <span>
        {first}–{last} / {meta.total} dòng
      </span>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" aria-label="Trang trước" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>
          <ChevronLeft />
        </Button>
        <span className="px-2">
          Trang {meta.page} / {pages}
        </span>
        <Button variant="outline" size="icon-sm" aria-label="Trang sau" disabled={meta.page >= pages} onClick={() => onPage(meta.page + 1)}>
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
