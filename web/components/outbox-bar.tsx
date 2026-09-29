"use client";

import { CircleAlert, CircleCheck, CloudUpload, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { OutboxItem } from "@/lib/driver-outbox";
import { cn } from "@/lib/utils";

/** Thanh trạng thái gửi luôn hiện: có biểu tượng + chữ ("đã gửi hết / chờ gửi / lỗi"), màu chỉ là lớp thứ ba. */
export function OutboxBar({ items, sending, onFlush, onDiscard }: { items: OutboxItem[]; sending: boolean; onFlush: () => void; onDiscard: (id: string) => void }) {
  const pending = items.filter((i) => i.state === "pending");
  const failed = items.filter((i) => i.state === "failed");
  return (
    <div className="space-y-2" data-testid="outbox-bar">
      <div
        role="status"
        className={cn(
          "flex min-h-11 items-center gap-2 rounded-lg border px-3 text-sm",
          failed.length ? "border-danger/40 bg-danger-soft text-danger-ink" : pending.length ? "border-warning/40 bg-warning-soft text-warning-ink" : "bg-card text-muted-foreground",
        )}
      >
        {failed.length ? <CircleAlert className="size-4 shrink-0" aria-hidden /> : pending.length ? <CloudUpload className="size-4 shrink-0" aria-hidden /> : <CircleCheck className="size-4 shrink-0" aria-hidden />}
        <span className="flex-1">
          {failed.length ? `${failed.length} thao tác gửi lỗi` : pending.length ? `${pending.length} thao tác chưa gửi` : "Đã gửi hết"}
          {pending.length > 0 && failed.length > 0 ? ` · ${pending.length} chưa gửi` : ""}
        </span>
        {pending.length > 0 && (
          <Button size="sm" variant="outline" className="h-9" disabled={sending} onClick={onFlush}>
            <RefreshCw className={sending ? "animate-spin" : undefined} />
            Gửi lại
          </Button>
        )}
      </div>
      {failed.map((item) => (
        <div key={item.client_request_id} role="alert" className="space-y-1 rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm text-danger-ink">
          <p className="font-medium">{item.label}</p>
          <p>{item.error}</p>
          <Button size="sm" variant="outline" className="h-9" onClick={() => onDiscard(item.client_request_id)}>Bỏ thao tác này</Button>
        </div>
      ))}
    </div>
  );
}
