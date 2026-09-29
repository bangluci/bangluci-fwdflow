"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Camera, CircleCheck, MapPin, Phone } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { OutboxBar } from "@/components/outbox-bar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { compressImage } from "@/lib/compress-image";
import { addItem, listItems, type OutboxItem } from "@/lib/driver-outbox";
import type { DriverAction, DriverTask } from "@/lib/driver-types";
import { formatTime } from "@/lib/format";
import { useOutbox } from "@/lib/use-outbox";

const FAIL_REASONS = ["Không liên lạc được người nhận", "Người nhận hẹn lại", "Sai địa chỉ", "Người nhận từ chối nhận", "Khác"];
const OTHER = "Khác";
const GEO_TIMEOUT_MS = 8000;

type Position = { lat: number; lng: number } | null;

/** Vị trí lúc bấm thao tác: từ chối quyền, hết giờ hay tắt GPS đều trả `null` (vẫn cập nhật được, ghi "Chưa có vị trí"). */
function readPosition(): Promise<Position> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: Number(p.coords.latitude.toFixed(6)), lng: Number(p.coords.longitude.toFixed(6)) }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: GEO_TIMEOUT_MS, maximumAge: 30_000 },
    );
  });
}

type Draft = { action: DriverAction; requestId: string; photo: File | null; photoUrl: string | null; signer: string; reasonChoice: string; reasonText: string; position: Position | undefined };

