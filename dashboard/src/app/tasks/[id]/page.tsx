"use client";

import { use } from "react";
import { useTask } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cancelTask } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { PlanApproval } from "@/components/PlanApproval";
import { MergeApproval } from "@/components/MergeApproval";
import { DiffViewer } from "@/components/DiffViewer";
import { LogStream } from "@/components/LogStream";
import { Loader2, ArrowLeft, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

export default function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const taskId = Number(id);
  const { data: task, error, isLoading, mutate } = useTask(taskId);
  const [cancelling, setCancelling] = useState(false);

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
    return (
      <div className="text-red-500 p-4">
        Failed to load task.
      </div>
    );
  }

  const canCancel = !["DONE", "FAILED", "CANCELLED"].includes(task.status);

  async function handleCancel() {
    setCancelling(true);
    try {
      await cancelTask(taskId);
      mutate();
    } catch {
      // ignore
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/tasks"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-3"
        >
          <ArrowLeft size={14} />
          Back to board
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{task.title}</h1>
            <div className="flex items-center gap-3 mt-2">
              <StatusBadge status={task.status} />
              <span className="text-sm text-gray-500">
                Task #{task.id}
              </span>
              {task.branch_name && (
                <span className="text-xs text-gray-400 font-mono bg-gray-100 px-2 py-0.5 rounded">
                  {task.branch_name}
                </span>
              )}
            </div>
          </div>
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

      {/* Description */}
      {task.description && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Description</h2>
          <p className="text-sm text-gray-600 whitespace-pre-wrap">{task.description}</p>
        </div>
      )}

      {/* Error */}
      {task.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-red-700 mb-1">Error</h2>
          <p className="text-sm text-red-600 whitespace-pre-wrap">{task.error_message}</p>
        </div>
      )}

      {/* Plan Approval */}
      {task.status === "AWAIT_PLAN_APPROVAL" && task.plan_text && (
        <PlanApproval
          taskId={task.id}
          planText={task.plan_text}
          onApproved={() => mutate()}
        />
      )}

      {/* Merge Approval */}
      {task.status === "AWAIT_MERGE_APPROVAL" && task.diff_text && (
        <MergeApproval
          taskId={task.id}
          diffText={task.diff_text}
          onApproved={() => mutate()}
        />
      )}

      {/* Plan (when not in approval state) */}
      {task.plan_text && task.status !== "AWAIT_PLAN_APPROVAL" && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Plan</h2>
          <pre className="text-xs text-gray-600 overflow-auto max-h-[300px] whitespace-pre-wrap">
            {task.plan_text}
          </pre>
        </div>
      )}

      {/* Diff (when not in merge approval state) */}
      {task.diff_text && task.status !== "AWAIT_MERGE_APPROVAL" && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Changes</h2>
          <DiffViewer diff={task.diff_text} />
        </div>
      )}

      {/* Logs */}
      <LogStream taskId={task.id} />
    </div>
  );
}
