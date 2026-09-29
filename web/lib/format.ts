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

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Số tiền theo đơn vị nhỏ nhất của tiền tệ (VND: đồng, USD: cent) → chuỗi hiển thị. */
export function formatMoney(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount == null || !currency) return "";
  return currency === "USD" ? usd.format(amount / 100) : vnd.format(amount);
}

/** `2026-11-25T08:00:00+07:00` → `08:00` (giờ Việt Nam). */
const time = new Intl.DateTimeFormat("vi-VN", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit", hour12: false });
export const formatTime = (value: string | Date | null | undefined): string => (value ? time.format(parse(value)) : "");

const localInput = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Thời điểm ISO → giá trị cho `<input type="datetime-local">` theo giờ Việt Nam (`2026-11-25T08:00`). */
export const toLocalInput = (value: string | Date | null | undefined): string =>
  value ? localInput.format(parse(value)).replace(" ", "T") : "";

/** Giá trị `datetime-local` (hiểu là giờ Việt Nam) → ISO có múi giờ `+07:00`. */
export const fromLocalInput = (value: string): string => `${value}:00+07:00`;

/** Ngày hôm nay theo giờ Việt Nam, dạng `YYYY-MM-DD`. */
export const todayVn = (): string => localInput.format(new Date()).slice(0, 10);
