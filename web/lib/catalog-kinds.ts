// Bảy loại danh mục dùng chung một màn. Quy tắc kiểm tra khớp với schema của API (api/app/catalog/schemas.py).

export type FieldType = "text" | "textarea" | "aliases" | "ref";

export type CatalogField = {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  /** Với `ref`: danh mục được chọn (ví dụ `customers`). */
  refKind?: CatalogKind;
  hint?: string;
};

export const CATALOG_KIND_KEYS = ["customers", "carriers", "ports", "warehouses", "truckers", "trucks", "drivers"] as const;
export type CatalogKind = (typeof CATALOG_KIND_KEYS)[number];

export type CatalogConfig = {
  label: string;
  singular: string;
  /** Quyền ghi trong `GET /api/auth/me` → permissions. */
  writeAction: "catalog.commercial.write" | "catalog.transport.write";
  fields: CatalogField[];
  /** Cột hiện trong bảng (theo thứ tự); chỉ dùng tên trường. */
  columns: string[];
  searchHint: string;
};

export const CATALOG_KINDS: Record<CatalogKind, CatalogConfig> = {
  customers: {
    label: "Khách hàng",
    singular: "khách hàng",
    writeAction: "catalog.commercial.write",
    fields: [
      { name: "name", label: "Tên khách hàng", type: "text", required: true },
      { name: "tax_code", label: "Mã số thuế", type: "text" },
      { name: "email", label: "Email nhận nhắc hạn", type: "text", hint: "Có email thì khách nhận thư nhắc free time" },
      { name: "phone", label: "Số điện thoại", type: "text" },
      { name: "address", label: "Địa chỉ", type: "textarea" },
    ],
    columns: ["name", "tax_code", "email", "phone"],
    searchHint: "Tìm theo tên, mã số thuế, email",
  },
  carriers: {
    label: "Hãng tàu",
    singular: "hãng tàu",
    writeAction: "catalog.commercial.write",
    fields: [
      { name: "code", label: "Mã (SCAC)", type: "text", required: true, hint: "Ví dụ MAEU, REGU" },
      { name: "name", label: "Tên hãng tàu", type: "text", required: true },
    ],
    columns: ["code", "name"],
    searchHint: "Tìm theo mã hoặc tên",
  },
  ports: {
    label: "Cảng",
    singular: "cảng",
    writeAction: "catalog.commercial.write",
    fields: [
      { name: "code", label: "Mã UN/LOCODE", type: "text", required: true, hint: "5 chữ cái, ví dụ VNSGN" },
      { name: "name", label: "Tên cảng", type: "text", required: true },
      { name: "aliases", label: "Tên gọi khác", type: "aliases", hint: "Cách nhau bằng dấu phẩy, ví dụ VNCLI, CAT LAI" },
    ],
    columns: ["code", "name", "aliases"],
    searchHint: "Tìm theo mã hoặc tên",
  },
  warehouses: {
    label: "Kho",
    singular: "kho",
    writeAction: "catalog.transport.write",
    fields: [
      { name: "name", label: "Tên kho", type: "text", required: true },
      { name: "address", label: "Địa chỉ", type: "textarea", required: true },
      { name: "customer_id", label: "Kho của khách", type: "ref", refKind: "customers", hint: "Để trống nếu là kho công ty" },
    ],
    columns: ["name", "address", "customer_id"],
    searchHint: "Tìm theo tên hoặc địa chỉ",
  },
  truckers: {
    label: "Nhà xe",
    singular: "nhà xe",
    writeAction: "catalog.transport.write",
    fields: [
      { name: "name", label: "Tên nhà xe", type: "text", required: true },
      { name: "phone", label: "Số điện thoại", type: "text" },
    ],
    columns: ["name", "phone"],
    searchHint: "Tìm theo tên hoặc số điện thoại",
  },
  trucks: {
    label: "Xe",
    singular: "xe",
    writeAction: "catalog.transport.write",
    fields: [
      { name: "trucker_id", label: "Nhà xe", type: "ref", refKind: "truckers", required: true },
      { name: "plate_no", label: "Biển số", type: "text", required: true, hint: "Ví dụ 51C-12345" },
    ],
    columns: ["plate_no", "trucker_id"],
    searchHint: "Tìm theo biển số",
  },
  drivers: {
    label: "Tài xế",
    singular: "tài xế",
    writeAction: "catalog.transport.write",
    fields: [
      { name: "trucker_id", label: "Nhà xe", type: "ref", refKind: "truckers", required: true },
      { name: "full_name", label: "Họ và tên", type: "text", required: true },
      { name: "phone", label: "Số điện thoại", type: "text" },
    ],
    columns: ["full_name", "phone", "trucker_id"],
    searchHint: "Tìm theo tên hoặc số điện thoại",
  },
};

export const isCatalogKind = (value: string): value is CatalogKind => (CATALOG_KIND_KEYS as readonly string[]).includes(value);

export type CatalogItem = { id: number; active: boolean; [field: string]: unknown };
export type FormValues = Record<string, string>;

/** Giá trị form (toàn chuỗi) → payload gửi API: rỗng thành null, `aliases` thành mảng, `ref` thành số. */
export function toPayload(config: CatalogConfig, values: FormValues): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of config.fields) {
    const raw = (values[field.name] ?? "").trim();
    if (field.type === "aliases") payload[field.name] = raw ? raw.split(",").map((a) => a.trim()).filter(Boolean) : [];
    else if (field.type === "ref") payload[field.name] = raw ? Number(raw) : null;
    else payload[field.name] = raw || null;
  }
  return payload;
}

/** Bản ghi API → giá trị form (chuỗi). */
export function toFormValues(config: CatalogConfig, item?: CatalogItem): FormValues {
  const values: FormValues = {};
  for (const field of config.fields) {
    const value = item?.[field.name];
    values[field.name] = Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value);
  }
  return values;
}

/** Trường bắt buộc còn trống → thông báo lỗi theo từng trường. */
export function validateRequired(config: CatalogConfig, values: FormValues): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const field of config.fields) {
    if (field.required && !(values[field.name] ?? "").trim()) errors[field.name] = "Bắt buộc nhập";
  }
  return errors;
}
