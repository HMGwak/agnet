import type { TaskStatus, TaskSummary } from "@/lib/types";
import { formatKSTDateTime, parseBackendTimestamp } from "@/lib/time";
import { StatusBadge } from "./StatusBadge";

function parseTimestamp(dateStr: string): number {
  return parseBackendTimestamp(dateStr);
}

function formatRelativeTime(dateStr: string, now: number): string {
  const diffMs = Math.max(0, now - parseTimestamp(dateStr));
  const minutes = Math.floor(diffMs / 60000);

  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    if (remainingMinutes === 0) return `${hours}h ago`;
    return `${hours}h ${remainingMinutes}m ago`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  if (remainingHours === 0) return `${days}d ago`;
  return `${days}d ${remainingHours}h ago`;
}

function formatElapsedTime(start: string, endMs: number): string {
  const diffMs = Math.max(0, endMs - parseTimestamp(start));
  const totalMinutes = Math.floor(diffMs / 60000);

  if (totalMinutes < 1) return "< 1m";
  if (totalMinutes < 60) return `${totalMinutes}m`;

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours < 24) {
    return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours === 0 ? `${days}d` : `${days}d ${remainingHours}h`;
}

function isTerminalStatus(status: TaskStatus): boolean {
  return ["DONE", "FAILED", "CANCELLED", "NEEDS_ATTENTION"].includes(status);
}

function formatSchedule(dateStr: string): string {
  return formatKSTDateTime(dateStr, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TaskCard({
  task,
  now,
  onClick,
}: {
  task: TaskSummary;
  now: number;
  onClick?: (taskId: number) => void;
}) {
  const endTime = isTerminalStatus(task.status) ? parseTimestamp(task.updated_at) : now;

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
          <span className="text-xs text-gray-400">{formatRelativeTime(task.created_at, now)}</span>
        </div>
        {task.workspace_name && (
          <div className="mt-2 text-[11px] text-slate-500">
            {task.workspace_name}
            {task.workspace_kind ? ` · ${task.workspace_kind}` : ""}
          </div>
        )}
        <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500">
          <span>Started {formatSchedule(task.created_at)}</span>
          <span>Elapsed {formatElapsedTime(task.created_at, endTime)}</span>
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
