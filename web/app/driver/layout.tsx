"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { useMe } from "@/lib/use-me";

/** Khung app tài xế: một cột, hợp với điện thoại; chỉ vai trò DRIVER được vào. */
export default function DriverLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me, error, refetch } = useMe();
  const unauthenticated = error instanceof ApiError && error.status === 401;

  useEffect(() => {
    if (unauthenticated) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (me && me.role !== "DRIVER") router.replace("/login");
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
        <Button size="lg" variant="outline" onClick={() => refetch()}>Thử lại</Button>
      </div>
    );
  }
  if (!me || me.role !== "DRIVER") return <div className="m-auto text-muted-foreground">Đang tải…</div>;
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background">
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-primary px-4 text-primary-foreground">
        <div className="leading-tight">
          <p className="text-[15px] font-semibold">{me.full_name}</p>
          <p className="text-xs opacity-75">Tài xế</p>
        </div>
        <Button variant="ghost" className="h-11 text-primary-foreground hover:bg-white/10 hover:text-primary-foreground" onClick={logout}>
          <LogOut />
          Đăng xuất
        </Button>
      </header>
      <main className="flex-1 p-4">{children}</main>
    </div>
  );
}
