// Hàng chờ "chưa gửi" của app tài xế: thao tác được lưu vào IndexedDB (kèm ảnh) TRƯỚC khi gửi, nên mất mạng hay đóng
// tab cũng không mất. `client_request_id` bất biến nên gửi lại bao nhiêu lần server cũng chỉ ghi một event.

const DB_NAME = "fwdflow-driver";
const STORE = "outbox";

export type OutboxItem = {
  client_request_id: string;
  action: string;
  target_id: number;
  label: string;
  created_at: string;
  fields: Record<string, string>;
  photo: Blob | null;
  state: "pending" | "failed";
  error?: string;
};

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "client_request_id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const request = work(db.transaction(STORE, mode).objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export const addItem = (item: OutboxItem) => run("readwrite", (s) => s.put(item));
export const removeItem = (id: string) => run("readwrite", (s) => s.delete(id));
export const listItems = () => run<OutboxItem[]>("readonly", (s) => s.getAll());

/** Xin trình duyệt giữ dữ liệu (iOS Safari hay xoá bộ nhớ của tab không dùng). Lỗi hay không hỗ trợ đều bỏ qua. */
export async function requestPersistence(): Promise<void> {
  try {
    await navigator.storage?.persist?.();
  } catch {
    /* không bắt buộc */
  }
}

export type SendResult = { ok: true } | { ok: false; retry: boolean; message: string };

/** Gửi một thao tác. Mất mạng hoặc chưa đăng nhập (401) thì `retry = true`; lỗi nghiệp vụ (400/404/409) thì không. */
export async function sendItem(item: OutboxItem): Promise<SendResult> {
  const body = new FormData();
  body.append("client_request_id", item.client_request_id);
  body.append("action", item.action);
  body.append("target_id", String(item.target_id));
  for (const [key, value] of Object.entries(item.fields)) if (value) body.append(key, value);
  if (item.photo) body.append("photo", item.photo, "photo.jpg");
  let response: Response;
  try {
    response = await fetch("/api/driver/actions", { method: "POST", body, credentials: "same-origin" });
  } catch {
    return { ok: false, retry: true, message: "Không kết nối được máy chủ" };
  }
  let envelope: { success: boolean; error?: { message: string } | null } | null = null;
  try {
    envelope = await response.json();
  } catch {
    return { ok: false, retry: true, message: "Máy chủ trả lời không đọc được" };
  }
  if (envelope?.success) return { ok: true };
  const retry = response.status === 401 || response.status >= 500;
  return { ok: false, retry, message: envelope?.error?.message ?? "Gửi không thành công" };
}

let flushing: Promise<number> | null = null;

/** Gửi mọi thao tác đang chờ theo thứ tự tạo; trả về số thao tác đã gửi xong. Gọi song song thì dùng chung một lượt. */
export function flushOutbox(): Promise<number> {
  flushing ??= (async () => {
    let sent = 0;
    const items = (await listItems()).filter((i) => i.state === "pending").sort((a, b) => a.created_at.localeCompare(b.created_at));
    for (const item of items) {
      const result = await sendItem(item);
      if (result.ok) {
        await removeItem(item.client_request_id);
        sent++;
      } else if (!result.retry) {
        await addItem({ ...item, state: "failed", error: result.message });
      } else {
        break; // mất mạng: dừng, giữ nguyên thứ tự cho lần sau
      }
    }
    return sent;
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}
