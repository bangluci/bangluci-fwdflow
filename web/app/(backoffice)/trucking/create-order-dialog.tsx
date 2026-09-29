"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, apiFetchPage } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { fromLocalInput } from "@/lib/format";
import type { ShipmentDetail } from "@/lib/shipment-types";
import { useDebounce } from "@/lib/use-debounce";
import type { ShipmentRow } from "../shipments/shipment-list";
import type { TruckingOrderRow } from "./week-calendar";

const catalog = (kind: string) => ({ queryKey: ["catalog", kind, "options"], queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`) });

export function CreateOrderDialog({ defaultDay, onClose }: { defaultDay: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useDebounce(search.trim());
  const [shipmentId, setShipmentId] = useState<number | null>(null);
  const [containerId, setContainerId] = useState("");
  const [kind, setKind] = useState<"PICKUP_FULL" | "RETURN_EMPTY">("PICKUP_FULL");
  const [trucker, setTrucker] = useState("");
  const [when, setWhen] = useState(`${defaultDay}T08:00`);
  const [pickupEdit, setPickupEdit] = useState<string>();
  const [dropEdit, setDropEdit] = useState<string>();
  const found = useQuery({
    queryKey: ["shipments", "pick", q],
    queryFn: () => apiFetchPage<ShipmentRow>(`/api/shipments?q=${encodeURIComponent(q)}&limit=6`),
    enabled: q.length >= 3 && shipmentId === null,
  });
  const detail = useQuery({ queryKey: ["shipment", shipmentId], queryFn: () => apiFetch<ShipmentDetail>(`/api/shipments/${shipmentId}`), enabled: shipmentId !== null });
  const truckers = useQuery(catalog("truckers"));
  const ports = useQuery(catalog("ports"));
  const warehouses = useQuery(catalog("warehouses"));
  const sibling = useQuery({
    queryKey: ["trucking-orders", "shipment", shipmentId],
    queryFn: () => apiFetch<TruckingOrderRow[]>(`/api/trucking-orders?shipment_id=${shipmentId}`),
    enabled: shipmentId !== null,
  });

  // Điền sẵn điểm lấy / trả (người dùng gõ đè thì dùng giá trị gõ): lấy hàng đầy từ cảng dỡ về kho đích;
  // trả vỏ bắt đầu ở nơi hàng đã được giao, điểm trả để trống.
  const shipment = detail.data;
  const delivered = sibling.data?.find((o) => o.container_id === Number(containerId) && o.kind === "PICKUP_FULL" && o.status === "COMPLETED");
  const port = ports.data?.find((p) => p.id === shipment?.pod_port_id);
  const warehouse = warehouses.data?.find((w) => w.id === shipment?.dest_warehouse_id);
  const pickup = pickupEdit ?? (kind === "PICKUP_FULL" ? (port ? String(port.name) : "") : (delivered?.drop_location ?? ""));
  const drop = dropEdit ?? (kind === "PICKUP_FULL" ? (warehouse ? String(warehouse.address) : "") : "");
  const changeKind = (next: typeof kind) => { setKind(next); setPickupEdit(undefined); setDropEdit(undefined); };

  const create = useMutation({
    mutationFn: () => apiFetch("/api/trucking-orders", {
      method: "POST",
      json: { container_id: Number(containerId), kind, trucker_id: Number(trucker), pickup_location: pickup, drop_location: drop, planned_at: fromLocalInput(when) },
    }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["trucking-orders"] }); onClose(); },
  });
  const ready = containerId && trucker && pickup.trim() && drop.trim() && when;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tạo lệnh xe</DialogTitle>
          <DialogDescription>Chỉ lô FCL còn hiệu lực. Trả vỏ rỗng chỉ tạo được sau khi lệnh lấy hàng đầy đã hoàn tất.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {shipmentId === null ? (
            <Field label="Tìm lô" htmlFor="c-search" hint="Gõ số container, mã lô hoặc số MBL/HBL (từ 3 ký tự)">
              <div className="relative">
                <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
                <Input id="c-search" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <ul className="mt-1 space-y-1">
                {(found.data?.data ?? []).filter((s) => s.load_type === "FCL").map((s) => (
                  <li key={s.id}>
                    <button type="button" className="w-full rounded-md border px-2.5 py-1.5 text-left text-[13px] hover:bg-accent" onClick={() => setShipmentId(s.id)}>
                      <span className="font-mono font-semibold">{s.code}</span> · {s.customer_name}
                    </button>
                  </li>
                ))}
              </ul>
            </Field>
          ) : (
            <p className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-[13px]">
              <span>Lô <span className="font-mono font-semibold">{detail.data?.code}</span> · {detail.data?.customer_name}</span>
              <Button variant="ghost" size="xs" onClick={() => { setShipmentId(null); setContainerId(""); }}>Đổi lô</Button>
            </p>
          )}
          {detail.data && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Container" htmlFor="c-cont" required>
                <Select value={containerId} onValueChange={setContainerId}>
                  <SelectTrigger id="c-cont" className="w-full"><SelectValue placeholder="Chọn container" /></SelectTrigger>
                  <SelectContent>{detail.data.containers.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.container_no}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="Loại lệnh" htmlFor="c-kind">
                <Select value={kind} onValueChange={(v) => changeKind(v as typeof kind)}>
                  <SelectTrigger id="c-kind" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="PICKUP_FULL">Lấy cont đầy</SelectItem><SelectItem value="RETURN_EMPTY">Trả vỏ rỗng</SelectItem></SelectContent>
                </Select>
              </Field>
              <Field label="Nhà xe" htmlFor="c-trucker" required>
                <Select value={trucker} onValueChange={setTrucker}>
                  <SelectTrigger id="c-trucker" className="w-full"><SelectValue placeholder="Chọn nhà xe" /></SelectTrigger>
                  <SelectContent>{(truckers.data ?? []).map((t) => <SelectItem key={t.id} value={String(t.id)}>{String(t.name)}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field label="Giờ dự kiến (giờ VN)" htmlFor="c-when" required><Input id="c-when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
              <Field label="Điểm lấy" htmlFor="c-pick" required><Input id="c-pick" value={pickup} onChange={(e) => setPickupEdit(e.target.value)} /></Field>
              <Field label={kind === "RETURN_EMPTY" ? "Depot trả rỗng (theo D/O / EIR)" : "Điểm trả"} htmlFor="c-drop" required><Input id="c-drop" value={drop} onChange={(e) => setDropEdit(e.target.value)} /></Field>
            </div>
          )}
          <ErrorBanner error={create.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!ready || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Đang tạo…" : "Tạo lệnh"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
