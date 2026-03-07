"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { ArrowLeft, Loader2, Trash2, XCircle } from "lucide-react";
import { useTask } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cancelTask, deleteTask, resumeTask } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { PlanApproval } from "@/components/PlanApproval";
import { MergeApproval } from "@/components/MergeApproval";
import { DiffViewer } from "@/components/DiffViewer";
import { LogStream } from "@/components/LogStream";
import { formatKSTDateTime } from "@/lib/time";

type Props = {
  taskId: number;
  showBackLink?: boolean;
  className?: string;
  onDeleted?: () => void;
};

export function TaskDetailContent({
  taskId,
  showBackLink = true,
  className = "max-w-4xl space-y-6",
  onDeleted,
}: Props) {
  const router = useRouter();
  const { mutate: mutateCache } = useSWRConfig();
  const { data: task, error, isLoading, mutate } = useTask(taskId);
  const [cancelling, setCancelling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [followUpComment, setFollowUpComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  useWebSocket(taskId, (msg) => {
    if (msg.type === "task_state_changed") {
      mutate();
    }
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    );
  }

  if (error || !task) {
    return <div className="text-red-500 p-4">Failed to load task.</div>;
  }

  const canCancel = !["DONE", "CANCELLED"].includes(task.status);
  const canResume = ["NEEDS_ATTENTION", "FAILED", "CANCELLED"].includes(task.status);
  const canDelete = task.status === "CANCELLED";

  function formatSchedule(dateStr: string) {
    return formatKSTDateTime(dateStr);
  }

  async function handleCancel() {
    setCancelling(true);
    setActionError(null);
    try {
      await cancelTask(taskId);
      mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to cancel task.");
    } finally {
      setCancelling(false);
    }
  }

  async function handleResume() {
    setResuming(true);
    setActionError(null);
    try {
      await resumeTask(taskId, { comment: followUpComment.trim() || undefined });
      setFollowUpComment("");
      mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to requeue task.");
    } finally {
      setResuming(false);
    }
  }

  async function handleDelete() {
    const currentTask = task;
    if (!currentTask) {
      return;
    }
    setDeleting(true);
    setActionError(null);
    try {
      let deleteWorkspaceToo = false;
      if (currentTask.workspace_kind === "FEATURE" && currentTask.workspace_task_count === 1) {
        deleteWorkspaceToo = window.confirm(
          `This is the last task in workspace "${currentTask.workspace_name}".\n\nDelete the workspace too?`
        );
      }
      await deleteTask(taskId, {
        delete_workspace_if_empty: deleteWorkspaceToo,
      });
      await mutateCache((key: unknown) => Array.isArray(key) && key[0] === "tasks");
      await mutateCache((key: unknown) => Array.isArray(key) && key[0] === "workspaces");
      await mutateCache(["task", taskId], undefined, { revalidate: false });
      onDeleted?.();
      if (!onDeleted) {
        router.push("/tasks");
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete task.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className={className}>
      <div>
        {showBackLink && (
          <Link
            href="/tasks"
            className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-3"
          >
            <ArrowLeft size={14} />
            Back to board
          </Link>
        )}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{task.title}</h1>
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              <StatusBadge status={task.status} />
              <span className="text-sm text-gray-500">Task #{task.id}</span>
              {task.branch_name && (
                <span className="text-xs text-gray-400 font-mono bg-gray-100 px-2 py-0.5 rounded">
                  {task.branch_name}
                </span>
              )}
              {task.workspace_name && (
                <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                  Workspace: {task.workspace_name}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {canDelete && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-1 text-sm text-slate-600 hover:text-slate-700 border border-slate-200 rounded-md px-3 py-1.5"
              >
                {deleting ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <Trash2 size={14} />
                )}
                Delete
              </button>
            )}
            {canCancel && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="flex items-center gap-1 text-sm text-red-600 hover:text-red-700 border border-red-200 rounded-md px-3 py-1.5"
              >
                {cancelling ? (
                  <Loader2 className="animate-spin" size={14} />
                ) : (
                  <XCircle size={14} />
                )}
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>

      {task.description && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Description</h2>
          <p className="text-sm text-gray-600 whitespace-pre-wrap">{task.description}</p>
        </div>
      )}

      {task.workspace_name && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Workspace</h2>
          <div className="space-y-2 text-sm text-gray-600">
            <p>
              {task.workspace_name}
              {task.workspace_kind ? ` · ${task.workspace_kind}` : ""}
            </p>
            {task.branch_name && <p className="font-mono text-xs">{task.branch_name}</p>}
            {task.workspace_path && <p className="font-mono text-xs">{task.workspace_path}</p>}
            <p>{task.workspace_task_count} task(s) in this workspace</p>
          </div>
        </div>
      )}

      {(canResume || actionError) && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-700 mb-1">Next Action</h2>
            <p className="text-sm text-gray-500">
              Add follow-up instructions and put this task back into the queue.
            </p>
          </div>
          {canResume && (
            <>
              <textarea
                value={followUpComment}
                onChange={(event) => setFollowUpComment(event.target.value)}
                rows={4}
                placeholder="Optional: tell the agent what to fix or try next."
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleResume}
                  disabled={resuming}
                  className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:opacity-50"
                >
                  {resuming && <Loader2 className="animate-spin" size={14} />}
                  Send Command & Requeue
                </button>
              </div>
            </>
          )}
          {actionError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {actionError}
            </div>
          )}
        </div>
      )}

      {(task.scheduled_for || task.blocked_by_task_id) && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Queue Conditions</h2>
          <div className="space-y-2 text-sm text-gray-600">
            {task.scheduled_for && <p>Start after: {formatSchedule(task.scheduled_for)}</p>}
            {task.blocked_by_task_id && (
              <p>
                After task #{task.blocked_by_task_id}
                {task.blocked_by_title ? ` ${task.blocked_by_title}` : ""}
              </p>
            )}
          </div>
        </div>
      )}

      {task.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-red-700 mb-1">Error</h2>
          <p className="text-sm text-red-600 whitespace-pre-wrap">{task.error_message}</p>
        </div>
      )}

      {task.status === "AWAIT_PLAN_APPROVAL" && task.plan_text && (
        <PlanApproval taskId={task.id} planText={task.plan_text} onApproved={() => mutate()} />
      )}

      {task.status === "AWAIT_MERGE_APPROVAL" && task.diff_text && (
        <MergeApproval taskId={task.id} diffText={task.diff_text} onApproved={() => mutate()} />
      )}

      {task.plan_text && task.status !== "AWAIT_PLAN_APPROVAL" && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Plan</h2>
          <pre className="text-xs text-gray-600 overflow-auto max-h-[300px] whitespace-pre-wrap">
            {task.plan_text}
          </pre>
        </div>
      )}

      {task.diff_text && task.status !== "AWAIT_MERGE_APPROVAL" && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Changes</h2>
          <DiffViewer diff={task.diff_text} />
        </div>
      )}

      <LogStream taskId={task.id} />
    </div>
  );
}
