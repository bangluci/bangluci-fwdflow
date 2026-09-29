import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, request as pwRequest, type APIRequestContext, type Page } from "@playwright/test";

export type Role = "ADMIN" | "DOCS" | "DISPATCH" | "ACCOUNTANT" | "CUSTOMER" | "DRIVER";

// Tài khoản seed (api/scripts/seed_demo.py); mật khẩu là SEED_PASSWORD trong .env ở gốc repo (hoặc biến môi trường).
export const ACCOUNTS: Record<Role, string> = {
  ADMIN: "admin@fwdflow.local",
  DOCS: "docs@fwdflow.local",
  DISPATCH: "dispatch@fwdflow.local",
  ACCOUNTANT: "accountant@fwdflow.local",
  CUSTOMER: "customer@fwdflow.local",
  DRIVER: "0900000006",
};

export function seedPassword(): string {
  if (process.env.SEED_PASSWORD) return process.env.SEED_PASSWORD;
  const env = readFileSync(resolve(__dirname, "../../.env"), "utf8");
  const line = env.split(/\r?\n/).find((l) => l.startsWith("SEED_PASSWORD="));
  if (!line) throw new Error("Đặt SEED_PASSWORD trong .env");
  return line.slice("SEED_PASSWORD=".length).trim();
}

/** File phiên đã đăng nhập sẵn của một vai trò (tạo bởi global-setup); dùng `test.use({ storageState: authFile(role) })`. */
export const authFile = (role: Role) => `e2e/.auth/${role}.json`;

/** Đăng nhập bằng API; cookie phiên nằm trong context của trang. Chỉ dùng khi cần đổi vai trò giữa test. */
export async function apiLogin(request: APIRequestContext, role: Role): Promise<void> {
  const res = await request.post("/api/auth/login", { data: { identifier: ACCOUNTS[role], password: seedPassword() } });
  expect(res.ok(), `đăng nhập ${role}`).toBeTruthy();
}

/** Đăng nhập qua form thật. */
export async function loginAs(page: Page, role: Role): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email hoặc số điện thoại").fill(ACCOUNTS[role]);
  await page.getByLabel("Mật khẩu").fill(seedPassword());
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

export async function api<T = unknown>(request: APIRequestContext, method: "get" | "post" | "patch" | "put" | "delete", path: string, data?: unknown): Promise<T> {
  const res = await request[method](path, data === undefined ? undefined : { data });
  const body = await res.json();
  expect(body.success, `${method.toUpperCase()} ${path}: ${JSON.stringify(body.error)}`).toBeTruthy();
  return body.data as T;
}

let counter = 0;
/** Chuỗi duy nhất trong một lần chạy (tránh trùng mã giữa các test). */
export const unique = (prefix: string) => `${prefix}${Date.now().toString(36).toUpperCase()}${++counter}`;

/** Số container ISO 6346 hợp lệ với tiền tố 4 chữ cái + số thứ tự 6 chữ số. */
export function containerNo(prefix: string, serial: number): string {
  const body = `${prefix}${String(serial).padStart(6, "0")}`;
  const values = Object.fromEntries("0123456789A?BCDEFGHIJK?LMNOPQRSTU?VWXYZ".split("").map((ch, i) => [ch, i]));
  const total = body.split("").reduce((sum, ch, i) => sum + values[ch] * 2 ** i, 0);
  return body + String((total % 11) % 10);
}

/** Tạo lô FCL tối thiểu (cần đã đăng nhập DOCS hoặc ADMIN) và trả `{id, code}`. */
export async function createShipment(request: APIRequestContext, extra: Record<string, unknown> = {}): Promise<{ id: number; code: string }> {
  const customers = await api<{ id: number }[]>(request, "get", "/api/catalog/customers?active=true");
  const ports = await api<{ id: number; code: string }[]>(request, "get", "/api/catalog/ports?active=true");
  const carriers = await api<{ id: number }[]>(request, "get", "/api/catalog/carriers?active=true");
  return api(request, "post", "/api/shipments", {
    load_type: "FCL", delivery_mode: "VIA_WAREHOUSE", customer_id: customers[0].id, carrier_id: carriers[0].id,
    pol_port_id: ports.find((p) => p.code === "CNSHA")?.id, pod_port_id: ports.find((p) => p.code === "VNSGN")?.id,
    mbl_no: unique("E2E-"), eta: new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10), ...extra,
  });
}

/** Context API đã đăng nhập sẵn cho một vai trò (dùng để dựng dữ liệu bằng quyền khác với người đang thao tác trên UI). */
export async function apiAs(role: Role): Promise<APIRequestContext> {
  return pwRequest.newContext({ baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8088", storageState: authFile(role) });
}

/** Ngày `YYYY-MM-DD` theo giờ Việt Nam, lùi `daysAgo` ngày. */
export function vnDate(daysAgo = 0): string {
  const formatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" });
  return formatter.format(new Date(Date.now() - daysAgo * 86_400_000));
}

let containerSerial = Math.floor(Date.now() % 900_000);
export const nextContainerNo = () => containerNo("TSTU", ++containerSerial);

/**
 * Lô FCL đã tới ARRIVED có một container 40HC được dỡ `daysAgo` ngày trước (00:01 giờ VN để không vượt giờ server).
 * Hãng tàu / cảng dỡ lấy theo `createShipment`, nên dùng quy tắc free time của seed (DEM free 5 ngày, DET free 7 ngày).
 */
export async function createFreetimeCase(request: APIRequestContext, daysAgo: number): Promise<{ id: number; code: string; containerNo: string }> {
  const shipment = await createShipment(request);
  await api(request, "post", `/api/shipments/${shipment.id}/transition`, { to_status: "IN_TRANSIT" });
  await api(request, "post", `/api/shipments/${shipment.id}/transition`, { to_status: "ARRIVED" });
  const number = nextContainerNo();
  const container = await api<{ id: number }>(request, "post", `/api/shipments/${shipment.id}/containers`, { container_no: number, container_type: "40HC" });
  await api(request, "post", `/api/containers/${container.id}/events`, { kind: "DISCHARGED", occurred_at: `${vnDate(daysAgo)}T00:01:00+07:00` });
  return { ...shipment, containerNo: number };
}
