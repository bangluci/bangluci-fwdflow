"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { columnHelper, DataTable } from "@/components/data-table";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, apiFetch, errorText } from "@/lib/api";
import { ROLES, ROLE_LABELS, type Role } from "@/lib/roles";
import { useDebounce } from "@/lib/use-debounce";
import { ChangeRoleDialog, CreateUserDialog, ResetPasswordDialog, type UserRow } from "./user-dialogs";

const helper = columnHelper<UserRow>();
const ALL = "all";

export function UsersScreen() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState<Role | typeof ALL>(ALL);
  const [status, setStatus] = useState<"all" | "active" | "locked">(ALL);
  const [dialog, setDialog] = useState<{ kind: "create" } | { kind: "role" | "password"; user: UserRow } | null>(null);
  const [notice, setNotice] = useState("");
  const q = useDebounce(search.trim());

  const users = useQuery({
    queryKey: ["users", q],
    queryFn: () => apiFetch<UserRow[]>(`/api/users${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });
  const rows = useMemo(
    () => (users.data ?? []).filter((u) => (role === ALL || u.role === role) &&
      (status === ALL || (status === "active") === u.is_active)),
    [users.data, role, status],
  );

  const act = useMutation({
    mutationFn: ({ path, json, method = "POST" }: { path: string; json?: unknown; method?: string }) =>
      apiFetch(`/api/users/${path}`, { method, json }),
    onSuccess: async (_, vars) => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setNotice(vars.method === "PATCH" ? "Đã cập nhật; mọi phiên của người này đã bị đăng xuất." : "Đã mở khoá đăng nhập.");
    },
    onError: (error) => setNotice(errorText(error)),
  });

  const columns = useMemo(() => [
    helper.accessor("full_name", { header: "Họ và tên", cell: (ctx) => <span className="font-medium">{ctx.getValue()}</span> }),
    helper.accessor((row) => row.email ?? row.phone ?? "", { id: "login", header: "Email / SĐT",
      cell: (ctx) => <span className="font-mono text-xs">{ctx.getValue()}</span> }),
    helper.accessor((row) => ROLE_LABELS[row.role], { id: "role", header: "Vai trò",
      cell: (ctx) => <StatusBadge tone="info">{ctx.getValue()}</StatusBadge> }),
    helper.accessor((row) => (row.is_active ? "Đang hoạt động" : "Đã khoá"), { id: "status", header: "Trạng thái",
      cell: (ctx) => <StatusBadge tone={ctx.row.original.is_active ? "success" : "neutral"}>{ctx.getValue()}</StatusBadge> }),
    helper.display({ id: "actions", header: () => <span className="sr-only">Thao tác</span>, cell: (ctx) => {
      const user = ctx.row.original;
      return (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setDialog({ kind: "role", user })}>Đổi vai trò</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => act.mutate({ path: String(user.id), method: "PATCH", json: { is_active: !user.is_active } })}>
                {user.is_active ? "Khoá tài khoản" : "Mở lại tài khoản"}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => act.mutate({ path: `${user.id}/unlock` })}>Mở khoá đăng nhập</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setDialog({ kind: "password", user })}>Đặt lại mật khẩu</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      );
    } }),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], []);

  const forbidden = users.error instanceof ApiError && users.error.status === 403;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search aria-hidden className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Tìm kiếm" placeholder="Tìm theo tên, email, số điện thoại" className="pl-8" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={role} onValueChange={(v) => setRole(v as Role | typeof ALL)}>
          <SelectTrigger aria-label="Lọc theo vai trò" className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Mọi vai trò</SelectItem>
            {ROLES.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
          <SelectTrigger aria-label="Lọc theo trạng thái" className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Mọi trạng thái</SelectItem>
            <SelectItem value="active">Đang hoạt động</SelectItem>
            <SelectItem value="locked">Đã khoá</SelectItem>
          </SelectContent>
        </Select>
        <p role="status" className="text-[13px] text-muted-foreground">{notice}</p>
        <Button className="ml-auto" onClick={() => setDialog({ kind: "create" })}><Plus />Thêm người dùng</Button>
      </div>
      {forbidden ? (
        <p role="alert" className="rounded-lg border bg-card p-10 text-center text-sm">Bạn không có quyền xem trang này</p>
      ) : (
        <DataTable columns={columns} data={rows} loading={users.isPending} error={users.error} onRetry={() => users.refetch()}
          filtered={!!q || role !== ALL || status !== ALL} getRowId={(row) => String(row.id)}
          empty={{ none: { title: "Chưa có người dùng nào" }, filtered: { title: "Không có kết quả khớp", hint: "Thử đổi từ khoá hoặc bộ lọc." } }} />
      )}
      {dialog?.kind === "create" && <CreateUserDialog onClose={() => setDialog(null)} onDone={setNotice} />}
      {dialog?.kind === "role" && <ChangeRoleDialog user={dialog.user} onClose={() => setDialog(null)} onDone={setNotice} />}
      {dialog?.kind === "password" && <ResetPasswordDialog user={dialog.user} onClose={() => setDialog(null)} onDone={setNotice} />}
    </div>
  );
}
