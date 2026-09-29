import { cn } from "@/lib/utils";

/** Dấu hiệu: một thùng container nhìn nghiêng, có các gân dọc. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn("size-6", className)}>
      <rect x="2" y="5" width="20" height="14" rx="2.5" fill="currentColor" />
      {[7, 10.5, 14, 17.5].map((x) => (
        <rect key={x} x={x} y="7.5" width="1.4" height="9" rx="0.7" className="fill-[var(--logo-rib,rgba(255,255,255,0.55))]" />
      ))}
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 text-[15px] font-semibold tracking-tight", className)}>
      <LogoMark className="text-sidebar-primary [--logo-rib:oklch(0.2_0.03_255)]" />
      FwdFlow
    </span>
  );
}
