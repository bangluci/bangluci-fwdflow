import type { Metadata } from "next";
import { TrackView } from "./[code]/track-view";

export const metadata: Metadata = { title: "Tra cứu vận đơn", robots: { index: false, follow: false } };

export default function TrackHome() {
  return <TrackView code="" />;
}
