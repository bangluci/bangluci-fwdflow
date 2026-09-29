import { deflateSync, crc32 } from "node:zlib";
import type { APIRequestContext } from "@playwright/test";
import { ACCOUNTS, api, createShipment, vnDate } from "./helpers";

let pixel = Date.now() % 200;

/** PNG 8×8 hợp lệ, mỗi lần gọi một màu khác (chứng từ trùng nội dung bị server từ chối). */
export function pngBytes(): Buffer {
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const out = Buffer.alloc(body.length + 8);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc32(body), body.length + 4);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(8, 0);
  header.writeUInt32BE(8, 4);
  header.set([8, 2, 0, 0, 0], 8); // 8 bit, RGB
  const value = ++pixel;
  const rows = Buffer.concat(Array.from({ length: 8 }, () => Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 24 }, (_, i) => (value * (i + 3)) % 256))])));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

export const photoFile = () => ({ name: "bang-chung.png", mimeType: "image/png", buffer: pngBytes() });

const LCL_DOCS = ["HBL", "INVOICE", "PACKING_LIST", "ARRIVAL_NOTICE", "CUSTOMS_DECLARATION", "DO"];

/**
 * Lô LCL giao qua kho đã ở trạng thái "Đã về kho" (hoặc "Đã thông quan" nếu `receive: false`) với `packages` kiện chưa tách (dựng đủ chứng từ, tờ khai thông quan,
 * nhận hàng tại kho bằng ảnh) — đi đúng đường của người dùng thật, cần context API của ADMIN.
 */
export async function createWarehouseLot(admin: APIRequestContext, packages: number, options: { receive?: boolean } = {}): Promise<{ id: number; code: string }> {
  const shipment = await createShipment(admin, { load_type: "LCL", delivery_mode: "VIA_WAREHOUSE", hbl_no: `H${Date.now()}`, total_packages: packages });
  await api(admin, "post", `/api/shipments/${shipment.id}/transition`, { to_status: "IN_TRANSIT" });
  for (const docType of LCL_DOCS) {
    const res = await admin.post(`/api/shipments/${shipment.id}/documents`, { multipart: { doc_type: docType, file: photoFile() } });
    if (!res.ok()) throw new Error(`Upload ${docType}: ${await res.text()}`);
  }
  await api(admin, "post", `/api/shipments/${shipment.id}/customs-declarations`, {
    declaration_no: String(Date.now()).slice(-12), type_code: "A11", registered_at: `${vnDate(1)}T09:00:00+07:00`, cleared_at: `${vnDate(0)}T00:30:00+07:00`,
  });
  await api(admin, "post", `/api/shipments/${shipment.id}/transition`, { to_status: "CUSTOMS_CLEARING" });
  await api(admin, "post", `/api/shipments/${shipment.id}/transition`, { to_status: "CLEARED" });
  if (options.receive === false) return shipment; // dừng ở "Đã thông quan" để test nhận hàng qua UI
  const received = await admin.post(`/api/shipments/${shipment.id}/receive-at-warehouse`, { multipart: { photo: photoFile(), note: "nhận đủ kiện" } });
  if (!received.ok()) throw new Error(`Nhận hàng: ${await received.text()}`);
  return shipment;
}

export interface AssignedOrder { id: number; trackingCode: string; recipient: string; shipmentId: number }

/** Một đơn giao 1 kiện hẹn hôm nay, đã gán cho tài xế đăng nhập trong e2e (ACCOUNTS.DRIVER); dựng bằng quyền ADMIN. */
export async function createAssignedOrder(admin: APIRequestContext, recipient: string): Promise<AssignedOrder> {
  const lot = await createWarehouseLot(admin, 1);
  const drivers = await api<{ id: number; phone: string | null }[]>(admin, "get", "/api/catalog/drivers?active=true");
  const driver = drivers.find((d) => d.phone === ACCOUNTS.DRIVER);
  if (!driver) throw new Error("Không thấy tài xế e2e: chạy lại seed_demo --reset");
  await api(admin, "post", `/api/shipments/${lot.id}/last-mile-orders`, {
    orders: [{ recipient_name: recipient, recipient_phone: "0901234567", address: "12 Lê Lợi, Quận 1, TP.HCM", packages: 1, weight_kg: null, planned_date: vnDate(0), driver_id: driver.id }],
  });
  const rows = await api<{ id: number; tracking_code: string }[]>(admin, "get", `/api/last-mile-orders?shipment_id=${lot.id}`);
  return { id: rows[0].id, trackingCode: rows[0].tracking_code, recipient, shipmentId: lot.id };
}
