"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, apiFetch } from "@/lib/api";
import { homePath } from "@/lib/roles";
import { safeNext } from "@/lib/safe-next";
import { meQuery } from "@/lib/use-me";

const schema = z.object({
  identifier: z.string().trim().min(1, "Nhập email hoặc số điện thoại"),
  password: z.string().min(1, "Nhập mật khẩu"),
});
type Values = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await apiFetch("/api/auth/login", { method: "POST", json: values });
      const me = await queryClient.fetchQuery({ ...meQuery, staleTime: 0 });
      router.replace(next ?? homePath(me.role));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Đã có lỗi, vui lòng thử lại");
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="identifier">Email hoặc số điện thoại</Label>
        <Input id="identifier" autoComplete="username" aria-invalid={!!errors.identifier} {...register("identifier")} />
        {errors.identifier && <p className="text-xs text-destructive">{errors.identifier.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Mật khẩu</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          {...register("password")}
        />
        {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
      </div>
      {error && (
        <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Đang đăng nhập…" : "Đăng nhập"}
      </Button>
    </form>
  );
}

const LEGEND = [
  { dot: "bg-success", label: "An toàn" },
  { dot: "bg-warning", label: "Sắp hạn" },
  { dot: "bg-danger", label: "Quá hạn" },
];

export default function LoginPage() {
  return (
    <div className="flex min-h-screen">
      <section className="container-ribs relative hidden flex-1 flex-col justify-between bg-sidebar p-12 text-sidebar-accent-foreground lg:flex">
        <Logo />
        <div className="max-w-md space-y-4">
          <p className="text-4xl font-semibold leading-[1.15] tracking-tight">Mỗi container một chiếc đồng hồ.</p>
          <p className="text-[15px] leading-relaxed text-sidebar-foreground">
            Chứng từ, free time và giao hàng door-to-door trên một màn hình. Lô nào sắp quá hạn, nhìn là biết.
          </p>
        </div>
        <ul className="flex gap-6 text-xs text-sidebar-foreground">
          {LEGEND.map(({ dot, label }) => (
            <li key={label} className="flex items-center gap-2">
              <span className={`size-2 rounded-full ${dot}`} />
              {label}
            </li>
          ))}
        </ul>
      </section>
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-7">
          <div className="space-y-1.5">
            <Logo className="mb-6 text-foreground lg:hidden" />
            <h1 className="text-2xl font-semibold tracking-tight">Đăng nhập</h1>
            <p className="text-[13px] text-muted-foreground">Vào hệ thống FwdFlow bằng tài khoản được cấp.</p>
          </div>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
