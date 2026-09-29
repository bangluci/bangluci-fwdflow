// Kiểu dữ liệu của `GET /api/shipments/{id}` và các phần con (khớp api/app/shipments/queries.py).

export type ShipmentItem = {
  id: number;
  line_no: number;
  description: string;
  quantity: string | number;
  unit: string | null;
  packages: number | null;
  gross_weight_kg: string | number | null;
  value_amount: number | null;
  value_currency: string | null;
  hs_code: string | null;
  hs_source: "manual" | "ai_accepted" | null;
};

export type Declaration = {
  id: number;
  declaration_no: string;
  type_code: string;
  registered_at: string;
  lane: "GREEN" | "YELLOW" | "RED" | null;
  cleared_at: string | null;
};

export type EventOut = {
  id: number;
  kind: string;
  occurred_at: string;
  recorded_at: string;
  actor_id: number | null;
  adjusts_event_id: number | null;
  reason: string | null;
};

export type ContainerDetail = {
  id: number;
  container_no: string;
  container_type: string;
  seal_no: string | null;
  gross_weight_kg: string | number | null;
  status: string | null;
  events: EventOut[];
  milestones: Record<string, { event_id: number; occurred_at: string }>;
};

export type ShipmentDetail = {
  id: number;
  code: string;
  load_type: "FCL" | "LCL";
  delivery_mode: "VIA_WAREHOUSE" | "CONTAINER_TO_DOOR";
  customer_id: number;
  customer_name: string;
  staff_id: number;
  carrier_id: number | null;
  pol_port_id: number | null;
  pod_port_id: number | null;
  dest_warehouse_id: number | null;
  mbl_no: string | null;
  hbl_no: string | null;
  vessel: string | null;
  voyage: string | null;
  etd: string | null;
  eta: string | null;
  claims_fta: boolean;
  do_no: string | null;
  do_valid_until: string | null;
  total_packages: number | null;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
  items: ShipmentItem[];
  declarations: Declaration[];
  containers: ContainerDetail[];
  events: (EventOut & { from_status: string | null; to_status: string | null })[];
  allowed_transitions: string[];
  in_transit_missing: string[];
};

export type ChecklistItem = { doc_type: string; label: string; required_from_status: string; present: boolean };
export type Checklist = { status: string; items: ChecklistItem[]; missing: string[] };

export const IN_TRANSIT_FIELD_LABEL: Record<string, string> = {
  bl_no: "số B/L (MBL hoặc HBL)",
  carrier_id: "hãng tàu",
  pol_port_id: "cảng xếp",
  pod_port_id: "cảng dỡ",
  eta: "ETA",
};
