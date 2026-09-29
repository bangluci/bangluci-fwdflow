"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ShipmentStatusBadge } from "@/components/shipment-status";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, apiFetch } from "@/lib/api";
import { DELIVERY_MODE_LABEL } from "@/lib/shipment-labels";
import type { ShipmentDetail as Detail } from "@/lib/shipment-types";
import { useMe } from "@/lib/use-me";
import { ChargesTab } from "./charges-tab";
import { ContainersTab } from "./containers-tab";
import { DeclarationsTab } from "./declarations-tab";
import { DocumentsTab } from "./documents-tab";
import { FreeTimeTab } from "./freetime-tab";
import { InfoTab } from "./info-tab";
import { ItemsTab } from "./items-tab";
import { SidePanel, type TabKey } from "./side-panel";
import { StatusActions } from "./status-actions";
import { TimelineTab } from "./timeline-tab";

export function ShipmentDetail({ id }: { id: number }) {
  const { data: me } = useMe();
  const [tab, setTab] = useState<TabKey>("info");
  const query = useQuery({ queryKey: ["shipment", id], queryFn: () => apiFetch<Detail>(`/api/shipments/${id}`) });

  if (query.error instanceof ApiError && query.error.status === 404) {
    return (
      <div role="alert" className="mx-auto max-w-md space-y-3 rounded-lg border bg-card p-10 text-center">
        <p className="font-medium">Không tìm thấy lô hàng</p>
        <Button asChild variant="outline"><Link href="/shipments">Về danh sách lô</Link></Button>
      </div>
    );
  }
  if (query.error) {
    return (
      <div role="alert" className="mx-auto max-w-md space-y-3 rounded-lg border bg-card p-10 text-center">
        <p className="text-sm">{query.error.message}</p>
        <Button variant="outline" onClick={() => query.refetch()}>Thử lại</Button>
      </div>
    );
  }
  const shipment = query.data;
  if (!shipment || !me) return <p className="text-muted-foreground">Đang tải…</p>;

  const can = (action: string) => me.permissions.includes(action);
  const fcl = shipment.load_type === "FCL";
  const closed = shipment.status === "CANCELLED";
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <Link href="/shipments" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-3.5" aria-hidden />
          Lô hàng
        </Link>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h2 className="font-mono text-xl font-semibold tracking-tight">{shipment.code}</h2>
          <ShipmentStatusBadge status={shipment.status} />
          <StatusBadge tone="neutral" icon={undefined}>{shipment.load_type} · {DELIVERY_MODE_LABEL[shipment.delivery_mode]}</StatusBadge>
          <span className="text-sm text-muted-foreground">{shipment.customer_name}</span>
          <div className="ml-auto">
            <StatusActions shipment={shipment} canWrite={can("shipment.write")} />
          </div>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)} className="min-w-0">
          <TabsList className="h-auto flex-wrap justify-start">
            <TabsTrigger value="info">Thông tin</TabsTrigger>
            <TabsTrigger value="items">Dòng hàng</TabsTrigger>
            <TabsTrigger value="declarations">Tờ khai</TabsTrigger>
            {fcl && <TabsTrigger value="containers">Container</TabsTrigger>}
            <TabsTrigger value="documents">Chứng từ</TabsTrigger>
            {fcl && <TabsTrigger value="freetime">Free time</TabsTrigger>}
            {can("finance.read") && <TabsTrigger value="charges">Tài chính</TabsTrigger>}
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
          </TabsList>
          <TabsContent value="info"><InfoTab shipment={shipment} canWrite={can("shipment.write")} /></TabsContent>
          <TabsContent value="items"><ItemsTab shipment={shipment} canWrite={can("shipment.write")} /></TabsContent>
          <TabsContent value="declarations"><DeclarationsTab shipment={shipment} canWrite={can("shipment.write")} /></TabsContent>
          {fcl && <TabsContent value="containers"><ContainersTab shipment={shipment} canWrite={can("shipment.write")} canMilestone={can("container.milestone")} /></TabsContent>}
          <TabsContent value="documents">
            <DocumentsTab shipmentId={shipment.id} canWrite={can("document.write")} canReview={can("extraction.review")} closed={closed} />
          </TabsContent>
          {fcl && <TabsContent value="freetime"><FreeTimeTab shipmentId={shipment.id} canWrite={can("freetime.write")} /></TabsContent>}
          {can("finance.read") && <TabsContent value="charges"><ChargesTab shipmentId={shipment.id} /></TabsContent>}
          <TabsContent value="timeline"><TimelineTab shipment={shipment} /></TabsContent>
        </Tabs>
        <SidePanel shipment={shipment} canReview={can("extraction.review")} onGoto={setTab} />
      </div>
    </div>
  );
}
