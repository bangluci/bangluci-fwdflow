import { CircleCheck, OctagonAlert, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate, formatMoney } from "@/lib/format";
import { FEE_TYPE_SHORT, type FreeTimeRow } from "@/lib/freetime";

type Chip = { icon: typeof CircleCheck | null; text: string; className: string };

// Hệ trạng thái free time tách hẳn luồng hải quan: tick "An toàn", tam giác "Sắp hạn", bát giác "Quá hạn".
export function describeClock(row: FreeTimeRow): Chip {
  if (row.status === "NO_RULE") {
    return { icon: null, text: "Chưa có quy tắc: thêm quy tắc hoặc ghi đè số ngày", className: "border-dashed text-muted-foreground" };
  }
  if (row.status === "MISSING_DATA") {
    return { icon: null, text: "Thiếu ngày dỡ hàng: nhập DISCHARGED", className: "border-dashed text-muted-foreground" };
  }
  if (row.status === "NOT_STARTED") return { icon: null, text: "Chưa bắt đầu", className: "border-dashed text-muted-foreground" };
  if (row.status === "CLOSED") {
    const over = row.days_over ? `, quá ${row.days_over} ngày` : "";
    return { icon: null, text: `Đã đóng: dùng ${row.days_used} ngày${over}`, className: "bg-muted text-muted-foreground border-transparent" };
  }
  const left = row.days_left ?? 0;
  if (row.level === "RED") {
    const fee = row.fee_amount ? ` · phí ước tính ${formatMoney(row.fee_amount, row.fee_currency)}` : "";
    return { icon: OctagonAlert, text: `Quá ${row.days_over} ngày${fee}`, className: "bg-danger-soft text-danger-ink border-transparent" };
  }
  if (row.level === "YELLOW") {
    const text = left === 0 ? "Hôm nay là ngày cuối" : `Còn ${left} ngày · hết hạn ${formatDate(row.due_date).slice(0, 5)}`;
    return { icon: TriangleAlert, text, className: "bg-warning-soft text-warning-ink border-transparent" };
  }
  return {
    icon: CircleCheck,
    text: `Còn ${left} ngày · hết hạn ${formatDate(row.due_date).slice(0, 5)}`,
    className: "bg-success-soft text-success-ink border-transparent",
  };
}

export function FreeTimeChip({ row, showFee = true }: { row: FreeTimeRow; showFee?: boolean }) {
  const chip = describeClock(row);
  const Icon = chip.icon;
  const text = showFee || row.level !== "RED" ? chip.text : chip.text.split(" · ")[0];
  return (
    <span className={cn("inline-flex min-h-5 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", chip.className)}>
      {Icon && <Icon aria-hidden className="size-3 shrink-0" />}
      <span className="font-semibold">{FEE_TYPE_SHORT[row.fee_type]}</span>
      {text}
    </span>
  );
}
