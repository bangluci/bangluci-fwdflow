export type LastMileOrderRow = {
  id: number;
  shipment_id: number;
  shipment_code: string;
  tracking_code: string;
  recipient_name: string;
  recipient_phone: string;
  address: string;
  packages: number;
  weight_kg: string | null;
  driver_id: number | null;
  driver_name: string | null;
  planned_date: string;
  status: string;
};

export type LastMileEventOut = {
  id: number;
  kind: string;
  occurred_at: string;
  actor_id: number | null;
  actor_name: string | null;
  reason: string | null;
  lat: string | null;
  lng: string | null;
  has_photo: boolean;
  voided: boolean;
};

export type LastMileDetail = LastMileOrderRow & { events: LastMileEventOut[] };
export type PoolMeta = { total_packages: number | null; packages_available: number };

/** `DEM00TRACK` → `DEM00-TRACK`. */
export const formatCode = (code: string) => `${code.slice(0, 5)}-${code.slice(5)}`;
