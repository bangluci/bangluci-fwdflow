"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, errorText } from "@/lib/api";
import type { CatalogItem } from "@/lib/catalog-kinds";
import { ROLES, ROLE_LABELS, type Role } from "@/lib/roles";

export type UserRow = {
  id: number;
  email: string | null;
  phone: string | null;
  full_name: string;
  role: Role;
  customer_id: number | null;
  driver_id: number | null;
  is_active: boolean;
};

const MIN_PASSWORD = 10;
const MAX_PASSWORD = 128;

function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
      {errorText(error)}
    </p>
  );
}

function RoleLink({ role, value, onChange }: { role: Role; value: { customer: string; driver: string };
  onChange: (next: { customer: string; driver: string }) => void }) {
  const kind = role === "CUSTOMER" ? "customers" : role === "DRIVER" ? "drivers" : null;
  const options = useQuery({
    queryKey: ["catalog", kind, "options"],
    queryFn: () => apiFetch<CatalogItem[]>(`/api/catalog/${kind}?active=true`),
    enabled: kind !== null,
  });
  if (!kind) return null;
  const current = role === "CUSTOMER" ? value.customer : value.driver;
  return (
    <div className="space-y-1.5">
      <Label htmlFor="u-link">{role === "CUSTOMER" ? "Khách hàng *" : "Tài xế *"}</Label>
      <Select value={current} onValueChange={(v) => onChange(role === "CUSTOMER" ? { ...value, customer: v } : { ...value, driver: v })}>
        <SelectTrigger id="u-link" className="w-full"><SelectValue placeholder="Chọn…" /></SelectTrigger>
        <SelectContent>
          {(options.data ?? []).map((o) => (
            <SelectItem key={o.id} value={String(o.id)}>{String(o.name ?? o.full_name)}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

const roleBody = (role: Role, link: { customer: string; driver: string }) => ({
  role,
  ...(role === "CUSTOMER" ? { customer_id: Number(link.customer) } : {}),
  ...(role === "DRIVER" ? { driver_id: Number(link.driver) } : {}),
});

export function CreateUserDialog({ onClose, onDone }: { onClose: () => void; onDone: (message: string) => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [role, setRole] = useState<Role>("DOCS");
  const [link, setLink] = useState({ customer: "", driver: "" });
  const [problem, setProblem] = useState("");
  const create = useMutation({
    mutationFn: () => apiFetch("/api/users", { method: "POST", json: {
      full_name: form.full_name.trim(), email: form.email.trim() || null, phone: form.phone.trim() || null,
      password: form.password, ...roleBody(role, link) } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      onDone("Đã tạo người dùng.");
      onClose();
    },
  });
  const set = (name: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.full_name.trim()) return setProblem("Nhập họ và tên");
    if (!form.email.trim() && !form.phone.trim()) return setProblem("Cần email hoặc số điện thoại để đăng nhập");
    if (form.password.length < MIN_PASSWORD || form.password.length > MAX_PASSWORD)
      return setProblem(`Mật khẩu phải từ ${MIN_PASSWORD} đến ${MAX_PASSWORD} ký tự`);
    if ((role === "CUSTOMER" && !link.customer) || (role === "DRIVER" && !link.driver)) return setProblem("Chọn khách hàng / tài xế liên kết");
    setProblem("");
    create.mutate();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Thêm người dùng</DialogTitle>
          <DialogDescription>Đăng nhập bằng email hoặc số điện thoại.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="space-y-3">
          <div className="space-y-1.5"><Label htmlFor="u-name">Họ và tên *</Label><Input id="u-name" value={form.full_name} onChange={set("full_name")} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label htmlFor="u-email">Email</Label><Input id="u-email" value={form.email} onChange={set("email")} /></div>
            <div className="space-y-1.5"><Label htmlFor="u-phone">Số điện thoại</Label><Input id="u-phone" value={form.phone} onChange={set("phone")} /></div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="u-role">Vai trò *</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger id="u-role" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <RoleLink role={role} value={link} onChange={setLink} />
          <div className="space-y-1.5">
            <Label htmlFor="u-pass">Mật khẩu *</Label>
            <Input id="u-pass" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} />
            <p className="text-xs text-muted-foreground">{MIN_PASSWORD} đến {MAX_PASSWORD} ký tự.</p>
          </div>
          {problem && <p role="alert" className="text-xs text-destructive">{problem}</p>}
          <FormError error={create.error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Huỷ</Button>
            <Button type="submit" disabled={create.isPending}>{create.isPending ? "Đang lưu…" : "Tạo"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ChangeRoleDialog({ user, onClose, onDone }: { user: UserRow; onClose: () => void; onDone: (m: string) => void }) {
  const queryClient = useQueryClient();
  const [role, setRole] = useState<Role>(user.role);
  const [link, setLink] = useState({ customer: String(user.customer_id ?? ""), driver: String(user.driver_id ?? "") });
  const change = useMutation({
    mutationFn: () => apiFetch(`/api/users/${user.id}`, { method: "PATCH", json: roleBody(role, link) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      onDone("Đã đổi vai trò; mọi phiên đăng nhập của người này đã bị đăng xuất.");
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Đổi vai trò</DialogTitle>
          <DialogDescription>{user.full_name}. Đổi vai trò sẽ đăng xuất mọi phiên của người này.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Select value={role} onValueChange={(v) => setRole(v as Role)}>
            <SelectTrigger aria-label="Vai trò" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}</SelectContent>
          </Select>
          <RoleLink role={role} value={link} onChange={setLink} />
          <FormError error={change.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={change.isPending || role === user.role} onClick={() => change.mutate()}>Đổi vai trò</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ResetPasswordDialog({ user, onClose, onDone }: { user: UserRow; onClose: () => void; onDone: (m: string) => void }) {
  const [password, setPassword] = useState("");
  const reset = useMutation({
    mutationFn: () => apiFetch(`/api/users/${user.id}/reset-password`, { method: "POST", json: { password } }),
    onSuccess: () => {
      onDone("Đã đặt lại mật khẩu; mọi phiên của người này đã bị đăng xuất.");
      onClose();
    },
  });
  const valid = password.length >= MIN_PASSWORD && password.length <= MAX_PASSWORD;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Đặt lại mật khẩu</DialogTitle>
          <DialogDescription>{user.full_name}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="r-pass">Mật khẩu mới</Label>
          <Input id="r-pass" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="text-xs text-muted-foreground">{MIN_PASSWORD} đến {MAX_PASSWORD} ký tự.</p>
        </div>
        <FormError error={reset.error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!valid || reset.isPending} onClick={() => reset.mutate()}>Đặt lại</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
