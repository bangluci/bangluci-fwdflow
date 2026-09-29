"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";
import { ErrorBanner, Field } from "@/components/form-field";
import { StatusBadge } from "@/components/status-badge";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { formatDate, formatMoney } from "@/lib/format";
import { FEE_TYPE_LABEL } from "@/lib/freetime";
import { validateTiersClient, type TierDraft } from "@/lib/freetime-tiers";
import { toMinorUnits } from "@/lib/money";
import { useMe } from "@/lib/use-me";

type Tier = { from_day: number; to_day: number | null; rate_amount: number; currency: string };
type Rule = { id: number; fee_type: keyof typeof FEE_TYPE_LABEL; free_days: number; tiers: Tier[] };
type Version = { carrier_id: number; carrier_name: string; port_id: number; port_code: string; container_type: string; effective_from: string; editable: boolean; rules: Rule[] };

const CONTAINER_TYPES = ["20GP", "40GP", "40HC", "45HC", "20RF", "40RF", "40RH"];
const ANY = "__any__";
const versionKey = (v: Version) => `${v.carrier_id}-${v.port_id}-${v.container_type}-${v.effective_from}`;

function useOptions(kind: string) {
  return useQuery({ queryKey: ["catalog", kind, "options"], queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`) });
}

type FeeForm = { free_days: string; currency: "VND" | "USD"; tiers: { to_day: string; rate: string }[] };
const emptyFee = (): FeeForm => ({ free_days: "", currency: "USD", tiers: [{ to_day: "", rate: "" }] });

/** Bậc i bắt đầu ở ngày (bậc trước kết thúc + 1); bậc đầu bắt đầu ở ngày free + 1. */
function draftTiers(fee: FeeForm): TierDraft[] {
  const free = Number(fee.free_days);
  return fee.tiers.map((row, index) => {
    const previous = index === 0 ? free : Number(fee.tiers[index - 1].to_day);
    return { from_day: previous + 1, to_day: row.to_day.trim() === "" ? null : Number(row.to_day), rate_amount: toMinorUnits(row.rate, fee.currency) ?? Number.NaN, currency: fee.currency };
  });
}

function FeeEditor({ title, fee, onChange, error }: { title: string; fee: FeeForm; onChange: (fee: FeeForm) => void; error?: string }) {
  const tiers = fee.free_days === "" ? [] : draftTiers(fee);
  const patchTier = (index: number, patch: Partial<FeeForm["tiers"][number]>) => onChange({ ...fee, tiers: fee.tiers.map((t, i) => (i === index ? { ...t, ...patch } : t)) });
  return (
    <fieldset className="space-y-2 rounded-lg border p-3">
      <legend className="px-1 text-[13px] font-semibold">{title}</legend>
      <div className="flex items-end gap-3">
        <Field label="Số ngày free" htmlFor={`f-${title}`}><Input id={`f-${title}`} type="number" min={0} max={365} className="w-28" value={fee.free_days} onChange={(e) => onChange({ ...fee, free_days: e.target.value })} /></Field>
        <Field label="Tiền tệ" htmlFor={`cur-${title}`}>
          <Select value={fee.currency} onValueChange={(v) => onChange({ ...fee, currency: v as "VND" | "USD" })}>
            <SelectTrigger id={`cur-${title}`} className="w-28"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="USD">USD</SelectItem><SelectItem value="VND">VND</SelectItem></SelectContent>
          </Select>
        </Field>
      </div>
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1 font-medium">Từ ngày</th><th className="font-medium">Đến ngày</th><th className="font-medium">Đơn giá / ngày ({fee.currency === "USD" ? "USD" : "đồng"})</th><th /></tr></thead>
        <tbody>
          {fee.tiers.map((row, index) => (
            <tr key={index}>
              <td className="w-24 py-1 tabular-nums">{fee.free_days === "" ? "—" : tiers[index]?.from_day}</td>
              <td className="w-32 pr-2"><Input aria-label={`Bậc ${index + 1} đến ngày`} type="number" min={1} placeholder="trở đi" value={row.to_day} onChange={(e) => patchTier(index, { to_day: e.target.value })} className="h-8" /></td>
              <td className="pr-2"><Input aria-label={`Bậc ${index + 1} đơn giá`} inputMode="decimal" value={row.rate} onChange={(e) => patchTier(index, { rate: e.target.value })} className="h-8" /></td>
              <td className="w-8">{fee.tiers.length > 1 && <Button type="button" variant="ghost" size="icon-sm" aria-label={`Xoá bậc ${index + 1}`} onClick={() => onChange({ ...fee, tiers: fee.tiers.filter((_, i) => i !== index) })}><Trash2 /></Button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button type="button" variant="outline" size="xs" onClick={() => onChange({ ...fee, tiers: [...fee.tiers, { to_day: "", rate: "" }] })}><Plus />Thêm bậc</Button>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </fieldset>
  );
}

function VersionDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const carriers = useOptions("carriers");
  const ports = useOptions("ports");
  const [head, setHead] = useState({ carrier_id: "", port_id: "", container_type: "40HC", effective_from: "", mode: "PAIR" });
  const [fees, setFees] = useState<Record<string, FeeForm>>({ DEM: emptyFee(), DET: emptyFee(), COMBINED: emptyFee() });
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState("");
  const kinds = head.mode === "PAIR" ? ["DEM", "DET"] : ["COMBINED"];
  const save = useMutation({
    mutationFn: () => apiFetch("/api/freetime/rules", {
      method: "POST",
      json: {
        carrier_id: Number(head.carrier_id), port_id: Number(head.port_id), container_type: head.container_type, effective_from: head.effective_from,
        rules: kinds.map((kind) => ({ fee_type: kind, free_days: Number(fees[kind].free_days), tiers: draftTiers(fees[kind]) })),
      },
    }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["freetime-rules"] }); onClose(); },
  });
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!head.carrier_id || !head.port_id || !head.effective_from) return setGeneral("Chọn hãng tàu, cảng và ngày hiệu lực");
    const found: Record<string, string> = {};
    for (const kind of kinds) {
      const free = fees[kind].free_days;
      if (free === "" || !Number.isInteger(Number(free)) || Number(free) < 0) { found[kind] = "Nhập số ngày free (số nguyên từ 0)"; continue; }
      const issue = validateTiersClient(Number(free), draftTiers(fees[kind]));
      if (issue) found[kind] = issue.message;
    }
    setProblems(found);
    setGeneral("");
    if (Object.keys(found).length === 0) save.mutate();
  }
  const pick = (key: "carrier_id" | "port_id", rows: CatalogItem[] | undefined, label: string) => (
    <Field label={label} htmlFor={`v-${key}`} required>
      <Select value={head[key] || ANY} onValueChange={(v) => setHead((c) => ({ ...c, [key]: v === ANY ? "" : v }))}>
        <SelectTrigger id={`v-${key}`} className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          {!head[key] && <SelectItem value={ANY}>Chọn…</SelectItem>}
          {(rows ?? []).map((r) => <SelectItem key={r.id} value={String(r.id)}>{`${r.code} · ${r.name}`}</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
  );
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Thêm phiên bản quy tắc</DialogTitle>
          <DialogDescription>Phiên bản đã có hiệu lực không sửa được: muốn đổi hãy thêm phiên bản với ngày hiệu lực mới.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {pick("carrier_id", carriers.data, "Hãng tàu")}
            {pick("port_id", ports.data, "Cảng dỡ")}
            <Field label="Loại container" htmlFor="v-type">
              <Select value={head.container_type} onValueChange={(v) => setHead((c) => ({ ...c, container_type: v }))}>
                <SelectTrigger id="v-type" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{CONTAINER_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Hiệu lực từ" htmlFor="v-from" required><Input id="v-from" type="date" value={head.effective_from} onChange={(e) => setHead((c) => ({ ...c, effective_from: e.target.value }))} /></Field>
          </div>
          <div className="flex gap-4 text-[13px]" role="radiogroup" aria-label="Chế độ tính">
            {[["PAIR", "DEM + DET riêng"], ["COMBINED", "Gộp DEM và DET"]].map(([value, label]) => (
              <label key={value} className="flex items-center gap-1.5"><input type="radio" name="mode" className="accent-[var(--primary)]" checked={head.mode === value} onChange={() => setHead((c) => ({ ...c, mode: value }))} />{label}</label>
            ))}
          </div>
          {kinds.map((kind) => <FeeEditor key={kind} title={FEE_TYPE_LABEL[kind as keyof typeof FEE_TYPE_LABEL]} fee={fees[kind]} onChange={(fee) => setFees((c) => ({ ...c, [kind]: fee }))} error={problems[kind]} />)}
          <ErrorBanner error={general || save.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Huỷ</Button>
            <Button type="submit" disabled={save.isPending}>{save.isPending ? "Đang lưu…" : "Lưu phiên bản"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RulesScreen() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canWrite = !!me?.permissions.includes("freetime.write");
  const [filter, setFilter] = useState({ carrier: "", port: "", type: "" });
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<Version | null>(null);
  const carriers = useOptions("carriers");
  const ports = useOptions("ports");
  const list = useQuery({
    queryKey: ["freetime-rules", filter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filter.carrier) params.set("carrier_id", filter.carrier);
      if (filter.port) params.set("port_id", filter.port);
      if (filter.type) params.set("container_type", filter.type);
      return apiFetch<Version[]>(`/api/freetime/rules?${params}`);
    },
  });
  const remove = useMutation({
    mutationFn: (v: Version) => apiFetch(`/api/freetime/rules/${v.rules[0].id}`, { method: "DELETE" }),
    onSuccess: async () => { setDeleting(null); await queryClient.invalidateQueries({ queryKey: ["freetime-rules"] }); },
  });
  const toggle = (key: string) => setOpen((c) => { const next = new Set(c); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const select = (label: string, key: "carrier" | "port" | "type", rows: { value: string; label: string }[], width: string) => (
    <Select value={filter[key] || ANY} onValueChange={(v) => setFilter((c) => ({ ...c, [key]: v === ANY ? "" : v }))}>
      <SelectTrigger aria-label={label} className={width}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ANY}>{label}: tất cả</SelectItem>
        {rows.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
  return (
    <div className="space-y-3">
      <Link href="/freetime" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" aria-hidden />Bảng free time</Link>
      <div className="flex flex-wrap items-center gap-2">
        {select("Hãng tàu", "carrier", (carriers.data ?? []).map((c) => ({ value: String(c.id), label: String(c.code) })), "w-40")}
        {select("Cảng", "port", (ports.data ?? []).map((p) => ({ value: String(p.id), label: String(p.code) })), "w-40")}
        {select("Loại cont", "type", CONTAINER_TYPES.map((t) => ({ value: t, label: t })), "w-40")}
        {canWrite && <Button className="ml-auto" onClick={() => setAdding(true)}><Plus />Thêm phiên bản</Button>}
      </div>
      <ErrorBanner error={remove.error} />
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table className="text-[13px]">
          <TableHeader className="bg-muted/90">
            <TableRow className="h-9">
              {["", "Hãng tàu", "Cảng", "Loại cont", "Hiệu lực từ", "Chế độ", "Số ngày free", "Số bậc", ""].map((h, i) => <TableHead key={i} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{h}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(list.data ?? []).map((v) => {
              const key = versionKey(v);
              const expanded = open.has(key);
              return (
                <Fragment key={key}>
                  <TableRow className="h-10">
                    <TableCell className="w-8 py-0"><Button variant="ghost" size="icon-sm" aria-label={expanded ? "Thu gọn" : "Xem bậc phí"} aria-expanded={expanded} onClick={() => toggle(key)}>{expanded ? <ChevronDown /> : <ChevronRight />}</Button></TableCell>
                    <TableCell className="font-medium">{v.carrier_name}</TableCell>
                    <TableCell className="font-mono text-xs">{v.port_code}</TableCell>
                    <TableCell>{v.container_type}</TableCell>
                    <TableCell>{formatDate(v.effective_from)}</TableCell>
                    <TableCell>{v.rules.some((r) => r.fee_type === "COMBINED") ? "Gộp" : "DEM + DET"}</TableCell>
                    <TableCell>{v.rules.map((r) => `${r.fee_type === "COMBINED" ? "D&D" : r.fee_type} ${r.free_days}`).join(" · ")}</TableCell>
                    <TableCell className="tabular-nums">{v.rules.reduce((n, r) => n + r.tiers.length, 0)}</TableCell>
                    <TableCell className="text-right">
                      {v.editable ? (
                        canWrite && <Button variant="ghost" size="xs" className="text-destructive" onClick={() => { remove.reset(); setDeleting(v); }}><Trash2 />Xoá</Button>
                      ) : (
                        <StatusBadge tone="neutral">Đã hiệu lực, thêm phiên bản mới để đổi</StatusBadge>
                      )}
                    </TableCell>
                  </TableRow>
                  {expanded && (
                    <TableRow className="bg-muted/30 hover:bg-muted/30">
                      <TableCell />
                      <TableCell colSpan={8} className="py-3">
                        <div className="grid gap-4 sm:grid-cols-2">
                          {v.rules.map((r) => (
                            <div key={r.id}>
                              <p className="mb-1 text-xs font-semibold">{FEE_TYPE_LABEL[r.fee_type]} · free {r.free_days} ngày</p>
                              <ul className="space-y-0.5 text-xs">
                                {r.tiers.map((t) => <li key={t.from_day}>Ngày {t.from_day}{t.to_day ? `–${t.to_day}` : " trở đi"}: {formatMoney(t.rate_amount, t.currency)} / ngày</li>)}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
        {list.data?.length === 0 && <p className="px-6 py-12 text-center text-sm text-muted-foreground">Chưa có quy tắc nào khớp. Đồng hồ free time cần quy tắc theo hãng tàu × cảng dỡ × loại container.</p>}
        {list.isPending && <p className="px-6 py-12 text-center text-sm text-muted-foreground">Đang tải…</p>}
      </div>
      {adding && <VersionDialog onClose={() => setAdding(false)} />}
      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá phiên bản quy tắc?</AlertDialogTitle>
            <AlertDialogDescription>{deleting && `${deleting.carrier_name} · ${deleting.port_code} · ${deleting.container_type}, hiệu lực từ ${formatDate(deleting.effective_from)}.`}</AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorBanner error={remove.error} />
          <AlertDialogFooter>
            <AlertDialogCancel>Giữ lại</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={remove.isPending} onClick={(e) => { e.preventDefault(); if (deleting) remove.mutate(deleting); }}>Xoá</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
