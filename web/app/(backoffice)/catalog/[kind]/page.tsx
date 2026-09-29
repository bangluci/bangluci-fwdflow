import { notFound } from "next/navigation";
import { isCatalogKind } from "@/lib/catalog-kinds";
import { CatalogScreen } from "./catalog-screen";

export default async function CatalogPage({ params }: PageProps<"/catalog/[kind]">) {
  const { kind } = await params;
  if (!isCatalogKind(kind)) notFound();
  return <CatalogScreen kind={kind} />;
}
