"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ShipmentStatusBadge } from "@/components/shipment-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, apiFetchPage } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { DELIVERY_MODE_LABEL, LAST_MILE_STATUS_LABEL } from "@/lib/shipment-labels";
import type { ShipmentDetail } from "@/lib/shipment-types";
import { useDebounce } from "@/lib/use-debounce";
import { useMe } from "@/lib/use-me";
import { useUrlFilters } from "@/lib/use-url-filters";
import type { ShipmentRow } from "../shipments/shipment-list";
import type { LastMileOrderRow, PoolMeta } from "./last-mile-types";
import { LotActions } from "./lot-actions";
import { OrdersTable } from "./orders-table";
import { SplitForm } from "./split-form";

const DEFAULTS = { shipment: "", date: "", driver: "", status: "", code: "" };
const ANY = "__any__";

function LotPicker({ onPick }: { onPick: (id: number) => void }) {
  const [search, setSearch] = useState("");
  const q = useDebounce(search.trim());
  const found = useQuery({
    queryKey: ["shipments", "lot-pick", q],
    queryFn: () => apiFetchPage<ShipmentRow>(`/api/shipments?q=${encodeURIComponent(q)}&limit=6&status=CLEARED&status=AT_WAREHOUSE&status=DELIVERING&status=COMPLETED`),
    enabled: q.length >= 3,
  });
  return (
    <div className="relative w-96">
      <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
      <Input aria-label="Chọn lô" placeholder="Chọn lô: mã lô, số container, MBL/HBL" className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} />
      {q.length >= 3 && (
        <ul className="absolute top-9 z-10 w-full space-y-0.5 rounded-md border bg-popover p-1 shadow-md">
          {(found.data?.data ?? []).map((s) => (
            <li key={s.id}>
              <button type="button" className="w-full rounded px-2 py-1.5 text-left text-[13px] hover:bg-accent" onClick={() => { setSearch(""); onPick(s.id); }}>
                <span className="font-mono font-semibold">{s.code}</span> · {s.customer_name} · {s.load_type}
              </button>
            </li>
          ))}
          {found.data?.data.length === 0 && <li className="px-2 py-1.5 text-[13px] text-muted-foreground">Không có lô nào khớp</li>}
        </ul>
      )}
    </div>
  );
}

export function LastMileBoard() {
  const { data: me } = useMe();
  const [filters, setFilters] = useUrlFilters(DEFAULTS);
  const canManage = !!me?.permissions.includes("transport.write");
  const canVoid = !!me?.permissions.includes("transport.void_event");
  const shipmentId = filters.shipment ? Number(filters.shipment) : null;
  const drivers = useQuery({ queryKey: ["catalog", "drivers", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/drivers?active=true") });
  const shipment = useQuery({ queryKey: ["shipment", shipmentId], queryFn: () => apiFetch<ShipmentDetail>(`/api/shipments/${shipmentId}`), enabled: shipmentId !== null });
  const orders = useQuery({
    queryKey: ["last-mile", "orders", filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.shipment) params.set("shipment_id", filters.shipment);
      if (filters.date) params.set("planned_date", filters.date);
      if (filters.driver) params.set("driver_id", filters.driver);
      if (filters.status) params.set("status", filters.status);
      if (filters.code) params.set("tracking_code", filters.code);
      const page = await apiFetchPage<LastMileOrderRow>(`/api/last-mile-orders?${params}`);
      // Khi lọc theo lô, `meta` là quỹ kiện chứ không phải phân trang.
      const meta = "packages_available" in page.meta ? (page.meta as unknown as PoolMeta) : null;
      return { rows: page.data, meta };
    },
  });
  const lot = shipment.data;
  const pool = orders.data?.meta;
  const delivered = (orders.data?.rows ?? []).filter((o) => o.status === "DELIVERED").reduce((sum, o) => sum + o.packages, 0);
  const canSplit = canManage && lot?.delivery_mode === "VIA_WAREHOUSE" && (lot.status === "AT_WAREHOUSE" || lot.status === "DELIVERING");
  const hasFilter = !!(filters.date || filters.driver || filters.status || filters.code);
  const select = (label: string, key: "driver" | "status", rows: { value: string; label: string }[], width: string) => (
    <Select value={filters[key] || ANY} onValueChange={(v) => setFilters({ [key]: v === ANY ? "" : v })}>
      <SelectTrigger aria-label={label} className={width}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>{label}: tất cả</SelectItem>
        {rows.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <LotPicker onPick={(id) => setFilters({ shipment: String(id) })} />
        <Input aria-label="Ngày giao" type="date" className="w-40" value={filters.date} onChange={(e) => setFilters({ date: e.target.value })} />
        {select("Tài xế", "driver", (drivers.data ?? []).map((d) => ({ value: String(d.id), label: String(d.full_name) })), "w-44")}
        {select("Trạng thái", "status", Object.entries(LAST_MILE_STATUS_LABEL).map(([value, label]) => ({ value, label })), "w-44")}
        <Input aria-label="Mã vận đơn" placeholder="Mã vận đơn" className="w-40 font-mono" value={filters.code} onChange={(e) => setFilters({ code: e.target.value })} />
        {hasFilter && <Button variant="ghost" size="sm" onClick={() => setFilters({ date: "", driver: "", status: "", code: "" })}><X />Bỏ lọc</Button>}
      </div>
      {lot && (
        <section className="space-y-3 rounded-lg border bg-card p-4">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Link href={`/shipments/${lot.id}`} className="font-mono text-lg font-semibold text-primary hover:underline">{lot.code}</Link>
            <ShipmentStatusBadge status={lot.status} />
            <span className="text-[13px] text-muted-foreground">{lot.customer_name} · {lot.load_type} · {DELIVERY_MODE_LABEL[lot.delivery_mode]}</span>
            <span className="text-[13px]">Tổng {lot.total_packages ?? 0} kiện{pool ? <> · còn <strong className="tabular-nums">{pool.packages_available}</strong> kiện chưa tách</> : null}</span>
            <div className="ml-auto flex items-center gap-2">
              {canManage && <LotActions shipment={lot} delivered={delivered} />}
              <Button variant="ghost" size="icon" aria-label="Bỏ chọn lô" onClick={() => setFilters({ shipment: "" })}><X /></Button>
            </div>
          </div>
          {lot.delivery_mode !== "VIA_WAREHOUSE" && <p className="text-[13px] text-muted-foreground">Lô giao tới cửa không tách đơn giao nội địa.</p>}
        </section>
      )}
      {lot && canSplit && pool && <SplitForm shipmentId={lot.id} available={pool.packages_available} />}
      <OrdersTable orders={orders.data?.rows ?? []} loading={orders.isPending} canManage={canManage} canVoid={canVoid} showShipment={!lot} />
      {orders.error && <p role="alert" className="text-[13px] text-destructive">{orders.error.message}</p>}
    </div>
  );
}
