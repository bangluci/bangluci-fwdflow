import type { Metadata } from "next";
import { TrackView } from "./track-view";

export const metadata: Metadata = { title: "Tra cứu vận đơn", robots: { index: false, follow: false } };

export default async function TrackPage({ params }: PageProps<"/track/[code]">) {
  const { code } = await params;
  return <TrackView code={decodeURIComponent(code)} />;
}
