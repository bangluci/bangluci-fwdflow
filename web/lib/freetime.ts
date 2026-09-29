// Kiểu dữ liệu và cách diễn đạt đồng hồ free time (khớp `GET /api/freetime/containers`).

export type FreeTimeRow = {
  container_id: number;
  container_no: string;
  container_type: string;
  shipment_id: number;
  shipment_code: string;
  shipment_status: string;
  customer_name: string;
  carrier_name: string | null;
  pod_code: string | null;
  fee_type: "DEM" | "DET" | "COMBINED";
  rule_source: "OVERRIDE" | "RULE" | "NONE";
  status: "NOT_STARTED" | "OPEN" | "CLOSED" | "NO_RULE" | "MISSING_DATA";
  level: "GREEN" | "YELLOW" | "RED" | "NO_RULE" | "MISSING_DATA" | null;
  container_level: string | null;
  discharged_date: string | null;
  gate_out_date: string | null;
  returned_date: string | null;
  start_date: string | null;
  end_date: string | null;
  free_days: number | null;
  due_date: string | null;
  days_used: number | null;
  days_left: number | null;
  days_over: number | null;
  fee_amount: number | null;
  fee_currency: string | null;
};

export const FEE_TYPE_LABEL = { DEM: "DEM (lưu cont)", DET: "DET (lưu vỏ)", COMBINED: "Gộp DEM+DET" } as const;
export const FEE_TYPE_SHORT = { DEM: "DEM", DET: "DET", COMBINED: "D&D" } as const;
export const LEVEL_FILTER_LABEL: Record<string, string> = {
  RED: "Quá hạn",
  YELLOW: "Sắp hạn",
  GREEN: "An toàn",
  NO_RULE: "Chưa có quy tắc",
  MISSING_DATA: "Thiếu ngày dỡ hàng",
};
