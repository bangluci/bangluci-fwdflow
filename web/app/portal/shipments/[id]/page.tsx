import { notFound } from "next/navigation";
import { PortalShipmentView } from "./portal-shipment";

export default async function PortalShipmentPage({ params }: PageProps<"/portal/shipments/[id]">) {
  const { id } = await params;
  const shipmentId = Number(id);
  if (!Number.isInteger(shipmentId) || shipmentId <= 0) notFound();
  return <PortalShipmentView id={shipmentId} />;
}
