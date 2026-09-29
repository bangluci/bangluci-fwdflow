"use client";

import { useQuery } from "@tanstack/react-query";
import { Field } from "@/components/form-field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";

/** Các trường vận chuyển của lô (dùng chung cho tạo mới và sửa). Ngày và ô số giữ dạng chuỗi trong form. */
export type ShipmentFields = {
  carrier_id: string;
  pol_port_id: string;
  pod_port_id: string;
  dest_warehouse_id: string;
  mbl_no: string;
  hbl_no: string;
  vessel: string;
  voyage: string;
  etd: string;
  eta: string;
  claims_fta: boolean;
  do_no: string;
  do_valid_until: string;
  total_packages: string;
};

export const EMPTY_FIELDS: ShipmentFields = {
  carrier_id: "", pol_port_id: "", pod_port_id: "", dest_warehouse_id: "", mbl_no: "", hbl_no: "", vessel: "", voyage: "",
  etd: "", eta: "", claims_fta: false, do_no: "", do_valid_until: "", total_packages: "",
};

const ID_KEYS = ["carrier_id", "pol_port_id", "pod_port_id", "dest_warehouse_id"] as const;
const TEXT_KEYS = ["mbl_no", "hbl_no", "vessel", "voyage", "etd", "eta", "do_no", "do_valid_until"] as const;
const NONE = "__none__";

/** Form → body API. `forUpdate`: trường rỗng gửi `null` để xoá giá trị; tạo mới thì bỏ qua trường rỗng. */
export function fieldsToBody(form: ShipmentFields, forUpdate: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = { claims_fta: form.claims_fta };
  for (const key of ID_KEYS) if (form[key]) body[key] = Number(form[key]);
  else if (forUpdate) body[key] = null;
  for (const key of TEXT_KEYS) if (form[key].trim()) body[key] = form[key].trim();
  else if (forUpdate) body[key] = null;
  if (form.total_packages !== "") body.total_packages = Number(form.total_packages);
  else if (forUpdate) body.total_packages = null;
  return body;
}

export function detailToFields(detail: Record<string, unknown>): ShipmentFields {
  const str = (key: string) => (detail[key] == null ? "" : String(detail[key]));
  return {
    carrier_id: str("carrier_id"), pol_port_id: str("pol_port_id"), pod_port_id: str("pod_port_id"),
    dest_warehouse_id: str("dest_warehouse_id"), mbl_no: str("mbl_no"), hbl_no: str("hbl_no"), vessel: str("vessel"),
    voyage: str("voyage"), etd: str("etd"), eta: str("eta"), claims_fta: Boolean(detail.claims_fta), do_no: str("do_no"),
    do_valid_until: str("do_valid_until"), total_packages: str("total_packages"),
  };
}

function useOptions(kind: string) {
  return useQuery({ queryKey: ["catalog", kind, "options"], queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`) });
}

function Pick({ id, value, onChange, rows, label }: { id: string; value: string; onChange: (v: string) => void; rows: CatalogItem[] | undefined; label: (row: CatalogItem) => string }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>Chưa chọn</SelectItem>
        {(rows ?? []).map((row) => (
          <SelectItem key={row.id} value={String(row.id)}>
            {label(row)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

type Props = { form: ShipmentFields; onChange: (patch: Partial<ShipmentFields>) => void; idPrefix: string; disabled?: boolean };

export function ShipmentFormFields({ form, onChange, idPrefix, disabled }: Props) {
  const carriers = useOptions("carriers");
  const ports = useOptions("ports");
  const warehouses = useOptions("warehouses");
  const text = (key: keyof ShipmentFields) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ [key]: e.target.value });
  const id = (name: string) => `${idPrefix}-${name}`;
  const code = (r: CatalogItem) => `${r.code} · ${r.name}`;
  return (
    <fieldset disabled={disabled} className="grid gap-4 sm:grid-cols-3">
      <Field label="Hãng tàu" htmlFor={id("carrier")}><Pick id={id("carrier")} value={form.carrier_id} onChange={(v) => onChange({ carrier_id: v })} rows={carriers.data} label={code} /></Field>
      <Field label="Cảng xếp (POL)" htmlFor={id("pol")}><Pick id={id("pol")} value={form.pol_port_id} onChange={(v) => onChange({ pol_port_id: v })} rows={ports.data} label={code} /></Field>
      <Field label="Cảng dỡ (POD)" htmlFor={id("pod")}><Pick id={id("pod")} value={form.pod_port_id} onChange={(v) => onChange({ pod_port_id: v })} rows={ports.data} label={code} /></Field>
      <Field label="Số MBL" htmlFor={id("mbl")}><Input id={id("mbl")} value={form.mbl_no} onChange={text("mbl_no")} className="font-mono" /></Field>
      <Field label="Số HBL" htmlFor={id("hbl")}><Input id={id("hbl")} value={form.hbl_no} onChange={text("hbl_no")} className="font-mono" /></Field>
      <Field label="Kho đích" htmlFor={id("wh")}><Pick id={id("wh")} value={form.dest_warehouse_id} onChange={(v) => onChange({ dest_warehouse_id: v })} rows={warehouses.data} label={(r) => String(r.name)} /></Field>
      <Field label="Tàu" htmlFor={id("vessel")}><Input id={id("vessel")} value={form.vessel} onChange={text("vessel")} /></Field>
      <Field label="Chuyến" htmlFor={id("voyage")}><Input id={id("voyage")} value={form.voyage} onChange={text("voyage")} /></Field>
      <Field label="Số kiện" htmlFor={id("packages")}><Input id={id("packages")} type="number" min={0} value={form.total_packages} onChange={text("total_packages")} /></Field>
      <Field label="ETD" htmlFor={id("etd")}><Input id={id("etd")} type="date" value={form.etd} onChange={text("etd")} /></Field>
      <Field label="ETA" htmlFor={id("eta")}><Input id={id("eta")} type="date" value={form.eta} onChange={text("eta")} /></Field>
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={form.claims_fta} onChange={(e) => onChange({ claims_fta: e.target.checked })} />
        Hưởng ưu đãi FTA (cần C/O)
      </label>
      <Field label="Số D/O" htmlFor={id("do")}><Input id={id("do")} value={form.do_no} onChange={text("do_no")} className="font-mono" /></Field>
      <Field label="D/O có hiệu lực đến" htmlFor={id("dovalid")}><Input id={id("dovalid")} type="date" value={form.do_valid_until} onChange={text("do_valid_until")} /></Field>
    </fieldset>
  );
}
