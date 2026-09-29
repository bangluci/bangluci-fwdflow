"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { ErrorBanner } from "@/components/form-field";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { ShipmentDetail } from "@/lib/shipment-types";
import { STATUS_LABEL, type ShipmentStatus } from "@/lib/shipment-labels";

const label = (status: string) => STATUS_LABEL[status as ShipmentStatus] ?? status;
const MIN_REASON = 3;

/** Đúng một nút hành động kế tiếp ở đầu trang; các bước khác và "Huỷ lô" nằm trong menu. */
export function StatusActions({ shipment, canWrite }: { shipment: ShipmentDetail; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] });
    queryClient.invalidateQueries({ queryKey: ["shipments"] });
    queryClient.invalidateQueries({ queryKey: ["shipment-side", shipment.id] });
  };
  const move = useMutation({
    mutationFn: (to: string) => apiFetch(`/api/shipments/${shipment.id}/transition`, { method: "POST", json: { to_status: to } }),
    onSuccess: () => { setConfirm(null); refresh(); },
  });
  const cancel = useMutation({
    mutationFn: () => apiFetch(`/api/shipments/${shipment.id}/cancel`, { method: "POST", json: { reason: reason.trim() } }),
    onSuccess: () => { setCancelling(false); setReason(""); refresh(); },
  });

  const [next, ...others] = shipment.allowed_transitions;
  const closed = shipment.status === "COMPLETED" || shipment.status === "CANCELLED";
  if (!canWrite && !next) return null;
  return (
    <div className="flex items-center gap-2">
      {canWrite && next && (
        <div className="flex">
          <Button className={others.length ? "rounded-r-none" : ""} onClick={() => { move.reset(); setConfirm(next); }}>
            {label(next)}
            <ArrowRight />
          </Button>
          {others.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button className="rounded-l-none border-l border-primary-foreground/25 px-1.5" aria-label="Bước khác">
                  <ChevronDown />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {others.map((to) => (
                  <DropdownMenuItem key={to} onSelect={() => { move.reset(); setConfirm(to); }}>
                    Chuyển sang: {label(to)}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      )}
      {canWrite && !closed && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="icon" aria-label="Thao tác khác">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuSeparator className="hidden" />
            <DropdownMenuItem variant="destructive" onSelect={() => { cancel.reset(); setCancelling(true); }}>Huỷ lô</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Chuyển sang &ldquo;{confirm && label(confirm)}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "IN_TRANSIT" && shipment.in_transit_missing.length > 0
                ? "Còn thiếu thông tin bắt buộc, hệ thống sẽ từ chối. Bổ sung trước khi chuyển."
                : "Bước này được ghi vào nhật ký và không tự quay lại được."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorBanner error={move.error} />
          <AlertDialogFooter>
            <AlertDialogCancel>Để sau</AlertDialogCancel>
            <AlertDialogAction disabled={move.isPending} onClick={(e) => { e.preventDefault(); if (confirm) move.mutate(confirm); }}>
              {move.isPending ? "Đang chuyển…" : "Chuyển trạng thái"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={cancelling} onOpenChange={(open) => { if (!open) { setCancelling(false); setReason(""); } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Huỷ lô {shipment.code}</DialogTitle>
            <DialogDescription>Lô huỷ rồi không sửa được nữa. Nhập lý do để lưu vào nhật ký.</DialogDescription>
          </DialogHeader>
          <Textarea aria-label="Lý do huỷ" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ví dụ: khách huỷ đơn hàng" />
          <ErrorBanner error={cancel.error} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelling(false)}>Đóng</Button>
            <Button variant="destructive" disabled={reason.trim().length < MIN_REASON || cancel.isPending} onClick={() => cancel.mutate()}>
              Huỷ lô
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
