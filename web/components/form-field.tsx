import { Label } from "@/components/ui/label";
import { errorText } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Nhãn + ô nhập + gợi ý / lỗi của một trường. */
export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  hint?: string;
  error?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {required && " *"}
      </Label>
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Khung báo lỗi của API ở đầu form / hộp thoại. */
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
      {typeof error === "string" ? error : errorText(error)}
    </p>
  );
}
