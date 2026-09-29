import { Suspense } from "react";
import { FreeTimeBoard } from "./freetime-board";

export default function FreeTimePage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
      <FreeTimeBoard />
    </Suspense>
  );
}
