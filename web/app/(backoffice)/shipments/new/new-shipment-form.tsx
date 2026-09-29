"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { DELIVERY_MODE_LABEL } from "@/lib/shipment-labels";
import { useMe } from "@/lib/use-me";
import { EMPTY_FIELDS, fieldsToBody, ShipmentFormFields, type ShipmentFields } from "../shipment-fields";

type Head = { load_type: "FCL" | "LCL"; delivery_mode: "VIA_WAREHOUSE" | "CONTAINER_TO_DOOR"; customer_id: string; staff_id: string };
const NONE = "__none__";

export function NewShipmentForm() {
  const router = useRouter();
  const { data: me } = useMe();
  const [head, setHead] = useState<Head>({ load_type: "FCL", delivery_mode: "VIA_WAREHOUSE", customer_id: "", staff_id: "" });
  const [fields, setFields] = useState<ShipmentFields>(EMPTY_FIELDS);
  const [problem, setProblem] = useState("");
  const customers = useQuery({ queryKey: ["catalog", "customers", "options"], queryFn: () => apiFetch<CatalogItem[]>("/api/catalog/customers?active=true") });
  const staff = useQuery({
    queryKey: ["users", "staff-options"],
    queryFn: () => apiFetch<{ id: number; full_name: string; role: string }[]>("/api/users"),
    enabled: me?.role === "ADMIN",
  });

  const create = useMutation({
    mutationFn: () => {
      const body = { ...fieldsToBody(fields, false), load_type: head.load_type, delivery_mode: head.delivery_mode, customer_id: Number(head.customer_id) };
      if (head.staff_id) Object.assign(body, { staff_id: Number(head.staff_id) });
      return apiFetch<{ id: number }>("/api/shipments", { method: "POST", json: body });
    },
    onSuccess: (shipment) => router.push(`/shipments/${shipment.id}`),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!head.customer_id) return setProblem("Chọn khách hàng");
    if (fields.etd && fields.eta && fields.etd > fields.eta) return setProblem("ETD không được sau ETA");
    setProblem("");
    create.mutate();
  }

  const lcl = head.load_type === "LCL";
  return (
    <form onSubmit={submit} noValidate className="mx-auto max-w-4xl space-y-6">
      <ErrorBanner error={problem || create.error} />
      <section className="grid gap-4 rounded-lg border bg-card p-5 sm:grid-cols-3">
        <h2 className="text-sm font-semibold sm:col-span-3">Loại lô và khách hàng</h2>
        <Field label="Loại hàng" htmlFor="n-load">
          <Select value={head.load_type} onValueChange={(v) => setHead((c) => ({ ...c, load_type: v as Head["load_type"], delivery_mode: v === "LCL" ? "VIA_WAREHOUSE" : c.delivery_mode }))}>
            <SelectTrigger id="n-load" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="FCL">FCL (nguyên container)</SelectItem>
              <SelectItem value="LCL">LCL (hàng lẻ)</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Kiểu giao" htmlFor="n-mode" hint={lcl ? "Hàng lẻ luôn giao qua kho" : undefined}>
          <Select value={head.delivery_mode} disabled={lcl} onValueChange={(v) => setHead((c) => ({ ...c, delivery_mode: v as Head["delivery_mode"] }))}>
            <SelectTrigger id="n-mode" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(DELIVERY_MODE_LABEL).map(([key, label]) => (
                <SelectItem key={key} value={key}>{label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Khách hàng" htmlFor="n-customer" required>
          <Select value={head.customer_id || NONE} onValueChange={(v) => setHead((c) => ({ ...c, customer_id: v === NONE ? "" : v }))}>
            <SelectTrigger id="n-customer" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {!head.customer_id && <SelectItem value={NONE}>Chọn…</SelectItem>}
              {(customers.data ?? []).map((row) => (
                <SelectItem key={row.id} value={String(row.id)}>{String(row.name)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {me?.role === "ADMIN" && (
          <Field label="Nhân viên phụ trách" htmlFor="n-staff" hint="Bỏ trống thì là bạn">
            <Select value={head.staff_id || NONE} onValueChange={(v) => setHead((c) => ({ ...c, staff_id: v === NONE ? "" : v }))}>
              <SelectTrigger id="n-staff" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Tôi</SelectItem>
                {(staff.data ?? []).filter((u) => u.role === "DOCS" || u.role === "ADMIN").map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>{u.full_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
      </section>
      <section className="space-y-4 rounded-lg border bg-card p-5">
        <h2 className="text-sm font-semibold">Vận chuyển</h2>
        <ShipmentFormFields form={fields} onChange={(patch) => setFields((c) => ({ ...c, ...patch }))} idPrefix="n" />
      </section>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => router.push("/shipments")}>Huỷ</Button>
        <Button type="submit" disabled={create.isPending}>{create.isPending ? "Đang lưu…" : "Tạo lô"}</Button>
      </div>
    </form>
  );
}
