"use client";

import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { formatHsCode, type HsSuggestItem, type HsSuggestResult } from "@/lib/hs-code";
import { FALLBACK_PROVIDER_LABEL, useAiStatus } from "@/lib/use-ai-status";

const ERROR_TEXT: Record<string, string> = {
  RATE_LIMITED: "Bạn đã dùng hết lượt, thử lại sau",
  AI_DISABLED: "AI đang tắt, nhập mã tay",
};

function Item({ item, onPick }: { item: HsSuggestItem; onPick: () => void }) {
  return (
    <li className="space-y-1 rounded-md border bg-card p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-sm font-semibold">{formatHsCode(item.code)}</span>
            {item.needs_review && <StatusBadge tone="attention">Cần xem kỹ</StatusBadge>}
          </p>
          <p className="text-[13px]">{item.description_vi}</p>
        </div>
        <Button type="button" size="xs" variant="outline" onClick={onPick}>Chọn</Button>
      </div>
      {item.explanation && <p className="text-[13px] text-muted-foreground">{item.explanation}</p>}
      <p className="text-xs tabular-nums text-muted-foreground">
        Hạng tìm kiếm #{item.rank} · RRF {item.rrf_score.toFixed(4)} · cosine {item.cosine == null ? "—" : item.cosine.toFixed(2)}
      </p>
    </li>
  );
}

/** Gợi ý mã HS cho một mô tả hàng. Mọi chữ từ API render dạng văn bản thuần (React tự escape). */
export function HsSuggest({ description, onPick }: { description: string; onPick: (code: string, logId: number) => void }) {
  const suggest = useMutation({
    mutationFn: () => apiFetch<HsSuggestResult>("/api/hs/suggest", { method: "POST", json: { description: description.trim() } }),
  });
  const providerLabel = useAiStatus().data?.provider_label ?? FALLBACK_PROVIDER_LABEL;
  const result = suggest.data;
  const error = suggest.error;
  const errorMessage = error instanceof ApiError ? (ERROR_TEXT[error.code] ?? error.message) : error?.message;
  return (
    <div className="space-y-2">
      <Button type="button" size="sm" variant="outline" disabled={!description.trim() || suggest.isPending} onClick={() => suggest.mutate()}>
        <Sparkles />{suggest.isPending ? "Đang gợi ý…" : "Gợi ý mã HS"}
      </Button>
      <p className="text-xs text-muted-foreground">Mô tả hàng sẽ được gửi tới {providerLabel}</p>
      {errorMessage && <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">{errorMessage}</p>}
      {result?.degraded && <p role="status" className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">Tìm kiếm rút gọn: chưa dùng được mô hình ngữ nghĩa, kết quả chỉ dựa trên từ khoá.</p>}
      {result?.status === "INSUFFICIENT" && (
        <div role="status" className="rounded-md border bg-muted/50 px-3 py-2 text-[13px]">
          <p className="font-medium">Chưa đủ thông tin</p>
          {result.hint && <p className="text-muted-foreground">{result.hint}</p>}
        </div>
      )}
      {result?.status === "SEARCH_ONLY" && <p role="status" className="text-[13px] text-muted-foreground">AI không trả lời, đây là kết quả tìm kiếm.</p>}
      {result && result.items.length > 0 && (
        <ul aria-label="Mã HS gợi ý" className="space-y-2">
          {result.items.map((item) => <Item key={item.code} item={item} onPick={() => onPick(item.code, result.log_id)} />)}
        </ul>
      )}
    </div>
  );
}
