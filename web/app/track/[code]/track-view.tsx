"use client";

import { useQuery } from "@tanstack/react-query";
import { Package, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tracking = { tracking_code: string; status: string; status_label: string; updated_date: string; recipient_masked: string };

// Ba chặng người nhận quan tâm; FAILED / RETURNED / CANCELLED không nằm trên đường này nên chỉ hiện nhãn.
const STEPS: { key: string; label: string; statuses: string[] }[] = [
  { key: "wait", label: "Chờ giao", statuses: ["CREATED", "ASSIGNED"] },
  { key: "go", label: "Đang giao", statuses: ["PICKED_UP"] },
  { key: "done", label: "Đã giao", statuses: ["DELIVERED"] },
];

function Progress({ status }: { status: string }) {
  const current = STEPS.findIndex((s) => s.statuses.includes(status));
  if (current < 0) return null;
  return (
    <ol className="mt-5 flex items-center gap-2" aria-label="Tiến trình giao hàng">
      {STEPS.map((step, index) => (
        <li key={step.key} className="flex flex-1 flex-col items-center gap-1.5 text-center">
          <span className={cn("h-1.5 w-full rounded-full", index <= current ? "bg-primary" : "bg-border")} aria-hidden />
          <span className={cn("text-xs", index === current ? "font-semibold text-foreground" : "text-muted-foreground")}>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}

/** Trang tra cứu công khai: gọi API từ trình duyệt (HTML không chứa dữ liệu vận đơn), chỉ hiện trạng thái + tên đã che. */
export function TrackView({ code }: { code: string }) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const result = useQuery({
    queryKey: ["track", code],
    queryFn: () => apiFetch<Tracking>(`/api/public/track/${encodeURIComponent(code)}`),
    enabled: code !== "",
    retry: false,
    refetchOnWindowFocus: false,
  });
  const error = result.error instanceof ApiError ? result.error : null;
  const message = !error ? null : error.status === 429 ? "Bạn tra cứu quá nhiều lần, thử lại sau 1 phút" : error.status === 404 ? "Không tìm thấy vận đơn. Kiểm tra lại mã trên nhãn." : "Không tra cứu được lúc này, vui lòng thử lại.";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col gap-6 px-4 py-8">
      <header className="flex items-center gap-2 text-primary">
        <Package aria-hidden className="size-6" />
        <span className="text-lg font-semibold tracking-tight">FwdFlow</span>
      </header>
      <h1 className="text-2xl font-semibold leading-tight">Tra cứu vận đơn</h1>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) router.push(`/track/${encodeURIComponent(input.trim())}`);
        }}
      >
        <Input aria-label="Mã vận đơn" placeholder="Nhập mã vận đơn" autoCapitalize="characters" autoComplete="off" spellCheck={false} className="h-12 font-mono text-base uppercase" value={input} onChange={(e) => setInput(e.target.value)} />
        <Button type="submit" className="h-12 px-4" aria-label="Tra cứu"><Search /></Button>
      </form>
      {result.isPending && code !== "" && <p className="text-muted-foreground" role="status">Đang tra cứu…</p>}
      {message && <p role="alert" className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3 text-[15px] text-danger-ink">{message}</p>}
      {result.data && (
        <section className="rounded-2xl border bg-card p-5 shadow-xs">
          <p className="font-mono text-sm tracking-wide text-muted-foreground">{result.data.tracking_code}</p>
          <p className="mt-1 text-3xl font-semibold leading-tight">{result.data.status_label}</p>
          <p className="mt-2 text-[15px] text-muted-foreground">Cập nhật {formatDate(result.data.updated_date)}</p>
          <p className="mt-1 text-[15px]">Người nhận: <span className="font-medium">{result.data.recipient_masked}</span></p>
          <Progress status={result.data.status} />
        </section>
      )}
      <p className="mt-auto text-xs text-muted-foreground">Vì lý do riêng tư, trang này chỉ hiện trạng thái và tên người nhận đã được che bớt.</p>
    </main>
  );
}
