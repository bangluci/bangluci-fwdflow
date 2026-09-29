import { Suspense } from "react";
import { LastMileBoard } from "./last-mile-board";

export default function LastMilePage() {
  return (
    <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
      <LastMileBoard />
    </Suspense>
  );
}
