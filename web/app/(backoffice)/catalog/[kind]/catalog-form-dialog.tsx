"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, errorText } from "@/lib/api";
import {
  type CatalogConfig,
  type CatalogItem,
  type CatalogKind,
  type FormValues,
  toFormValues,
  toPayload,
  validateRequired,
} from "@/lib/catalog-kinds";

const NONE = "__none__";

type Props = {
  kind: CatalogKind;
  config: CatalogConfig;
  /** Có `item` là sửa, không có là thêm mới. */
  item?: CatalogItem;
  refOptions: Partial<Record<CatalogKind, CatalogItem[]>>;
  onClose: () => void;
};

/** Form thêm / sửa một bản ghi danh mục; lỗi của API (trùng mã, tham chiếu sai...) hiện ngay trong hộp thoại. */
export function CatalogFormDialog({ kind, config, item, refOptions, onClose }: Props) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<FormValues>(() => toFormValues(config, item));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () =>
      item
        ? apiFetch(`/api/catalog/${kind}/${item.id}`, { method: "PATCH", json: toPayload(config, values) })
        : apiFetch(`/api/catalog/${kind}`, { method: "POST", json: toPayload(config, values) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["catalog", kind] });
      onClose();
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validateRequired(config, values);
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate();
  }

  const set = (name: string, value: string) => setValues((current) => ({ ...current, [name]: value }));

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{item ? `Sửa ${config.singular}` : `Thêm ${config.singular}`}</DialogTitle>
          <DialogDescription>Trường có dấu * là bắt buộc.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          {config.fields.map((field) => (
            <div key={field.name} className="space-y-1.5">
              <Label htmlFor={`f-${field.name}`}>
                {field.label}
                {field.required && " *"}
              </Label>
              {field.type === "textarea" ? (
                <Textarea id={`f-${field.name}`} rows={2} value={values[field.name]}
                  onChange={(e) => set(field.name, e.target.value)} aria-invalid={!!errors[field.name]} />
              ) : field.type === "ref" ? (
                <Select value={values[field.name] || NONE}
                  onValueChange={(value) => set(field.name, value === NONE ? "" : value)}>
                  <SelectTrigger id={`f-${field.name}`} className="w-full" aria-invalid={!!errors[field.name]}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {!field.required && <SelectItem value={NONE}>Không chọn</SelectItem>}
                    {(refOptions[field.refKind!] ?? []).map((option) => (
                      <SelectItem key={option.id} value={String(option.id)}>
                        {String(option.name ?? option.full_name ?? option.id)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input id={`f-${field.name}`} value={values[field.name]} onChange={(e) => set(field.name, e.target.value)}
                  aria-invalid={!!errors[field.name]} />
              )}
              {errors[field.name] ? (
                <p className="text-xs text-destructive">{errors[field.name]}</p>
              ) : (
                field.hint && <p className="text-xs text-muted-foreground">{field.hint}</p>
              )}
            </div>
          ))}
          {save.isError && (
            <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
              {errorText(save.error)}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Huỷ
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Đang lưu…" : "Lưu"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
