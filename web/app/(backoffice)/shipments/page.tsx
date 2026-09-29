import { Suspense } from "react";
import { ShipmentList } from "./shipment-list";

export default function ShipmentsPage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
      <ShipmentList />
    </Suspense>
  );
}
