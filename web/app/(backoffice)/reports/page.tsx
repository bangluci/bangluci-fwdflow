import { Suspense } from "react";
import { ReportsView } from "./reports-view";

export default function ReportsPage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
      <ReportsView />
    </Suspense>
  );
}
