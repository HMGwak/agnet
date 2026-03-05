import type { TaskStatus } from "@/lib/types";

const STATUS_COLORS: Record<TaskStatus, string> = {
  PENDING: "bg-gray-100 text-gray-700",
  PREPARING_WORKSPACE: "bg-blue-100 text-blue-700",
  PLANNING: "bg-blue-100 text-blue-700",
  AWAIT_PLAN_APPROVAL: "bg-yellow-100 text-yellow-700",
  IMPLEMENTING: "bg-blue-100 text-blue-700",
  TESTING: "bg-blue-100 text-blue-700",
  AWAIT_MERGE_APPROVAL: "bg-yellow-100 text-yellow-700",
  MERGING: "bg-blue-100 text-blue-700",
  DONE: "bg-green-100 text-green-700",
  FAILED: "bg-red-100 text-red-700",
  CANCELLED: "bg-gray-100 text-gray-500",
};

const STATUS_LABELS: Record<TaskStatus, string> = {
  PENDING: "Pending",
  PREPARING_WORKSPACE: "Preparing",
  PLANNING: "Planning",
  AWAIT_PLAN_APPROVAL: "Plan Review",
  IMPLEMENTING: "Implementing",
  TESTING: "Testing",
  AWAIT_MERGE_APPROVAL: "Merge Review",
  MERGING: "Merging",
  DONE: "Done",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
