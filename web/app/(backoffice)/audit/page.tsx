import { Suspense } from "react";
import { AuditView } from "./audit-view";

export default function AuditPage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
      <AuditView />
    </Suspense>
  );
}
