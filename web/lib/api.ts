// Client gọi API cùng origin (Caddy chuyển /api/* sang FastAPI). Mọi response theo envelope {success, data, error, meta}.

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
  }
}

export type PageMeta = { total: number; page: number; limit: number };
export type Page<T> = { data: T[]; meta: PageMeta };
type Init = RequestInit & { json?: unknown };
type Envelope<T> = {
  success: boolean;
  data: T;
  error: { code: string; message: string; details?: unknown } | null;
  meta: PageMeta | null;
};

const NETWORK_MESSAGE = "Không kết nối được máy chủ";

async function call<T>(path: string, { json, headers, ...init }: Init = {}): Promise<Envelope<T>> {
  const merged = new Headers(headers);
  let body = init.body;
  if (json !== undefined) {
    merged.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: merged, body, credentials: "same-origin" });
  } catch {
    throw new ApiError("NETWORK_ERROR", NETWORK_MESSAGE, 0);
  }
  let envelope: Envelope<T>;
  try {
    envelope = await res.json();
  } catch {
    throw new ApiError("NETWORK_ERROR", NETWORK_MESSAGE, res.status);
  }
  if (!envelope.success) {
    const { code, message, details } = envelope.error ?? { code: "UNKNOWN", message: "Lỗi không xác định" };
    throw new ApiError(code, message, res.status, details);
  }
  return envelope;
}

export async function apiFetch<T>(path: string, init?: Init): Promise<T> {
  return (await call<T>(path, init)).data;
}

export async function apiFetchPage<T>(path: string, init?: Init): Promise<Page<T>> {
  const { data, meta } = await call<T[]>(path, init);
  return { data, meta: meta ?? { total: data.length, page: 1, limit: data.length } };
}

/** Thông điệp hiển thị cho người dùng: thêm chi tiết từng trường (nếu API trả `details`) sau thông điệp chung. */
export function errorText(error: unknown): string {
  if (!(error instanceof ApiError)) return "Đã có lỗi, vui lòng thử lại";
  const details = Array.isArray(error.details) ? error.details : [];
  const messages = details
    .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg).replace(/^Value error, /, "") : ""))
    .filter(Boolean);
  return messages.length ? `${error.message}: ${messages.join("; ")}` : error.message;
}
