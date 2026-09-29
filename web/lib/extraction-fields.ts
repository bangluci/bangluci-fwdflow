// Các trường của kết quả AI đọc chứng từ, theo loại chứng từ (khớp api/app/ai/extraction/schemas.py).

export type FieldDef = { name: string; label: string; kind?: "text" | "number" | "date"; risky?: boolean };
export type ListDef = { name: string; label: string; columns: FieldDef[] };

export type Issue = { path: string; code: string; level: "BLOCK" | "WARN"; message: string };

const BL_SCALARS: FieldDef[] = [
  { name: "bl_no", label: "Số B/L", risky: true }, { name: "carrier_name", label: "Hãng tàu" }, { name: "shipper", label: "Người gửi" },
  { name: "consignee", label: "Người nhận" }, { name: "notify_party", label: "Bên nhận thông báo" }, { name: "vessel", label: "Tàu" },
  { name: "voyage", label: "Chuyến" }, { name: "pol", label: "Cảng xếp", risky: true }, { name: "pod", label: "Cảng dỡ", risky: true },
  { name: "onboard_date", label: "Ngày xếp lên tàu", kind: "date" }, { name: "total_packages", label: "Tổng số kiện", kind: "number" },
  { name: "package_unit", label: "Đơn vị kiện" }, { name: "gross_weight_kg", label: "Tổng khối lượng (kg)", kind: "number" },
];

export const FIELDS_BY_TYPE: Record<string, { scalars: FieldDef[]; lists: ListDef[] }> = {
  MBL: {
    scalars: BL_SCALARS,
    lists: [{ name: "containers", label: "Container", columns: [
      { name: "container_no", label: "Số container", risky: true }, { name: "seal_no", label: "Seal", risky: true },
      { name: "container_type_raw", label: "Loại (nguyên văn)" }, { name: "container_type", label: "Loại" },
      { name: "packages", label: "Kiện", kind: "number" }, { name: "gross_weight_kg", label: "KL (kg)", kind: "number" },
    ] }],
  },
  INVOICE: {
    scalars: [
      { name: "invoice_no", label: "Số hoá đơn" }, { name: "invoice_date", label: "Ngày hoá đơn", kind: "date" }, { name: "seller", label: "Người bán" },
      { name: "buyer", label: "Người mua" }, { name: "currency", label: "Tiền tệ" }, { name: "incoterm", label: "Incoterm" },
      { name: "total_amount", label: "Tổng tiền", kind: "number" },
    ],
    lists: [{ name: "lines", label: "Dòng hàng", columns: [
      { name: "description", label: "Mô tả" }, { name: "quantity", label: "SL", kind: "number" }, { name: "unit", label: "ĐVT" },
      { name: "unit_price", label: "Đơn giá", kind: "number" }, { name: "amount", label: "Thành tiền", kind: "number" },
    ] }],
  },
  PACKING_LIST: {
    scalars: [
      { name: "packing_list_no", label: "Số packing list" }, { name: "date", label: "Ngày", kind: "date" }, { name: "total_packages", label: "Tổng số kiện", kind: "number" },
      { name: "total_gross_weight_kg", label: "Tổng KL cả bì (kg)", kind: "number" }, { name: "total_net_weight_kg", label: "Tổng KL tịnh (kg)", kind: "number" },
    ],
    lists: [
      { name: "lines", label: "Dòng hàng", columns: [
        { name: "description", label: "Mô tả" }, { name: "packages", label: "Kiện", kind: "number" }, { name: "quantity", label: "SL", kind: "number" },
        { name: "unit", label: "ĐVT" }, { name: "gross_weight_kg", label: "KL cả bì", kind: "number" }, { name: "net_weight_kg", label: "KL tịnh", kind: "number" },
      ] },
      { name: "containers", label: "Container", columns: [{ name: "container_no", label: "Số container", risky: true }, { name: "seal_no", label: "Seal", risky: true }] },
    ],
  },
};
FIELDS_BY_TYPE.HBL = FIELDS_BY_TYPE.MBL;

export const EXTRACTION_STATUS_LABEL: Record<string, string> = {
  PENDING: "Đang chờ đọc",
  PROCESSING: "Đang đọc chứng từ",
  REVIEW: "Chờ duyệt",
  APPROVED: "Đã duyệt",
  REJECTED: "Đã từ chối",
  FAILED: "Đọc lỗi",
  CANCELLED: "Đã huỷ",
};
