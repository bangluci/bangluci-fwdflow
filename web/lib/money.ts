/**
 * Số tiền người dùng nhập → số nguyên đơn vị nhỏ nhất (VND: đồng; USD/khác: cent).
 * Tách chuỗi thay vì nhân số thực để không sai số; bỏ dấu chấm ngăn nghìn, dấu phẩy là thập phân.
 */
export function toMinorUnits(text: string, currency: string): number | null {
  const clean = text.trim().replace(/\./g, "").replace(",", ".");
  if (!clean) return null;
  const [whole, fraction = ""] = clean.split(".");
  if (currency === "VND") return Number(whole);
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

/** Số nguyên nhỏ nhất → chuỗi để hiện lại trong ô nhập. */
export function fromMinorUnits(amount: number | null | undefined, currency: string): string {
  if (amount == null) return "";
  return currency === "VND" ? String(amount) : (amount / 100).toFixed(2);
}
