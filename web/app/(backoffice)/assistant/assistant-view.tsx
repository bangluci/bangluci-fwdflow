"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, Send, X } from "lucide-react";
import { useState } from "react";
import { AssistantChart } from "@/components/assistant-chart";
import { ErrorBanner } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { EXAMPLE_QUESTIONS, type AssistantAnswer } from "@/lib/assistant-types";
import { formatNumber } from "@/lib/format";
import { FALLBACK_PROVIDER_LABEL, useAiStatus } from "@/lib/use-ai-status";

const MAX_QUESTION = 500;
const MIN_QUESTION = 3;

const cell = (value: AssistantAnswer["rows"][number][number]) => (typeof value === "number" ? formatNumber(value) : value === null ? "" : String(value));

function Result({ data }: { data: AssistantAnswer }) {
  const [rating, setRating] = useState<boolean | null>(null);
  const rate = useMutation({
    mutationFn: (correct: boolean) => apiFetch(`/api/assistant/${data.log_id}/rating`, { method: "POST", json: { correct } }),
    onSuccess: (_, correct) => setRating(correct),
  });
  const hasTable = data.columns.length > 0 && data.rows.length > 0;
  return (
    <section aria-label="Kết quả" className="space-y-3">
      {data.message && <p role="status" className="rounded-md border bg-muted/50 px-3 py-2 text-[13px]">{data.message}</p>}
      {data.answer && (
        <div className="space-y-1 rounded-lg border bg-card p-4">
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Câu trả lời</h2>
          <p data-testid="assistant-answer" className="whitespace-pre-wrap text-[15px]">{data.answer}</p>
        </div>
      )}
      {data.answer_checked === false && <p className="text-[13px] text-warning-ink">Câu trả lời có số không khớp bảng, chỉ hiện bảng.</p>}
      {data.chart && hasTable && <AssistantChart chart={data.chart} columns={data.columns} rows={data.rows} />}
      {hasTable && (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table className="text-[13px]">
            <TableHeader className="bg-muted/90">
              <TableRow className="h-9">{data.columns.map((name) => <TableHead key={name} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{name}</TableHead>)}</TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row, i) => (
                <TableRow key={i} className="h-9">
                  {row.map((value, j) => <TableCell key={j} className={typeof value === "number" ? "text-right tabular-nums" : undefined}>{cell(value)}</TableCell>)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {data.sql && (
        <details className="text-[13px]">
          <summary className="cursor-pointer text-muted-foreground">Xem câu lệnh SQL đã chạy</summary>
          <pre className="mt-2 overflow-x-auto rounded-md border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap">{data.sql}</pre>
        </details>
      )}
      {(hasTable || data.answer) && (
        <div className="flex items-center gap-2 text-[13px]">
          <span className="text-muted-foreground">Kết quả này đúng không?</span>
          <Button size="sm" variant={rating === true ? "default" : "outline"} aria-pressed={rating === true} disabled={rate.isPending} onClick={() => rate.mutate(true)}><Check />Đúng</Button>
          <Button size="sm" variant={rating === false ? "default" : "outline"} aria-pressed={rating === false} disabled={rate.isPending} onClick={() => rate.mutate(false)}><X />Sai</Button>
          <ErrorBanner error={rate.error} />
        </div>
      )}
    </section>
  );
}

export function AssistantView() {
  const [question, setQuestion] = useState("");
  const providerLabel = useAiStatus().data?.provider_label ?? FALLBACK_PROVIDER_LABEL;
  const ask = useMutation({ mutationFn: (text: string) => apiFetch<AssistantAnswer>("/api/assistant/ask", { method: "POST", json: { question: text } }) });
  const trimmed = question.trim();
  const canAsk = trimmed.length >= MIN_QUESTION && !ask.isPending;
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (canAsk) ask.mutate(trimmed);
  };
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <form onSubmit={submit} className="space-y-2 rounded-lg border bg-card p-4">
        <label htmlFor="q" className="text-sm font-medium">Hỏi về dữ liệu lô hàng, container, xe, giao hàng{" "}<span className="font-normal text-muted-foreground">(bằng tiếng Việt)</span></label>
        <Textarea id="q" rows={2} maxLength={MAX_QUESTION} placeholder="Ví dụ: Tháng này có bao nhiêu đơn giao thất bại?" value={question} onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e); }} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Câu hỏi và tối đa 50 dòng kết quả được gửi tới {providerLabel}; chỉ dùng dữ liệu mô phỏng.</p>
          <div className="flex items-center gap-3">
            <span className="text-xs tabular-nums text-muted-foreground">{question.length}/{MAX_QUESTION}</span>
            <Button type="submit" disabled={!canAsk}><Send />{ask.isPending ? "Đang hỏi…" : "Hỏi"}</Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          {EXAMPLE_QUESTIONS.map((example) => (
            <button key={example} type="button" className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent" onClick={() => setQuestion(example)}>{example}</button>
          ))}
        </div>
      </form>
      <ErrorBanner error={ask.error} />
      {ask.isPending && <p role="status" className="text-sm text-muted-foreground">Đang tìm câu trả lời…</p>}
      {ask.data && !ask.isPending && <Result key={ask.data.log_id} data={ask.data} />}
    </div>
  );
}
