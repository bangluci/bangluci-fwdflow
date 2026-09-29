"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sidebar } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { NAV_GROUPS, isActive } from "@/lib/nav-items";
import { ROLE_LABELS, homePath, isInternal } from "@/lib/roles";
import { useMe } from "@/lib/use-me";

export default function BackofficeLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me, error, refetch } = useMe();
  const unauthenticated = error instanceof ApiError && error.status === 401;

  useEffect(() => {
    if (unauthenticated) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (me && !isInternal(me.role)) router.replace(homePath(me.role));
  }, [unauthenticated, me, pathname, router]);

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  }

  if (error && !unauthenticated) {
    return (
      <div className="m-auto space-y-3 text-center" role="alert">
        <p>{error.message}</p>
        <Button variant="outline" onClick={() => refetch()}>
          Thử lại
        </Button>
      </div>
    );
  }
  if (!me || !isInternal(me.role)) return <div className="m-auto text-muted-foreground">Đang tải…</div>;

  const section = NAV_GROUPS.flatMap((g) => g.items).find((item) => isActive(item, pathname))?.label;
  return (
    <div className="min-h-screen pl-60">
      <Sidebar permissions={me.permissions} />
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/85 px-6 backdrop-blur">
        <h1 className="text-[15px] font-semibold tracking-tight">{section}</h1>
        <div className="flex items-center gap-3">
          <div className="text-right leading-tight">
            <p className="text-[13px] font-medium">{me.full_name}</p>
            <p className="text-xs text-muted-foreground">{ROLE_LABELS[me.role]}</p>
          </div>
          <Button variant="outline" size="sm" onClick={logout}>
            <LogOut />
            Đăng xuất
          </Button>
        </div>
      </header>
      <main className="p-6">{children}</main>
    </div>
  );
}
