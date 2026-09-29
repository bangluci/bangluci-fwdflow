// Định dạng hiển thị theo địa phương Việt Nam: ngày dd/MM/yyyy giờ Asia/Ho_Chi_Minh, tiền VND, số.

const TIME_ZONE = "Asia/Ho_Chi_Minh";
const date = new Intl.DateTimeFormat("vi-VN", { timeZone: TIME_ZONE, day: "2-digit", month: "2-digit", year: "numeric" });
const dateTime = new Intl.DateTimeFormat("vi-VN", {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const number = new Intl.NumberFormat("vi-VN");
const vnd = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

const parse = (value: string | Date) => (value instanceof Date ? value : new Date(value));

/** `2026-10-05` hoặc timestamp ISO → `05/10/2026`; rỗng nếu không có giá trị. */
export function formatDate(value: string | Date | null | undefined): string {
  return value ? date.format(parse(value)) : "";
}

export function formatDateTime(value: string | Date | null | undefined): string {
  return value ? dateTime.format(parse(value)) : "";
}

export const formatNumber = (value: number | null | undefined): string => (value == null ? "" : number.format(value));

/** Số nguyên đồng → `1.234.567 ₫`. */
export const formatVnd = (value: number | null | undefined): string => (value == null ? "" : vnd.format(value));
