import { notFound } from "next/navigation";
import { TaskScreen } from "./task-screen";

export default async function DriverTaskPage({ params }: PageProps<"/driver/task/[kind]/[id]">) {
  const { kind, id } = await params;
  const taskId = Number(id);
  if ((kind !== "trucking" && kind !== "last-mile") || !Number.isInteger(taskId) || taskId <= 0) notFound();
  return <TaskScreen kind={kind} id={taskId} />;
}
