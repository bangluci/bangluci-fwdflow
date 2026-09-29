"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, TriangleAlert, ZoomIn, ZoomOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ErrorBanner } from "@/components/form-field";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { EXTRACTION_STATUS_LABEL, FIELDS_BY_TYPE, type FieldDef, type Issue } from "@/lib/extraction-fields";
import { DOC_TYPE_LABEL } from "@/lib/shipment-labels";
import { cn } from "@/lib/utils";

type Extraction = {
  id: number;
  shipment_id: number;
  status: string;
  doc_type: string;
  detected_doc_type: string | null;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  result: Record<string, unknown> | null;
  field_issues: Issue[] | null;
  suspicious_content: boolean;
  suspicious_note: string | null;
  manual_check_done: boolean;
  version: number;
  document: { id: number; mime: string; pages: number; page_count_rendered: number; original_name: string | null };
  current: Record<string, unknown>;
};

const POLL_MS = 3000;
const MIN_REASON = 5;
const show = (value: unknown) => (value === null || value === undefined || value === "" ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value));
const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));

type Edits = Record<string, string>;
type Choices = Record<string, "old" | "new" | undefined>;

function CellInput({ value, onChange, issue, label, risky }: { value: string; onChange: (v: string) => void; issue?: Issue; label: string; risky?: boolean }) {
  return (
    <div className="space-y-0.5">
      <Input
        aria-label={label}
        aria-invalid={issue?.level === "BLOCK"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn("h-8 text-[13px]", risky && "font-mono", issue?.level === "BLOCK" && "border-danger ring-1 ring-danger/30", issue?.level === "WARN" && "border-warning")}
      />
      {issue && <p className={cn("text-[11px]", issue.level === "BLOCK" ? "text-danger-ink" : "text-warning-ink")}>{issue.message}</p>}
    </div>
  );
}

