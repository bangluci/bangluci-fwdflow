"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { ErrorBanner } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { formatDate } from "@/lib/format";
import { DELIVERY_MODE_LABEL } from "@/lib/shipment-labels";
import type { ShipmentDetail } from "@/lib/shipment-types";
import { detailToFields, fieldsToBody, ShipmentFormFields, type ShipmentFields } from "../shipment-fields";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 min-h-5 text-sm">{children || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

function useName(kind: string, id: number | null) {
  const rows = useQuery({ queryKey: ["catalog", kind, "options"], queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`) });
  const row = rows.data?.find((r) => r.id === id);
  return row ? String(row.name ?? row.code) : id ? `#${id}` : "";
}

export function InfoTab({ shipment, canWrite }: { shipment: ShipmentDetail; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ShipmentFields>(() => detailToFields(shipment as unknown as Record<string, unknown>));
  const carrier = useName("carriers", shipment.carrier_id);
  const pol = useName("ports", shipment.pol_port_id);
  const pod = useName("ports", shipment.pod_port_id);
  const warehouse = useName("warehouses", shipment.dest_warehouse_id);
  const closed = shipment.status === "CANCELLED";

  const save = useMutation({
    mutationFn: () => apiFetch(`/api/shipments/${shipment.id}`, { method: "PATCH", json: { ...fieldsToBody(form, true), version: shipment.version } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] });
      queryClient.invalidateQueries({ queryKey: ["shipments"] });
      setEditing(false);
    },
  });
  const conflict = save.error instanceof ApiError && save.error.code === "VERSION_CONFLICT";
  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["shipment", shipment.id] });
    const fresh = queryClient.getQueryData<ShipmentDetail>(["shipment", shipment.id]);
    if (fresh) setForm(detailToFields(fresh as unknown as Record<string, unknown>));
    save.reset();
  };

  if (editing) {
    return (
      <div className="space-y-4 rounded-lg border bg-card p-5">
        {conflict ? (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
            <span>Dữ liệu đã thay đổi, tải lại để lấy bản mới nhất.</span>
            <Button size="sm" variant="outline" onClick={reload}>Tải lại</Button>
          </div>
        ) : (
          <ErrorBanner error={save.error} />
        )}
        <ShipmentFormFields form={form} onChange={(patch) => setForm((c) => ({ ...c, ...patch }))} idPrefix="e" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setEditing(false); save.reset(); }}>Huỷ</Button>
          <Button disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Đang lưu…" : "Lưu thay đổi"}</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-4 rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Thông tin lô</h2>
        {canWrite && !closed && (
          <Button variant="outline" size="sm" onClick={() => { setForm(detailToFields(shipment as unknown as Record<string, unknown>)); setEditing(true); }}>
            <Pencil />
            Sửa
          </Button>
        )}
      </div>
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
        <Row label="Khách hàng">{shipment.customer_name}</Row>
        <Row label="Loại / kiểu giao">{`${shipment.load_type} · ${DELIVERY_MODE_LABEL[shipment.delivery_mode]}`}</Row>
        <Row label="Số kiện">{shipment.total_packages?.toString()}</Row>
        <Row label="Hãng tàu">{carrier}</Row>
        <Row label="Tàu / chuyến">{[shipment.vessel, shipment.voyage].filter(Boolean).join(" / ")}</Row>
        <Row label="Kho đích">{warehouse}</Row>
        <Row label="Cảng xếp (POL)">{pol}</Row>
        <Row label="Cảng dỡ (POD)">{pod}</Row>
        <Row label="FTA">{shipment.claims_fta ? "Có (cần C/O)" : "Không"}</Row>
        <Row label="MBL"><span className="font-mono text-[13px]">{shipment.mbl_no}</span></Row>
        <Row label="HBL"><span className="font-mono text-[13px]">{shipment.hbl_no}</span></Row>
        <Row label="ETD → ETA">{[formatDate(shipment.etd), formatDate(shipment.eta)].filter(Boolean).join(" → ")}</Row>
        <Row label="Số D/O"><span className="font-mono text-[13px]">{shipment.do_no}</span></Row>
        <Row label="D/O có hiệu lực đến">{formatDate(shipment.do_valid_until)}</Row>
        <Row label="Cập nhật lần cuối">{formatDate(shipment.updated_at)}</Row>
      </dl>
    </div>
  );
}
