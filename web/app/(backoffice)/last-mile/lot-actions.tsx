"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { compressImage } from "@/lib/compress-image";
import type { ShipmentDetail } from "@/lib/shipment-types";

const MIN_REASON = 5;

function PhotoDialog({ title, description, shipmentId, path, field, undelivered, onClose }: {
  title: string; description: string; shipmentId: number; path: "receive-at-warehouse" | "close"; field: "note" | "reason"; undelivered?: number; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: async () => {
      const body = new FormData();
      body.append("photo", await compressImage(file as File));
      body.append(field, text.trim());
      return apiFetch(`/api/shipments/${shipmentId}/${path}`, { method: "POST", body });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipment"] });
      queryClient.invalidateQueries({ queryKey: ["last-mile"] });
      onClose();
    },
  });
  const ready = file && (field === "note" || text.trim().length >= MIN_REASON);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {undelivered !== undefined && undelivered > 0 && (
            <p className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">Còn {undelivered} kiện chưa giao sẽ không được giao nữa khi đóng lô.</p>
          )}
          <Field label={field === "reason" ? "Lý do đóng lô" : "Ghi chú"} htmlFor="p-text" required={field === "reason"} hint={field === "reason" ? "5–500 ký tự" : undefined}>
            <Textarea id="p-text" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          <Field label={field === "reason" ? "Ảnh biên bản" : "Ảnh phiếu xuất kho CFS"} htmlFor="p-file" required hint="Ảnh được nén ở trình duyệt trước khi gửi.">
            <Input id="p-file" type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <ErrorBanner error={send.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!ready || send.isPending} onClick={() => send.mutate()}>{send.isPending ? "Đang gửi…" : "Xác nhận"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Nút hành động cấp lô: nhận hàng LCL về kho, đóng lô giao qua kho. */
export function LotActions({ shipment, delivered }: { shipment: ShipmentDetail; delivered: number }) {
  const [dialog, setDialog] = useState<"receive" | "close" | null>(null);
  const canReceive = shipment.load_type === "LCL" && shipment.status === "CLEARED";
  const canClose = shipment.delivery_mode === "VIA_WAREHOUSE" && (shipment.status === "AT_WAREHOUSE" || shipment.status === "DELIVERING");
  if (!canReceive && !canClose) return null;
  return (
    <>
      {canReceive && <Button variant="outline" onClick={() => setDialog("receive")}>Xác nhận nhận hàng tại kho</Button>}
      {canClose && <Button variant="outline" onClick={() => setDialog("close")}>Đóng lô</Button>}
      {dialog === "receive" && <PhotoDialog title="Nhận hàng LCL về kho" description="Hàng đã lấy khỏi kho CFS về kho công ty; lô sang trạng thái Đã về kho." shipmentId={shipment.id} path="receive-at-warehouse" field="note" onClose={() => setDialog(null)} />}
      {dialog === "close" && <PhotoDialog title={`Đóng lô ${shipment.code}`} description="Chỉ đóng được khi không còn đơn giao dở và (lô FCL) mọi container đã trả vỏ." shipmentId={shipment.id} path="close" field="reason" undelivered={Math.max(0, (shipment.total_packages ?? 0) - delivered)} onClose={() => setDialog(null)} />}
    </>
  );
}
