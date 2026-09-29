"use client";

import { formatDateTime } from "@/lib/format";
import { STATUS_LABEL, type ShipmentStatus } from "@/lib/shipment-labels";
import type { EventOut, ShipmentDetail } from "@/lib/shipment-types";
import { cn } from "@/lib/utils";

const MILESTONE_LABEL: Record<string, string> = { DISCHARGED: "Dỡ khỏi tàu", GATE_OUT_FULL: "Lấy cont ra khỏi cảng", EMPTY_RETURNED: "Trả vỏ rỗng" };
const label = (status: string | null) => (status ? STATUS_LABEL[status as ShipmentStatus] ?? status : "");

type Entry = EventOut & { scope: string; text: string };

function buildEntries(shipment: ShipmentDetail): Entry[] {
  const entries: Entry[] = [];
  for (const e of shipment.events) {
    entries.push({ ...e, scope: "Lô", text: e.kind === "TRANSITION" ? `${label(e.from_status) || "Tạo lô"} → ${label(e.to_status)}` : e.kind });
  }
  for (const c of shipment.containers) {
    for (const e of c.events) entries.push({ ...e, scope: c.container_no, text: MILESTONE_LABEL[e.kind] ?? e.kind });
  }
  return entries.sort((a, b) => (a.recorded_at < b.recorded_at ? -1 : a.recorded_at > b.recorded_at ? 1 : a.id - b.id));
}

/** Gộp event của lô và của từng container theo thời điểm ghi; event bị VOID bị gạch, RETIME nêu giờ cũ → giờ mới. */
export function TimelineTab({ shipment }: { shipment: ShipmentDetail }) {
  const entries = buildEntries(shipment);
  const voided = new Set(entries.filter((e) => e.kind === "VOID").map((e) => e.adjusts_event_id));
  return (
    <ol className="relative space-y-4 rounded-lg border bg-card p-5 pl-8 before:absolute before:top-6 before:bottom-6 before:left-[1.35rem] before:w-px before:bg-border">
      {entries.map((e) => {
        const target = e.adjusts_event_id ? entries.find((x) => x.id === e.adjusts_event_id && x.scope === e.scope) : undefined;
        const isVoided = voided.has(e.id) && e.kind !== "VOID" && e.kind !== "RETIME";
        return (
          <li key={`${e.scope}:${e.id}`} className="relative">
              <span className={cn("absolute top-1.5 -left-[1.4rem] size-2.5 rounded-full border-2 bg-card", e.kind === "VOID" ? "border-danger" : "border-primary")} aria-hidden />
              <p className={cn("text-sm", isVoided && "text-muted-foreground line-through")}>
                {e.kind === "RETIME" && target ? `Chỉnh giờ ${target.text}: ${formatDateTime(target.occurred_at)} → ${formatDateTime(e.occurred_at)}` : e.kind === "VOID" && target ? `Huỷ: ${target.text}` : e.text}
              </p>
              <p className="text-xs text-muted-foreground">
                {e.scope !== "Lô" && <span className="mr-2 rounded bg-muted px-1.5 py-0.5 font-mono">{e.scope}</span>}
                {formatDateTime(e.kind === "RETIME" ? e.recorded_at : e.occurred_at)}
                {e.actor_id == null ? " · hệ thống" : ""}
                {e.reason ? ` · ${e.reason}` : ""}
              </p>
          </li>
        );
      })}
      {entries.length === 0 && <li className="text-sm text-muted-foreground">Chưa có sự kiện nào</li>}
    </ol>
  );
}
