// Kiểm tra bậc phí ở client, cùng lý do và thứ tự với `validate_tiers` của API (api/app/freetime/tiers.py).

export type TierDraft = { from_day: number; to_day: number | null; rate_amount: number; currency: "VND" | "USD" };
export type TierProblem = { reason: string; index: number | null; message: string };

const problem = (reason: string, message: string, index: number | null = null): TierProblem => ({ reason, index, message });

export function validateTiersClient(freeDays: number, tiers: TierDraft[]): TierProblem | null {
  if (tiers.length === 0) return problem("EMPTY", "Quy tắc cần ít nhất một bậc phí");
  const ordered = [...tiers].sort((a, b) => a.from_day - b.from_day);
  for (const [index, t] of ordered.entries()) {
    const badNumber = ![t.from_day, t.rate_amount].every(Number.isFinite) || (t.to_day !== null && !Number.isFinite(t.to_day));
    if (badNumber || t.from_day < 1 || (t.to_day !== null && t.to_day < t.from_day) || t.rate_amount < 0) {
      return problem("BAD_VALUE", "Bậc phí có giá trị không hợp lệ (ngày ≥ 1, đến ≥ từ, đơn giá ≥ 0)", index);
    }
  }
  if (ordered[0].from_day !== freeDays + 1) return problem("FIRST_TIER_START", `Bậc đầu phải bắt đầu ở ngày ${freeDays + 1} (ngày free + 1)`, 0);
  for (let index = 1; index < ordered.length; index++) {
    const previous = ordered[index - 1];
    const tier = ordered[index];
    if (previous.to_day === null) return problem("OPEN_TIER_NOT_LAST", "Chỉ bậc cuối được để trống ngày kết thúc", index - 1);
    if (tier.from_day <= previous.to_day) return problem("OVERLAP", "Hai bậc phí chồng lên nhau", index);
    if (tier.from_day > previous.to_day + 1) return problem("GAP", "Giữa hai bậc phí có khoảng trống ngày", index);
  }
  if (ordered[ordered.length - 1].to_day !== null) return problem("LAST_TIER_CLOSED", "Bậc cuối phải để trống ngày kết thúc (tính từ đó trở đi)", ordered.length - 1);
  if (new Set(ordered.map((t) => t.currency)).size > 1) return problem("MIXED_CURRENCY", "Các bậc của một quy tắc phải cùng một loại tiền tệ");
  return null;
}
