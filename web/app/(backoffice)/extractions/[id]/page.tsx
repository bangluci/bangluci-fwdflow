import { notFound } from "next/navigation";
import { ReviewScreen } from "./review-screen";

export default async function ExtractionPage({ params }: PageProps<"/extractions/[id]">) {
  const { id } = await params;
  const extractionId = Number(id);
  if (!Number.isInteger(extractionId) || extractionId <= 0) notFound();
  return <ReviewScreen id={extractionId} />;
}
