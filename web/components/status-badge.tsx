import { Circle, CircleAlert, CircleCheck, CircleDashed, Info, OctagonAlert, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

// Mọi trạng thái là biểu tượng + chữ Việt + màu (màu chỉ là lớp thứ ba, không phải cách duy nhất truyền thông tin).
const TONES = {
  success: { icon: CircleCheck, className: "bg-success-soft text-success-ink" },
  warning: { icon: TriangleAlert, className: "bg-warning-soft text-warning-ink" },
  danger: { icon: OctagonAlert, className: "bg-danger-soft text-danger-ink" },
  info: { icon: Info, className: "bg-info-soft text-info-ink" },
  neutral: { icon: Circle, className: "bg-muted text-muted-foreground" },
  pending: { icon: CircleDashed, className: "border border-dashed border-border bg-transparent text-muted-foreground" },
  attention: { icon: CircleAlert, className: "bg-warning-soft text-warning-ink" },
} satisfies Record<string, { icon: LucideIcon; className: string }>;

export type Tone = keyof typeof TONES;

export function StatusBadge({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  const { icon: Icon, className: toneClass } = TONES[tone];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-full px-2 text-xs font-medium",
        toneClass,
        className,
      )}
    >
      <Icon aria-hidden className="size-3" />
      {children}
    </span>
  );
}
