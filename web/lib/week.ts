// Tính tuần (thứ Hai → Chủ nhật) trên chuỗi ngày `YYYY-MM-DD` theo lịch Việt Nam, không qua múi giờ trình duyệt.

const DAY_MS = 86_400_000;
const parse = (day: string) => Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10)));
const format = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export const addDays = (day: string, count: number): string => format(parse(day) + count * DAY_MS);

/** Thứ Hai của tuần chứa `day`. */
export function startOfWeek(day: string): string {
  const weekday = new Date(parse(day)).getUTCDay(); // 0 = Chủ nhật
  return addDays(day, -((weekday + 6) % 7));
}

export const weekDays = (start: string): string[] => Array.from({ length: 7 }, (_, i) => addDays(start, i));

const VN_DATE = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" });
/** Thời điểm ISO → ngày `YYYY-MM-DD` theo giờ Việt Nam. */
export const vnDay = (iso: string): string => VN_DATE.format(new Date(iso));

const WEEKDAY = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
export const weekdayLabel = (day: string): string => WEEKDAY[new Date(parse(day)).getUTCDay()];
export const shortDate = (day: string): string => `${day.slice(8, 10)}/${day.slice(5, 7)}`;