export function ReviewScreen({ id }: { id: number }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [zoom, setZoom] = useState(100);
  const [edits, setEdits] = useState<Edits>({});
  const [choices, setChoices] = useState<Choices>({});
  const [manualCheck, setManualCheck] = useState(false);
  const [confirmType, setConfirmType] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  const query = useQuery({
    queryKey: ["extraction", id],
    queryFn: () => apiFetch<Extraction>(`/api/extractions/${id}`),
    refetchInterval: (q) => (q.state.data && ["PENDING", "PROCESSING"].includes(q.state.data.status) ? POLL_MS : false),
  });
  const data = query.data;
  const issues = useMemo(() => {
    const map = new Map<string, Issue>();
    for (const issue of data?.field_issues ?? []) if (!map.has(issue.path) || issue.level === "BLOCK") map.set(issue.path, issue);
    return map;
  }, [data?.field_issues]);

  const approve = useMutation({
    mutationFn: () => {
      const fields: Record<string, { value: unknown; use?: "old" | "new" }> = {};
      const result = data!.result as Record<string, unknown>;
      const value = (path: string, original: unknown, kind?: string) => {
        const edited = edits[path];
        if (edited === undefined) return original;
        return edited === "" ? null : kind === "number" && !Number.isNaN(Number(edited)) ? Number(edited) : edited;
      };
      const defs = FIELDS_BY_TYPE[data!.doc_type];
      for (const def of defs.scalars) {
        const path = `/${def.name}`;
        if (edits[path] !== undefined || choices[path]) fields[path] = { value: value(path, result[def.name], def.kind), ...(choices[path] ? { use: choices[path] } : {}) };
      }
      for (const list of defs.lists) {
        (result[list.name] as Record<string, unknown>[] | undefined)?.forEach((row, index) => {
          const path = `/${list.name}/${index}`;
          const changed = list.columns.filter((c) => edits[`${path}/${c.name}`] !== undefined);
          if (changed.length || choices[path]) {
            fields[path] = { value: Object.fromEntries(changed.map((c) => [c.name, value(`${path}/${c.name}`, row[c.name], c.kind)])), ...(choices[path] ? { use: choices[path] } : {}) };
          }
        });
      }
      return apiFetch(`/api/extractions/${id}/approve`, { method: "POST", json: { version: data!.version, fields, manual_check_done: manualCheck, confirm_doc_type_mismatch: confirmType } });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["extraction", id] });
      queryClient.invalidateQueries({ queryKey: ["shipment"] });
      queryClient.invalidateQueries({ queryKey: ["extractions"] });
      router.push(`/shipments/${data!.shipment_id}`);
    },
  });
  const reject = useMutation({
    mutationFn: () => apiFetch(`/api/extractions/${id}/reject`, { method: "POST", json: { reason: reason.trim() } }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["extractions"] }); router.push(`/shipments/${data!.shipment_id}`); },
  });
  const retry = useMutation({
    mutationFn: () => apiFetch(`/api/extractions/${id}/retry`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["extraction", id] }),
  });

  if (query.error instanceof ApiError && query.error.status === 404) return <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">Không tìm thấy bản trích xuất</p>;
  if (query.error) return <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">{query.error.message}</p>;
  if (!data) return <p className="text-muted-foreground">Đang tải…</p>;

  const shipmentLink = <Link href={`/shipments/${data.shipment_id}`} className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" aria-hidden />Về lô</Link>;
  const title = <h2 className="text-lg font-semibold">Duyệt kết quả AI · {DOC_TYPE_LABEL[data.doc_type] ?? data.doc_type} <StatusBadge tone={data.status === "FAILED" ? "danger" : data.status === "REVIEW" ? "attention" : "neutral"} icon={undefined}>{EXTRACTION_STATUS_LABEL[data.status] ?? data.status}</StatusBadge></h2>;

  if (data.status === "PENDING" || data.status === "PROCESSING") {
    return (
      <div className="mx-auto max-w-lg space-y-4 pt-8 text-center">
        <div className="text-left">{shipmentLink}</div>
        <p role="status" className="text-base font-medium">Đang đọc chứng từ…</p>
        <p className="text-[13px] text-muted-foreground">{data.status === "PENDING" ? "Đã xếp hàng, chờ tới lượt." : "Đang đọc ảnh và kiểm tra các trường."} Trang tự cập nhật, bạn có thể quay lại sau.</p>
      </div>
    );
  }
  if (data.status === "FAILED") {
    return (
      <div className="mx-auto max-w-lg space-y-4 pt-8">
        {shipmentLink}
        {title}
        <ErrorBanner error={data.error_message ?? "AI không đọc được chứng từ này"} />
        <ErrorBanner error={retry.error} />
        <div className="flex gap-2">
          <Button disabled={retry.isPending} onClick={() => retry.mutate()}>Thử lại</Button>
          <Button variant="outline" asChild><Link href={`/shipments/${data.shipment_id}`}>Nhập tay</Link></Button>
        </div>
      </div>
    );
  }
  const result = data.result ?? {};
  const defs = FIELDS_BY_TYPE[data.doc_type];
  const readOnly = data.status !== "REVIEW";
  const edited = (path: string) => edits[path] !== undefined;
  const issueOf = (path: string) => (edited(path) && issues.get(path)?.level === "BLOCK" ? undefined : issues.get(path));
  const valueOf = (path: string, original: unknown) => (edits[path] !== undefined ? edits[path] : text(original));
  const blocking = [...issues.values()].filter((i) => i.level === "BLOCK" && !edited(i.path));
  // Trường có giá trị hiện tại khác giá trị AI: bắt buộc chọn giữ cũ hay dùng mới, không chọn sẵn.
  const conflicts = Object.entries(data.current).filter(([path, current]) => {
    if (current === null || current === undefined) return false;
    const [, name, index] = path.split("/");
    const ai = index === undefined ? result[name] : (result[name] as unknown[] | undefined)?.[Number(index)];
    if (typeof current === "object") return JSON.stringify(current) !== JSON.stringify(ai) && index !== undefined && Object.entries(current as Record<string, unknown>).some(([k, v]) => text(v) !== text((ai as Record<string, unknown> | undefined)?.[k]));
    return text(current) !== text(ai);
  }).map(([path]) => path);
  const unchosen = conflicts.filter((p) => !choices[p]);
  const mismatch = !!data.detected_doc_type && data.detected_doc_type !== data.doc_type;
  const reasons = [
    blocking.length > 0 && `${blocking.length} trường lỗi cần sửa`,
    unchosen.length > 0 && `${unchosen.length} trường khác dữ liệu hiện có cần chọn giữ cũ hay dùng mới`,
    data.suspicious_content && !manualCheck && "cần tick đã kiểm tay",
    mismatch && !confirmType && "cần xác nhận loại chứng từ",
  ].filter(Boolean) as string[];

  const conflictRow = (path: string) => {
    if (!conflicts.includes(path)) return null;
    return (
      <div className="mt-1 grid grid-cols-2 gap-2 rounded-md border border-warning/40 bg-warning-soft/60 p-2 text-[12px]">
        {(["old", "new"] as const).map((use) => (
          <label key={use} className={cn("flex cursor-pointer items-start gap-2 rounded p-1.5", choices[path] === use && "bg-card ring-1 ring-primary")}>
            <input type="radio" name={`c-${path}`} className="mt-0.5 accent-[var(--primary)]" checked={choices[path] === use} disabled={readOnly} onChange={() => setChoices((c) => ({ ...c, [path]: use }))} />
            <span>
              <span className="block font-medium">{use === "old" ? "Giữ hiện tại" : "Dùng AI đọc được"}</span>
              <span className="block break-all font-mono">{use === "old" ? show(data.current[path]) : show(path.split("/").length === 3 ? (result[path.split("/")[1]] as unknown[])?.[Number(path.split("/")[2])] : result[path.split("/")[1]])}</span>
            </span>
          </label>
        ))}
      </div>
    );
  };

  const pages = Array.from({ length: data.document.page_count_rendered }, (_, i) => i + 1);
  const scalar = (def: FieldDef) => {
    const path = `/${def.name}`;
    return (
      <div key={path} className="space-y-1">
        <label className="text-xs text-muted-foreground">{def.label}{def.risky && " (trường rủi ro cao, kiểm kỹ với ảnh)"}</label>
        <CellInput label={def.label} value={valueOf(path, result[def.name])} onChange={(v) => setEdits((e) => ({ ...e, [path]: v }))} issue={issueOf(path)} risky={def.risky} />
        {conflictRow(path)}
      </div>
    );
  };
  return (
    <div className="space-y-3">
      {shipmentLink}
      <div className="flex flex-wrap items-center justify-between gap-2">{title}<span className="text-xs text-muted-foreground">{data.document.original_name}</span></div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <section aria-label="Ảnh chứng từ" className="min-w-0 rounded-lg border bg-muted/40">
          <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs text-muted-foreground">
            <span>{data.document.pages} trang{data.document.pages > data.document.page_count_rendered ? ` (AI đọc ${data.document.page_count_rendered} trang đầu)` : ""}</span>
            <span className="flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" aria-label="Thu nhỏ" onClick={() => setZoom((z) => Math.max(50, z - 25))}><ZoomOut /></Button>
              <span className="w-10 text-center tabular-nums">{zoom}%</span>
              <Button variant="ghost" size="icon-sm" aria-label="Phóng to" onClick={() => setZoom((z) => Math.min(250, z + 25))}><ZoomIn /></Button>
            </span>
          </div>
          <div className="max-h-[calc(100vh-14rem)] space-y-3 overflow-auto p-3">
            {pages.map((page) => (
              // eslint-disable-next-line @next/next/no-img-element -- ảnh chứng từ do API render, kích thước biến đổi
              <img key={page} src={`/api/extractions/${id}/pages/${page}`} alt={`Trang ${page} của chứng từ`} style={{ width: `${zoom}%` }} className="max-w-none rounded border bg-white shadow-xs" />
            ))}
          </div>
        </section>
        <section aria-label="Kết quả AI đọc" className="min-w-0 space-y-4">
          {data.suspicious_content && (
            <div role="alert" className="space-y-2 rounded-lg border border-danger/40 bg-danger-soft p-3 text-[13px] text-danger-ink">
              <p className="flex items-center gap-1.5 font-semibold"><TriangleAlert className="size-4" aria-hidden />Chứng từ có dấu hiệu bất thường</p>
              {data.suspicious_note && <p>{data.suspicious_note}</p>}
              <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={manualCheck} disabled={readOnly} onChange={(e) => setManualCheck(e.target.checked)} />Tôi đã tự kiểm tra chứng từ này</label>
            </div>
          )}
          {mismatch && (
            <div role="alert" className="space-y-2 rounded-lg border border-warning/40 bg-warning-soft p-3 text-[13px] text-warning-ink">
              <p className="font-semibold">AI nhận diện đây là {DOC_TYPE_LABEL[data.detected_doc_type!] ?? data.detected_doc_type}, bạn đã chọn {DOC_TYPE_LABEL[data.doc_type] ?? data.doc_type}</p>
              <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-[var(--primary)]" checked={confirmType} disabled={readOnly} onChange={(e) => setConfirmType(e.target.checked)} />Đúng loại {DOC_TYPE_LABEL[data.doc_type]}, tiếp tục duyệt</label>
            </div>
          )}
          <div className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-2">{defs.scalars.map(scalar)}</div>
          {defs.lists.map((list) => {
            const rows = (result[list.name] as Record<string, unknown>[] | undefined) ?? [];
            return (
              <div key={list.name} className="overflow-hidden rounded-lg border bg-card">
                <h3 className="border-b px-4 py-2 text-[13px] font-semibold">{list.label} ({rows.length})</h3>
                <div className="overflow-auto">
                  <table className="w-full text-[13px]">
                    <thead><tr className="text-left text-xs text-muted-foreground">{list.columns.map((c) => <th key={c.name} className="px-2 py-1.5 font-medium">{c.label}</th>)}</tr></thead>
                    <tbody>
                      {rows.map((row, index) => {
                        const path = `/${list.name}/${index}`;
                        return (
                          <tr key={index} className="align-top">
                            {list.columns.map((c, ci) => (
                              <td key={c.name} className="min-w-28 px-2 py-1">
                                <CellInput label={`${list.label} ${index + 1}: ${c.label}`} value={valueOf(`${path}/${c.name}`, row[c.name])} onChange={(v) => setEdits((e) => ({ ...e, [`${path}/${c.name}`]: v }))} issue={issueOf(`${path}/${c.name}`)} risky={c.risky} />
                                {ci === 0 && conflictRow(path)}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
          {readOnly ? (
            <p className="flex items-center gap-1.5 rounded-lg border bg-card p-3 text-[13px]"><CircleCheck className="size-4 text-success" aria-hidden />Bản này đã {data.status === "APPROVED" ? "được duyệt" : "kết thúc"}, chỉ xem.</p>
          ) : (
            <div className="sticky bottom-0 space-y-2 rounded-lg border bg-card p-3 shadow-md">
              {reasons.length > 0 && <p className="text-[13px] text-warning-ink">Chưa duyệt được: {reasons.join("; ")}.</p>}
              <ErrorBanner error={approve.error ?? reject.error} />
              {rejecting ? (
                <div className="space-y-2">
                  <Textarea aria-label="Lý do từ chối" rows={2} placeholder="Lý do từ chối (tối thiểu 5 ký tự)" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <div className="flex gap-2">
                    <Button variant="destructive" disabled={reason.trim().length < MIN_REASON || reject.isPending} onClick={() => reject.mutate()}>Xác nhận từ chối</Button>
                    <Button variant="ghost" onClick={() => setRejecting(false)}>Đóng</Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">Chỉ trường bạn xác nhận mới được ghi vào lô; giá trị AI không tự ghi đè dữ liệu có sẵn.</p>
                  <div className="flex shrink-0 gap-2">
                    <Button variant="outline" onClick={() => setRejecting(true)}>Từ chối</Button>
                    <Button disabled={reasons.length > 0 || approve.isPending} onClick={() => approve.mutate()}>{approve.isPending ? "Đang duyệt…" : "Duyệt và ghi vào lô"}</Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
