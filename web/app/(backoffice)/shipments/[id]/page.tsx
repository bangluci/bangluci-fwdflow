import { notFound } from "next/navigation";
import { ShipmentDetail } from "./shipment-detail";

export default async function ShipmentPage({ params }: PageProps<"/shipments/[id]">) {
  const { id } = await params;
  const shipmentId = Number(id);
  if (!Number.isInteger(shipmentId) || shipmentId <= 0) notFound();
  return <ShipmentDetail id={shipmentId} />;
}
