import type { TaskSummary } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatSchedule(dateStr: string): string {
  return new Date(dateStr).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TaskCard({
  task,
  onClick,
}: {
  task: TaskSummary;
  onClick?: (taskId: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick?.(task.id)}
      className="w-full text-left bg-white rounded-lg border border-gray-200 p-3 hover:shadow-md transition-shadow cursor-pointer"
    >
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-medium text-gray-900 line-clamp-2">
            {task.title}
          </h3>
          <span className="text-xs text-gray-400 shrink-0">#{task.id}</span>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <StatusBadge status={task.status} />
          <span className="text-xs text-gray-400">{timeAgo(task.created_at)}</span>
        </div>
        {(task.scheduled_for || task.blocked_by_task_id) && (
          <div className="mt-2 space-y-1 text-[11px] text-gray-500">
            {task.scheduled_for && (
              <div className="rounded bg-slate-50 px-2 py-1">
                Start at {formatSchedule(task.scheduled_for)}
              </div>
            )}
            {task.blocked_by_task_id && (
              <div className="rounded bg-slate-50 px-2 py-1">
                After #{task.blocked_by_task_id}
                {task.blocked_by_title ? ` ${task.blocked_by_title}` : ""}
              </div>
            )}
          </div>
        )}
    </button>
  );
}
