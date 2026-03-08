"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useSWRConfig } from "swr";
import { ArrowLeft, CheckCircle2, Loader2, Timer, Trash2, XCircle } from "lucide-react";
import { useTask } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cancelTask, deleteTask, getTaskLogs, resumeTask } from "@/lib/api";
import type { Run } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { MergeApproval } from "@/components/MergeApproval";
import { DiffViewer } from "@/components/DiffViewer";
import { LogStream } from "@/components/LogStream";
import { formatKSTDateTime, parseBackendTimestamp } from "@/lib/time";

type Props = {
  taskId: number;
  showBackLink?: boolean;
  className?: string;
  onDeleted?: () => void;
};

type ParsedLogLine = {
  raw: string;
  timestampMs: number | null;
};

function stripTimestampPrefix(raw: string): string {
  const match = raw.match(/^\[[^\]]+\]\s*(.*)$/);
  return match ? match[1] : raw;
}

function parseLogLines(text: string): ParsedLogLine[] {
  return text
    .split("\n")
    .filter(Boolean)
    .map((raw) => {
      const match = raw.match(/^\[([^\]]+)\]/);
      if (!match) {
        return { raw, timestampMs: null };
      }
      const parsed = parseBackendTimestamp(match[1]);
      return { raw, timestampMs: Number.isNaN(parsed) ? null : parsed };
    });
}

