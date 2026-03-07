"use client";

import { use } from "react";
import { TaskDetailContent } from "@/components/TaskDetailContent";

export default function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <TaskDetailContent taskId={Number(id)} />;
}