export function TaskScreen({ kind, id }: { kind: "trucking" | "last-mile"; id: number }) {
  const outbox = useOutbox();
  const tasks = useQuery({ queryKey: ["driver-tasks"], queryFn: () => apiFetch<DriverTask[]>("/api/driver/tasks") });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [step, setStep] = useState<"form" | "confirm" | "done">("form");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState("");

  const task = tasks.data?.find((t) => t.id === id && (kind === "trucking" ? t.kind === "TRUCKING" : t.kind === "LAST_MILE"));
  if (tasks.isPending) return <p className="py-10 text-center text-muted-foreground">Đang tải…</p>;
  if (!task) {
    return (
      <div className="space-y-4 py-10 text-center">
        <p>{step === "done" ? "Đã xong việc này." : "Không tìm thấy việc này (đã xong hoặc không còn phân cho bạn)."}</p>
        <Button asChild size="lg" className="h-14 text-base"><Link href="/driver">Về danh sách việc</Link></Button>
      </div>
    );
  }

  const requires = (name: "photo" | "signer_name" | "reason") => draft?.action.requires.includes(name) ?? false;
  const reason = draft ? (draft.reasonChoice === OTHER || task.kind === "TRUCKING" ? draft.reasonText.trim() : draft.reasonChoice) : "";
  const missing = draft ? [requires("photo") && !draft.photo && "ảnh", requires("signer_name") && !draft.signer.trim() && "tên người ký nhận", requires("reason") && !reason && "lý do"].filter(Boolean) : [];

  async function begin(action: DriverAction) {
    setStep("form");
    setDraft({ action, requestId: crypto.randomUUID(), photo: null, photoUrl: null, signer: "", reasonChoice: "", reasonText: "", position: undefined });
    setBusy("Đang lấy vị trí…");
    const position = await readPosition();
    setDraft((d) => (d && d.action === action ? { ...d, position } : d));
    setBusy("");
  }

  async function pickPhoto(file: File | undefined) {
    if (!file) return;
    setBusy("Đang nén ảnh…");
    try {
      const compressed = await compressImage(file);
      setDraft((d) => (d ? { ...d, photo: compressed, photoUrl: URL.createObjectURL(compressed) } : d));
    } finally {
      setBusy("");
    }
  }

  async function submit() {
    if (!draft || !task) return;
    const fields: Record<string, string> = { device_time: new Date().toISOString() };
    if (draft.position) { fields.lat = String(draft.position.lat); fields.lng = String(draft.position.lng); }
    if (requires("signer_name") || draft.signer.trim()) fields.signer_name = draft.signer.trim();
    if (reason) fields.reason = reason;
    const item: OutboxItem = { client_request_id: draft.requestId, action: draft.action.action, target_id: task.id, label: `${draft.action.label} (${task.kind === "TRUCKING" ? task.container_no : task.tracking_code})`, created_at: new Date().toISOString(), fields, photo: draft.photo, state: "pending" };
    setBusy("Đang gửi…");
    await addItem(item); // lưu vào máy trước, rồi mới gửi
    await outbox.flush();
    await outbox.refresh();
    setBusy("");
    const left = (await listItems()).find((i) => i.client_request_id === draft.requestId);
    setResult(left ? (left.state === "failed" ? `Không gửi được: ${left.error}` : "Chưa gửi được, đã lưu trong máy. Sẽ tự gửi lại khi có mạng.") : "Đã gửi");
    setStep("done");
  }

  return (
    <div className="space-y-4 pb-28">
      <Link href="/driver" className="inline-flex h-11 items-center gap-1 text-[15px] text-muted-foreground"><ArrowLeft className="size-4" aria-hidden />Việc hôm nay</Link>
      <section className="space-y-2 rounded-xl border bg-card p-4">
        {task.kind === "TRUCKING" ? (
          <>
            <div className="flex justify-between"><h1 className="text-xl font-semibold">{task.title}</h1><p className="text-xl font-semibold tabular-nums">{formatTime(task.planned_at)}</p></div>
            <p className="font-mono text-lg font-semibold">{task.container_no}</p>
            <p className="text-[15px] text-muted-foreground">{task.container_type}{task.seal_no ? ` · seal ${task.seal_no}` : ""} · lô {task.shipment_code}</p>
            <p className="text-[15px]">{task.pickup_location} → {task.drop_location}</p>
          </>
        ) : (
          <>
            <div className="flex justify-between"><h1 className="text-xl font-semibold">Giao hàng</h1><p className="font-mono text-sm font-semibold">{task.tracking_code}</p></div>
            <p className="text-lg font-medium">{task.recipient_name} · {task.packages} kiện</p>
            <p className="text-[15px] text-muted-foreground">{task.address}</p>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Button asChild variant="outline" className="h-12 text-base"><a href={`tel:${task.recipient_phone}`}><Phone />Gọi</a></Button>
              <Button asChild variant="outline" className="h-12 text-base"><a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(task.address)}`} target="_blank" rel="noreferrer"><MapPin />Chỉ đường</a></Button>
            </div>
          </>
        )}
      </section>

      {step === "done" && (
        <section role="status" className="space-y-3 rounded-xl border bg-card p-5 text-center">
          <CircleCheck className="mx-auto size-10 text-success" aria-hidden />
          <p className="text-lg font-semibold">{result}</p>
          <Button asChild size="lg" className="h-14 w-full text-base"><Link href="/driver">Về danh sách việc</Link></Button>
        </section>
      )}

      {step !== "done" && !draft && (
        <div className="space-y-3">
          {task.actions.length === 0 && <p className="text-muted-foreground">Không có thao tác nào ở trạng thái này.</p>}
          {task.actions.map((action) => (
            <Button key={action.action} size="lg" className="h-16 w-full text-lg" onClick={() => begin(action)}>{action.label}</Button>
          ))}
        </div>
      )}

      {step === "form" && draft && (
        <section className="space-y-4 rounded-xl border bg-card p-4">
          <h2 className="text-lg font-semibold">{draft.action.label}</h2>
          {requires("photo") && (
            <div className="space-y-2">
              <p className="text-[15px] font-medium">Ảnh bằng chứng *</p>
              <label className="flex h-14 cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed text-base font-medium active:bg-accent">
                <Camera aria-hidden />
                {draft.photo ? "Chụp lại" : "Chụp ảnh"}
                <input aria-label="Chụp ảnh" type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => pickPhoto(e.target.files?.[0])} />
              </label>
              {draft.photoUrl && (
                // eslint-disable-next-line @next/next/no-img-element -- ảnh xem trước từ blob cục bộ
                <img src={draft.photoUrl} alt="Ảnh đã chụp" className="max-h-56 w-full rounded-lg border object-contain" />
              )}
            </div>
          )}
          {requires("signer_name") && (
            <div className="space-y-2">
              <label htmlFor="signer" className="text-[15px] font-medium">Người ký nhận *</label>
              <Input id="signer" className="h-12 text-base" value={draft.signer} onChange={(e) => setDraft({ ...draft, signer: e.target.value })} />
            </div>
          )}
          {requires("reason") && (
            <div className="space-y-2">
              <p className="text-[15px] font-medium">Lý do *</p>
              {task.kind === "LAST_MILE" ? (
                <div className="grid gap-2" role="radiogroup" aria-label="Lý do">
                  {FAIL_REASONS.map((r) => (
                    <label key={r} className="flex min-h-12 items-center gap-3 rounded-lg border px-3 text-base has-[:checked]:border-primary has-[:checked]:bg-accent">
                      <input type="radio" name="reason" className="size-5 accent-[var(--primary)]" checked={draft.reasonChoice === r} onChange={() => setDraft({ ...draft, reasonChoice: r })} />
                      {r}
                    </label>
                  ))}
                  {draft.reasonChoice === OTHER && <Textarea aria-label="Lý do khác" className="text-base" rows={2} value={draft.reasonText} onChange={(e) => setDraft({ ...draft, reasonText: e.target.value })} />}
                </div>
              ) : (
                <Textarea aria-label="Lý do" className="text-base" rows={2} value={draft.reasonText} onChange={(e) => setDraft({ ...draft, reasonText: e.target.value })} />
              )}
            </div>
          )}
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><MapPin className="size-4" aria-hidden />{draft.position === undefined ? "Đang lấy vị trí…" : draft.position ? "Đã có vị trí" : "Chưa có vị trí (vẫn cập nhật được)"}</p>
          {busy && <p role="status" className="text-sm text-muted-foreground">{busy}</p>}
          {missing.length > 0 && <p className="text-sm text-warning-ink">Còn thiếu: {missing.join(", ")}</p>}
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" className="h-14 text-base" onClick={() => setDraft(null)}>Huỷ</Button>
            <Button className="h-14 text-base" disabled={missing.length > 0 || !!busy} onClick={() => setStep("confirm")}>Tiếp tục</Button>
          </div>
        </section>
      )}

      {step === "confirm" && draft && (
        <section className="space-y-4 rounded-xl border-2 border-primary bg-card p-4">
          <h2 className="text-lg font-semibold">Xác nhận: {draft.action.label}</h2>
          <ul className="space-y-1 text-[15px]">
            <li>{task.kind === "TRUCKING" ? `Container ${task.container_no}` : `Đơn ${task.tracking_code} · ${task.recipient_name}`}</li>
            {draft.photo && <li>Ảnh: đã chụp ({Math.round(draft.photo.size / 1024)} KB)</li>}
            {draft.signer.trim() && <li>Người ký: {draft.signer.trim()}</li>}
            {reason && <li>Lý do: {reason}</li>}
            <li>Vị trí: {draft.position ? "đã ghi" : "chưa có"}</li>
          </ul>
          <p className="text-sm text-muted-foreground">Bước này không hoàn lại được.</p>
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" className="h-14 text-base" disabled={!!busy} onClick={() => setStep("form")}>Quay lại</Button>
            <Button className="h-14 text-base" disabled={!!busy} onClick={submit}>{busy || "Xác nhận"}</Button>
          </div>
        </section>
      )}

      <div className="fixed inset-x-0 bottom-0 mx-auto max-w-md border-t bg-background/95 p-3 backdrop-blur">
        <OutboxBar items={outbox.items} sending={outbox.sending} onFlush={outbox.flush} onDiscard={outbox.discard} />
      </div>
    </div>
  );
}