function formatPhaseLabel(phase: string): string {
  return phase
    .split("_")
    .join(" ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function describeRunState(run: Run): { label: string; tone: string; icon: "success" | "error" | "running" } {
  if (run.exit_code === null) {
    return {
      label: "In progress",
      tone: "bg-sky-50 text-sky-700 border-sky-200",
      icon: "running",
    };
  }
  if (run.exit_code === 0) {
    return {
      label: "Passed",
      tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
      icon: "success",
    };
  }
  return {
    label: "Failed",
    tone: "bg-red-50 text-red-700 border-red-200",
    icon: "error",
  };
}

function runListItemTone(run: Run, isSelected: boolean): string {
  if (run.exit_code === null) {
    return isSelected
      ? "border-sky-300 bg-sky-50 shadow-sm"
      : "border-sky-200 bg-sky-50/60 hover:bg-sky-50";
  }
  if (run.exit_code === 0) {
    return isSelected
      ? "border-emerald-300 bg-emerald-50 shadow-sm"
      : "border-emerald-200 bg-emerald-50/60 hover:bg-emerald-50";
  }
  return isSelected
    ? "border-red-300 bg-red-50 shadow-sm"
    : "border-red-200 bg-red-50/60 hover:bg-red-50";
}

function runIndicatorTone(run: Run): string {
  if (run.exit_code === null) {
    return "bg-sky-500";
  }
  if (run.exit_code === 0) {
    return "bg-emerald-500";
  }
  return "bg-red-500";
}

function getStepLogLinesByStageMarker(
  runs: Run[],
  runIndex: number,
  logLines: ParsedLogLine[],
): string[] {
  const phase = runs[runIndex]?.phase;
  if (!phase) {
    return [];
  }

  const markerPrefix = `Stage: ${phase}`;
  const occurrenceIndex = runs
    .slice(0, runIndex + 1)
    .filter((run) => run.phase === phase).length - 1;

  const markerIndexes = logLines.reduce<number[]>((indexes, line, index) => {
    if (stripTimestampPrefix(line.raw).startsWith(markerPrefix)) {
      indexes.push(index);
    }
    return indexes;
  }, []);

  const startIndex = markerIndexes[occurrenceIndex];
  if (startIndex === undefined) {
    return [];
  }

  let endIndex = logLines.length;
  for (let index = startIndex + 1; index < logLines.length; index += 1) {
    if (stripTimestampPrefix(logLines[index].raw).startsWith("Stage: ")) {
      endIndex = index;
      break;
    }
  }

  return logLines.slice(startIndex, endIndex).map((line) => line.raw);
}

function getStepLogLines(runs: Run[], selectedRunId: number | null, logLines: ParsedLogLine[]): string[] {
  if (!selectedRunId) {
    return [];
  }

  const runIndex = runs.findIndex((run) => run.id === selectedRunId);
  if (runIndex === -1) {
    return [];
  }

  const currentRun = runs[runIndex];
  const nextRun = runs[runIndex + 1];
  const startMs = parseBackendTimestamp(currentRun.started_at);
  const finishedMs = currentRun.finished_at
    ? parseBackendTimestamp(currentRun.finished_at)
    : Number.NaN;
  const nextRunMs = nextRun ? parseBackendTimestamp(nextRun.started_at) : Number.NaN;
  const lowerBound = Number.isNaN(startMs) ? null : startMs;
  const normalizedFinishedMs =
    !Number.isNaN(finishedMs) && finishedMs > startMs ? finishedMs : Number.NaN;
  const upperBound = !Number.isNaN(normalizedFinishedMs)
    ? normalizedFinishedMs
    : !Number.isNaN(nextRunMs) && nextRunMs > startMs
      ? nextRunMs
      : null;

  const timeWindowLines = logLines
    .filter((line) => {
      if (line.timestampMs === null || lowerBound === null) {
        return false;
      }
      if (line.timestampMs < lowerBound) {
        return false;
      }
      if (upperBound !== null && line.timestampMs >= upperBound) {
        return false;
      }
      return true;
    })
    .map((line) => line.raw);

  if (timeWindowLines.length > 0) {
    return timeWindowLines;
  }

  return getStepLogLinesByStageMarker(runs, runIndex, logLines);
}

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
  const [lastActivityAt, setLastActivityAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [logLines, setLogLines] = useState<ParsedLogLine[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);

  const { connected } = useWebSocket(taskId, (msg) => {
    if (msg.type === "task_state_changed") {
      mutate();
      return;
    }
    if (msg.type === "task_log_line") {
      const timestamp = typeof msg.data?.timestamp === "string" ? msg.data.timestamp : "";
      const line = typeof msg.data?.line === "string" ? msg.data.line : "";
      const parsed = parseBackendTimestamp(timestamp);
      if (!Number.isNaN(parsed)) {
        setLastActivityAt(parsed);
      }
      const raw = timestamp ? `[${timestamp}] ${line}` : line;
      setLogLines((prev) => [...prev, { raw, timestampMs: Number.isNaN(parsed) ? null : parsed }]);
    }
  });

  useEffect(() => {
    getTaskLogs(taskId)
      .then((text) => setLogLines(parseLogLines(text)))
      .catch(() => setLogLines([]));
  }, [taskId]);

  useEffect(() => {
    if (!task) {
      return;
    }
    const parsed = parseBackendTimestamp(task.updated_at);
    if (!Number.isNaN(parsed)) {
      setLastActivityAt(parsed);
    }
  }, [task?.updated_at, task]);

  useEffect(() => {
    const runs = task?.runs ?? [];
    if (runs.length === 0) {
      setSelectedRunId(null);
      return;
    }
    setSelectedRunId((current) => {
      if (current && runs.some((run) => run.id === current)) {
        return current;
      }
      return runs[runs.length - 1].id;
    });
  }, [task?.runs]);

  const isRunning = !!task && [
    "PREPARING_WORKSPACE",
    "PLANNING",
    "IMPLEMENTING",
    "TESTING",
    "MERGING",
  ].includes(task.status);

  useEffect(() => {
    if (!isRunning) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, [isRunning]);

  const executionState = useMemo(() => {
    if (!task) {
      return { headline: "", detail: "", activityMs: null as number | null };
    }

    const fallbackMs = parseBackendTimestamp(task.updated_at);
    const activityMs = lastActivityAt ?? (Number.isNaN(fallbackMs) ? null : fallbackMs);
    const idleSeconds = activityMs === null ? null : Math.max(0, Math.floor((now - activityMs) / 1000));

    let headline = "Waiting";
    if (task.status === "PREPARING_WORKSPACE") headline = "Preparing workspace";
    if (task.status === "PLANNING") headline = "Planning in progress";
    if (task.status === "IMPLEMENTING") headline = "Implementation in progress";
    if (task.status === "TESTING") headline = "Testing in progress";
    if (task.status === "MERGING") headline = "Merging in progress";
    if (task.status === "PENDING") headline = "Queued";
    if (task.status === "AWAIT_MERGE_APPROVAL") headline = "Waiting for merge approval";
    if (task.status === "NEEDS_ATTENTION") headline = "Needs attention";
    if (task.status === "FAILED") headline = "Execution failed";
    if (task.status === "CANCELLED") headline = "Execution cancelled";
    if (task.status === "DONE") headline = "Completed";

    let detail = "";
    if (isRunning) {
      if (!connected) {
        detail = "Live updates disconnected.";
      } else if (idleSeconds === null) {
        detail = "Running, waiting for the first log line.";
      } else if (idleSeconds < 15) {
        detail = "Receiving live output.";
      } else {
        detail = `Still running. No new log output for ${idleSeconds}s.`;
      }
    } else if (activityMs !== null) {
      detail = `Last activity ${formatKSTDateTime(new Date(activityMs).toISOString())}.`;
    }

    return { headline, detail, activityMs };
  }, [connected, isRunning, lastActivityAt, now, task]);

  const runs = useMemo(() => task?.runs ?? [], [task?.runs]);
  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );
  const stepLogLines = useMemo(
    () => getStepLogLines(runs, selectedRunId, logLines),
    [logLines, runs, selectedRunId]
  );

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

      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">Execution Status</h2>
        <div className="space-y-2 text-sm text-gray-600">
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 className="animate-spin text-sky-600" size={14} />}
            <span>{executionState.headline}</span>
          </div>
          {executionState.detail && <p>{executionState.detail}</p>}
          <p>Live connection: {connected ? "Connected" : "Disconnected"}</p>
          {executionState.activityMs !== null && (
            <p>Last activity: {formatKSTDateTime(new Date(executionState.activityMs).toISOString())}</p>
          )}
        </div>
      </div>

      {runs.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-700">Step History</h2>
              <p className="mt-1 text-sm text-gray-500">
                Review each recorded phase without leaving the board.
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
              {runs.length} step{runs.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
            <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
              {runs.map((run, index) => {
                const isSelected = run.id === selectedRunId;
                return (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => setSelectedRunId(run.id)}
                    className={`w-full rounded-2xl border px-3 py-3 text-left transition ${runListItemTone(run, isSelected)}`}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${runIndicatorTone(run)}`} />
                      <span className="font-semibold text-slate-900">Step {index + 1}</span>
                      <span className="text-slate-300">·</span>
                      <span className="font-medium uppercase tracking-wide text-slate-500">
                        {run.phase}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              {selectedRun ? (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-semibold text-slate-900">
                          {formatPhaseLabel(selectedRun.phase)}
                        </h3>
                        {describeRunState(selectedRun).icon === "success" && (
                          <CheckCircle2 className="text-emerald-600" size={16} />
                        )}
                        {describeRunState(selectedRun).icon === "error" && (
                          <XCircle className="text-red-600" size={16} />
                        )}
                        {describeRunState(selectedRun).icon === "running" && (
                          <Loader2 className="animate-spin text-sky-600" size={16} />
                        )}
                      </div>
                      <p className="mt-1 text-sm text-slate-500">
                        {selectedRun.finished_at
                          ? `${formatKSTDateTime(selectedRun.started_at)} - ${formatKSTDateTime(selectedRun.finished_at)}`
                          : `Started ${formatKSTDateTime(selectedRun.started_at)}`}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
                      Exit code: {selectedRun.exit_code ?? "running"}
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
                      <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                        <Timer size={14} />
                        Recorded window
                      </div>
                      <div className="mt-2 space-y-1 text-xs text-slate-500">
                        <p>Started: {formatKSTDateTime(selectedRun.started_at)}</p>
                        <p>
                          Finished:{" "}
                          {selectedRun.finished_at ? formatKSTDateTime(selectedRun.finished_at) : "Still running"}
                        </p>
                        {selectedRun.log_path && <p className="font-mono break-all">{selectedRun.log_path}</p>}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
                      <div className="text-sm font-medium text-slate-700">Artifacts</div>
                      <div className="mt-2 space-y-1 text-xs text-slate-500">
                        <p>Plan captured: {task.plan_text ? "Yes" : "No"}</p>
                        <p>Diff captured: {task.diff_text ? "Yes" : "No"}</p>
                        <p>Phase key: {selectedRun.phase}</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <h4 className="text-sm font-semibold text-slate-700">Step Logs</h4>
                    <div className="mt-2 rounded-2xl bg-slate-950 p-3">
                      {stepLogLines.length === 0 ? (
                        <p className="text-xs text-slate-400">No log lines were captured for this step yet.</p>
                      ) : (
                        <div className="max-h-[320px] space-y-0.5 overflow-y-auto font-mono text-xs text-slate-200">
                          {stepLogLines.map((line, index) => (
                            <div key={`${selectedRun.id}-${index}`} className="whitespace-pre-wrap break-all">
                              {line}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex min-h-[260px] items-center justify-center text-sm text-slate-400">
                  Select a step to inspect its detail.
                </div>
              )}
            </div>
          </div>
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

      {task.status === "AWAIT_MERGE_APPROVAL" && (
        <MergeApproval taskId={task.id} diffText={task.diff_text ?? ""} onApproved={() => mutate()} />
      )}

      {task.plan_text && (
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

      <LogStream taskId={task.id} onActivity={setLastActivityAt} />
    </div>
  );
}
