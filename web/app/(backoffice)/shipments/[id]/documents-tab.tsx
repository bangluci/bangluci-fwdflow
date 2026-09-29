"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileUp, MoreHorizontal, Replace } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { ErrorBanner, Field } from "@/components/form-field";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { FALLBACK_PROVIDER_LABEL, useAiStatus } from "@/lib/use-ai-status";
import { DOC_TYPE_LABEL } from "@/lib/shipment-labels";

export type DocumentRow = {
  id: number;
  doc_type: string;
  mime: string;
  size_bytes: number;
  pages: number;
  original_name: string | null;
  superseded_by_id: number | null;
  visible_to_customer: boolean;
  uploaded_at: string;
};
export type ExtractionSummary = { id: number; document_id: number; doc_type: string; status: string };

const AI_TYPES = ["MBL", "HBL", "INVOICE", "PACKING_LIST"];
const helper = columnHelper<DocumentRow>();
const size = (bytes: number) => (bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

function UploadDialog({ shipmentId, replacing, existing, onClose }: { shipmentId: number; replacing?: DocumentRow; existing: DocumentRow[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const providerLabel = useAiStatus().data?.provider_label ?? FALLBACK_PROVIDER_LABEL;
  const [docType, setDocType] = useState(replacing?.doc_type ?? "INVOICE");
  const [file, setFile] = useState<File | null>(null);
  const done = async () => {
    await queryClient.invalidateQueries({ queryKey: ["documents", shipmentId] });
    queryClient.invalidateQueries({ queryKey: ["extractions", shipmentId] });
    queryClient.invalidateQueries({ queryKey: ["shipment-side", shipmentId] });
    onClose();
  };
  const send = useMutation({
    mutationFn: ({ keepBoth, supersede }: { keepBoth?: boolean; supersede?: number }) => {
      const body = new FormData();
      body.append("file", file as File);
      if (supersede) return apiFetch(`/api/documents/${supersede}/supersede`, { method: "POST", body });
      body.append("doc_type", docType);
      if (keepBoth) body.append("keep_both", "true");
      return apiFetch(`/api/shipments/${shipmentId}/documents`, { method: "POST", body });
    },
    onSuccess: done,
  });
  const sameType = send.error instanceof ApiError && send.error.code === "SAME_TYPE_EXISTS";
  const current = existing.find((d) => d.doc_type === docType && d.superseded_by_id == null);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{replacing ? `Thay ${DOC_TYPE_LABEL[replacing.doc_type]}` : "Tải chứng từ lên"}</DialogTitle>
          <DialogDescription>PDF hoặc ảnh JPEG / PNG, tối đa 20 MB. File được làm sạch trước khi lưu.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {!replacing && (
            <Field label="Loại chứng từ" htmlFor="u-type">
              <Select value={docType} onValueChange={(v) => { setDocType(v); send.reset(); }}>
                <SelectTrigger id="u-type" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(DOC_TYPE_LABEL).map(([key, label]) => <SelectItem key={key} value={key}>{label}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          )}
          <Field label="File" htmlFor="u-file" required hint={AI_TYPES.includes(docType) ? "Chứng từ MBL/HBL/Invoice/Packing list sẽ được gửi tới " + providerLabel + " để đọc; chỉ dùng dữ liệu mô phỏng khi demo. Kết quả nằm chờ người duyệt." : undefined}>
            <Input id="u-file" type="file" accept="application/pdf,image/jpeg,image/png" onChange={(e) => { setFile(e.target.files?.[0] ?? null); send.reset(); }} />
          </Field>
          {sameType && current ? (
            <div role="alert" className="space-y-2 rounded-md border border-warning/40 bg-warning-soft p-3 text-[13px] text-warning-ink">
              <p>Lô đã có {DOC_TYPE_LABEL[docType]} ({current.original_name ?? `#${current.id}`}). Thay bản cũ hay giữ cả hai?</p>
              <div className="flex gap-2">
                <Button size="sm" disabled={send.isPending} onClick={() => send.mutate({ supersede: current.id })}>Thay bản cũ</Button>
                <Button size="sm" variant="outline" disabled={send.isPending} onClick={() => send.mutate({ keepBoth: true })}>Giữ cả hai</Button>
              </div>
            </div>
          ) : (
            <ErrorBanner error={send.error} />
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!file || send.isPending} onClick={() => send.mutate(replacing ? { supersede: replacing.id } : {})}>
            {send.isPending ? "Đang tải lên…" : "Tải lên"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DocumentsTab({ shipmentId, canWrite, canReview, closed }: { shipmentId: number; canWrite: boolean; canReview: boolean; closed: boolean }) {
  const [dialog, setDialog] = useState<{ replacing?: DocumentRow } | null>(null);
  const [showOld, setShowOld] = useState(false);
  const docs = useQuery({ queryKey: ["documents", shipmentId], queryFn: () => apiFetch<DocumentRow[]>(`/api/shipments/${shipmentId}/documents`) });
  const extractions = useQuery({
    queryKey: ["extractions", shipmentId],
    queryFn: () => apiFetch<ExtractionSummary[]>(`/api/shipments/${shipmentId}/extractions`),
    enabled: canReview,
  });
  const byDocument = new Map((extractions.data ?? []).map((e) => [e.document_id, e]));
  const rows = (docs.data ?? []).filter((d) => showOld || d.superseded_by_id == null);
  const columns = [
    helper.accessor((row) => DOC_TYPE_LABEL[row.doc_type] ?? row.doc_type, { id: "type", header: "Loại", cell: (ctx) => <span className="font-medium">{ctx.getValue()}</span> }),
    helper.accessor((row) => row.original_name ?? "", { id: "name", header: "Tên file", cell: (ctx) => <span className="block max-w-72 truncate" title={ctx.getValue()}>{ctx.getValue() || "—"}</span> }),
    helper.accessor("pages", { header: "Trang", cell: (ctx) => <span className="block text-right tabular-nums">{ctx.getValue()}</span> }),
    helper.accessor((row) => size(row.size_bytes), { id: "size", header: "Dung lượng" }),
    helper.accessor((row) => formatDateTime(row.uploaded_at), { id: "uploaded", header: "Tải lên lúc" }),
    helper.accessor((row) => (row.visible_to_customer ? "Có" : "Không"), { id: "visible", header: "Khách xem được" }),
    helper.display({
      id: "state", header: "Trạng thái",
      cell: (ctx) => {
        const row = ctx.row.original;
        if (row.superseded_by_id != null) return <StatusBadge tone="neutral">Đã thay thế</StatusBadge>;
        const extraction = byDocument.get(row.id);
        if (!extraction) return <StatusBadge tone="success">Hiện hành</StatusBadge>;
        if (extraction.status === "REVIEW") return <StatusBadge tone="attention">AI đọc xong, chờ duyệt</StatusBadge>;
        if (extraction.status === "PENDING" || extraction.status === "PROCESSING") return <StatusBadge tone="pending">AI đang đọc</StatusBadge>;
        if (extraction.status === "FAILED") return <StatusBadge tone="danger">AI đọc lỗi</StatusBadge>;
        return <StatusBadge tone="success">Hiện hành</StatusBadge>;
      },
    }),
    helper.display({
      id: "actions", header: () => <span className="sr-only">Thao tác</span>,
      cell: (ctx) => {
        const row = ctx.row.original;
        const extraction = byDocument.get(row.id);
        return (
          <div className="flex justify-end gap-1">
            {extraction && canReview && extraction.status !== "CANCELLED" && (
              <Button asChild variant="outline" size="xs">
                <Link href={`/extractions/${extraction.id}`}><Eye />Xem kết quả AI</Link>
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal /></Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem asChild><a href={`/api/documents/${row.id}/file`} target="_blank" rel="noreferrer"><Download />Tải về / xem</a></DropdownMenuItem>
                {canWrite && !closed && row.superseded_by_id == null && <DropdownMenuItem onSelect={() => setDialog({ replacing: row })}><Replace />Thay bằng bản mới</DropdownMenuItem>}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    }),
  ];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Chứng từ</h2>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" className="size-3.5 accent-[var(--primary)]" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} />
            Hiện cả bản đã thay thế
          </label>
          {canWrite && !closed && <Button size="sm" onClick={() => setDialog({})}><FileUp />Tải chứng từ</Button>}
        </div>
      </div>
      <DataTable columns={columns} data={rows} loading={docs.isPending} error={docs.error} onRetry={() => docs.refetch()} getRowId={(r) => String(r.id)}
        empty={{ none: { title: "Chưa có chứng từ", hint: canWrite ? 'Bấm "Tải chứng từ" để thêm chứng từ đầu tiên.' : undefined }, filtered: { title: "Không có kết quả" } }} />
      {dialog && <UploadDialog shipmentId={shipmentId} replacing={dialog.replacing} existing={docs.data ?? []} onClose={() => setDialog(null)} />}
    </div>
  );
}
