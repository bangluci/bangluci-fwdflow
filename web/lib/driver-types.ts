export type DriverAction = { action: string; label: string; requires: ("photo" | "signer_name" | "reason")[] };

export type TruckingTask = {
  kind: "TRUCKING";
  id: number;
  order_kind: "PICKUP_FULL" | "RETURN_EMPTY";
  title: string;
  status: string;
  planned_at: string;
  shipment_code: string;
  container_no: string;
  container_type: string;
  seal_no: string | null;
  pickup_location: string;
  drop_location: string;
  delivery_mode: string;
  actions: DriverAction[];
};

export type LastMileTask = {
  kind: "LAST_MILE";
  id: number;
  status: string;
  planned_date: string;
  tracking_code: string;
  shipment_code: string;
  recipient_name: string;
  recipient_phone: string;
  address: string;
  packages: number;
  weight_kg: string | null;
  actions: DriverAction[];
};

export type DriverTask = TruckingTask | LastMileTask;
export const taskPath = (task: DriverTask) => `/driver/task/${task.kind === "TRUCKING" ? "trucking" : "last-mile"}/${task.id}`;
