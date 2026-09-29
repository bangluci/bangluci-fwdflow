"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { LogoMark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { useMe } from "@/lib/use-me";

/** Khung cổng khách hàng: chỉ vai trò CUSTOMER; chỉ gọi /api/portal/* và /api/auth/*. */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me, error, refetch } = useMe();
  const unauthenticated = error instanceof ApiError && error.status === 401;

  useEffect(() => {
    if (unauthenticated) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (me && me.role !== "CUSTOMER") router.replace("/login");
  }, [unauthenticated, me, pathname, router]);

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  }

  if (error && !unauthenticated) {
    return (
      <div className="m-auto space-y-3 p-6 text-center" role="alert">
        <p>{error.message}</p>
        <Button variant="outline" onClick={() => refetch()}>Thử lại</Button>
      </div>
    );
  }
  if (!me || me.role !== "CUSTOMER") return <div className="m-auto text-muted-foreground">Đang tải…</div>;
  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-10 border-b bg-primary text-primary-foreground">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <Link href="/portal" className="flex items-center gap-2 font-semibold"><LogoMark className="size-5 text-sidebar-primary" />FwdFlow · Khách hàng</Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-[13px] sm:inline">{me.full_name}</span>
            <Button variant="ghost" size="sm" className="text-primary-foreground hover:bg-white/10 hover:text-primary-foreground" onClick={logout}><LogOut />Đăng xuất</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl p-4">{children}</main>
    </div>
  );
}
