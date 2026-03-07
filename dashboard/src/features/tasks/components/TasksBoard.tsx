"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRepos, useTasks, useWorkspaces } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { analyzeTaskIntake, createTask, refineTaskIntake } from "@/lib/api";
import { TaskCard } from "@/components/TaskCard";
import { TaskDetailContent } from "@/components/TaskDetailContent";
import { formatKSTDateTime, parseBackendTimestamp } from "@/lib/time";
import type {
  TaskIntakeDraft,
  TaskIntakeTurn,
  TaskStatus,
  TaskSummary,
  Workspace,
} from "@/lib/types";
import { useSWRConfig } from "swr";
import { ChevronDown, ChevronUp, Loader2, Plus, X } from "lucide-react";

type Column = {
  title: string;
  statuses: TaskStatus[];
  color: string;
};

const BOARD_COLUMNS: Column[] = [
  {
    title: "Working",
    statuses: ["PLANNING", "IMPLEMENTING", "TESTING", "MERGING"],
    color: "border-blue-400",
  },
  {
    title: "Needs Approval",
    statuses: ["AWAIT_MERGE_APPROVAL"],
    color: "border-yellow-400",
  },
  {
    title: "Needs Attention",
    statuses: ["NEEDS_ATTENTION", "FAILED", "AWAIT_PLAN_APPROVAL"],
    color: "border-amber-400",
  },
  {
    title: "Cancelled",
    statuses: ["CANCELLED"],
    color: "border-slate-300",
  },
  {
    title: "Done",
    statuses: ["DONE"],
    color: "border-green-400",
  },
];

const WORKSPACE_COLUMNS: Column[] = [
  {
    title: "Queued",
    statuses: ["PENDING", "PREPARING_WORKSPACE"],
    color: "border-slate-300",
  },
  ...BOARD_COLUMNS,
];

function filterTasks(tasks: TaskSummary[], statuses: TaskStatus[]) {
  return tasks.filter((task) => statuses.includes(task.status));
}

function sortQueuedTasks(tasks: TaskSummary[]) {
  return [...tasks].sort(
    (a, b) => parseBackendTimestamp(a.created_at) - parseBackendTimestamp(b.created_at)
  );
}

function pickLatestTask(tasks: TaskSummary[], statuses: TaskStatus[]) {
  const matches = filterTasks(tasks, statuses);
  if (matches.length === 0) {
    return null;
  }
  return [...matches].sort(
    (a, b) => parseBackendTimestamp(b.updated_at) - parseBackendTimestamp(a.updated_at)
  )[0];
}

function toDateTimeLocalValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

function buildDraftFromFields(
  workspaceMode: "existing" | "new",
  workspaceId: number | "",
  newWorkspaceName: string,
  title: string,
  description: string,
  blockedByTaskId: number | "",
  scheduledFor: string
): TaskIntakeDraft {
  return {
    workspace_mode: workspaceMode,
    workspace_id: workspaceMode === "existing" && workspaceId ? Number(workspaceId) : null,
    new_workspace_name:
      workspaceMode === "new" && newWorkspaceName.trim() ? newWorkspaceName.trim() : null,
    title: title.trim(),
    description: description.trim(),
    blocked_by_task_id: blockedByTaskId ? Number(blockedByTaskId) : null,
    scheduled_for: scheduledFor || null,
  };
}

function pickAssistantReply(questions: string[], notes: string[], needsConfirmation: boolean) {
  if (questions.length > 0) {
    return questions.join("\n");
  }
  if (notes.length > 0) {
    return notes.join("\n");
  }
  if (needsConfirmation) {
    return "Draft updated. Review the filled fields and create the task when ready.";
  }
  return "I updated the task draft.";
}

function TasksLoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin text-gray-400" size={32} />
    </div>
  );
}

function WorkspaceRow({
  workspace,
  tasks,
  now,
  onSelectTask,
}: {
  workspace: Workspace;
  tasks: TaskSummary[];
  now: number;
  onSelectTask: (taskId: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const history = useMemo(
    () =>
      [...tasks].sort(
        (a, b) => parseBackendTimestamp(b.updated_at) - parseBackendTimestamp(a.updated_at)
      ),
    [tasks]
  );

  return (
    <section className="rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-slate-900">{workspace.name}</h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
              {workspace.kind}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
            <span className="font-mono">{workspace.branch_name}</span>
            <span>Base: {workspace.base_branch}</span>
            <span>{workspace.task_count} task{workspace.task_count !== 1 ? "s" : ""}</span>
            {workspace.workspace_path && <span className="font-mono">{workspace.workspace_path}</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          History
        </button>
      </div>

      <div className="grid gap-3 p-4 xl:grid-cols-6">
        {WORKSPACE_COLUMNS.map((column) => {
          const task = pickLatestTask(tasks, column.statuses);
          return (
            <div key={column.title} className="flex min-h-[170px] flex-col">
              <div
                className={`rounded-t-2xl border-t-2 ${column.color} bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600`}
              >
                {column.title}
              </div>
              <div className="flex-1 rounded-b-2xl border border-t-0 border-slate-200 bg-slate-50/50 p-2">
                {task ? (
                  <TaskCard task={task} now={now} onClick={onSelectTask} />
                ) : (
                  <div className="flex h-full min-h-[104px] items-center justify-center rounded-2xl border border-dashed border-slate-200 px-3 text-xs text-slate-400">
                    No task
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {expanded && (
        <div className="border-t border-slate-200 px-4 py-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">History</h3>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400">No task history yet.</p>
          ) : (
            <div className="space-y-2">
              {history.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => onSelectTask(task.id)}
                  className="flex w-full items-center justify-between rounded-2xl border border-slate-200 px-3 py-2 text-left hover:bg-slate-50"
                >
                  <div>
                    <div className="text-sm font-medium text-slate-800">{task.title}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      #{task.id} · {task.status}
                    </div>
                  </div>
                  <div className="text-xs text-slate-400">
                    {formatKSTDateTime(task.updated_at)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function TaskComposer({
  isOpen,
  onClose,
  repos,
  reposLoading,
  tasks,
  repoFilter,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  repos: { id: number; name: string }[] | undefined;
  reposLoading: boolean;
  tasks: TaskSummary[];
  repoFilter?: number;
  onCreated: (taskId: number) => void;
}) {
  const { mutate } = useSWRConfig();
  const [repoId, setRepoId] = useState<number | "">(repoFilter ?? "");
  const selectedRepoId = repoId === "" ? undefined : Number(repoId);
  const { data: workspaces, isLoading: workspacesLoading } = useWorkspaces(selectedRepoId);
  const [workspaceMode, setWorkspaceMode] = useState<"existing" | "new">("existing");
  const [workspaceId, setWorkspaceId] = useState<number | "">("");
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scheduledFor, setScheduledFor] = useState("");
  const [blockedByTaskId, setBlockedByTaskId] = useState<number | "">("");
  const [userRequest, setUserRequest] = useState("");
  const [followUpAnswer, setFollowUpAnswer] = useState("");
  const [intakeTurns, setIntakeTurns] = useState<TaskIntakeTurn[]>([]);
  const [intakeQuestions, setIntakeQuestions] = useState<string[]>([]);
  const [intakeNotes, setIntakeNotes] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [hasAnalyzed, setHasAnalyzed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (repoFilter) {
      setRepoId(repoFilter);
    }
  }, [repoFilter]);

  useEffect(() => {
    if (!isOpen) {
      setSubmitError(null);
      setWorkspaceMode("existing");
      setWorkspaceId("");
      setNewWorkspaceName("");
      setTitle("");
      setDescription("");
      setScheduledFor("");
      setBlockedByTaskId("");
      setUserRequest("");
      setFollowUpAnswer("");
      setIntakeTurns([]);
      setIntakeQuestions([]);
      setIntakeNotes([]);
      setAnalyzing(false);
      setIntakeError(null);
      setHasAnalyzed(false);
      if (repoFilter) {
        setRepoId(repoFilter);
      }
      return;
    }
  }, [isOpen, repoFilter]);

  useEffect(() => {
    if (workspaceMode !== "existing" || hasAnalyzed) {
      return;
    }
    if (workspaceId !== "" || !workspaces || workspaces.length === 0) {
      return;
    }
    const mainWorkspace = workspaces.find((workspace) => workspace.kind === "MAIN");
    setWorkspaceId(mainWorkspace?.id ?? workspaces[0].id);
  }, [hasAnalyzed, workspaceId, workspaceMode, workspaces]);

  function applyDraft(draft: TaskIntakeDraft) {
    if (draft.workspace_mode === "existing") {
      setWorkspaceMode("existing");
      setWorkspaceId(draft.workspace_id ?? "");
      setNewWorkspaceName("");
    } else if (draft.workspace_mode === "new") {
      setWorkspaceMode("new");
      setWorkspaceId("");
      setNewWorkspaceName(draft.new_workspace_name ?? "");
    } else {
      setWorkspaceMode("existing");
      setWorkspaceId("");
      setNewWorkspaceName("");
    }

    setTitle(draft.title ?? "");
    setDescription(draft.description ?? "");
    setBlockedByTaskId(draft.blocked_by_task_id ?? "");
    setScheduledFor(draft.scheduled_for ? toDateTimeLocalValue(draft.scheduled_for) : "");
  }

  async function handleAnalyze() {
    if (!selectedRepoId || !userRequest.trim()) {
      return;
    }

    setAnalyzing(true);
    setIntakeError(null);
    try {
      const response = await analyzeTaskIntake({
        repo_id: selectedRepoId,
        user_request: userRequest.trim(),
      });
      applyDraft(response.draft);
      setIntakeNotes(response.notes);
      setIntakeQuestions(response.questions);
      setHasAnalyzed(true);
      setFollowUpAnswer("");
      setIntakeTurns([
        { role: "user", message: userRequest.trim() },
        {
          role: "assistant",
          message: pickAssistantReply(
            response.questions,
            response.notes,
            response.needs_confirmation
          ),
        },
      ]);
    } catch (err) {
      setIntakeError(err instanceof Error ? err.message : "Failed to analyze request");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleRefine() {
    if (!selectedRepoId || !userRequest.trim() || !followUpAnswer.trim()) {
      return;
    }

    const nextTurns: TaskIntakeTurn[] = [
      ...intakeTurns,
      { role: "user", message: followUpAnswer.trim() },
    ];

    setAnalyzing(true);
    setIntakeError(null);
    try {
      const response = await refineTaskIntake({
        repo_id: selectedRepoId,
        user_request: userRequest.trim(),
        conversation: nextTurns,
        draft: buildDraftFromFields(
          workspaceMode,
          workspaceId,
          newWorkspaceName,
          title,
          description,
          blockedByTaskId,
          scheduledFor
        ),
      });
      applyDraft(response.draft);
      setIntakeNotes(response.notes);
      setIntakeQuestions(response.questions);
      setHasAnalyzed(true);
      setFollowUpAnswer("");
      setIntakeTurns([
        ...nextTurns,
        {
          role: "assistant",
          message: pickAssistantReply(
            response.questions,
            response.notes,
            response.needs_confirmation
          ),
        },
      ]);
    } catch (err) {
      setIntakeError(err instanceof Error ? err.message : "Failed to update draft");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!repoId || !title.trim()) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const task = await createTask({
        repo_id: Number(repoId),
        title: title.trim(),
        description: description.trim() || undefined,
        scheduled_for: scheduledFor || undefined,
        blocked_by_task_id: blockedByTaskId ? Number(blockedByTaskId) : undefined,
        workspace_id: workspaceMode === "existing" && workspaceId ? Number(workspaceId) : undefined,
        create_workspace:
          workspaceMode === "new" ? { name: newWorkspaceName.trim() } : undefined,
      });
      await mutate((key: unknown) => Array.isArray(key) && key[0] === "tasks");
      await mutate((key: unknown) => Array.isArray(key) && key[0] === "workspaces");
      onCreated(task.id);
      onClose();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  }

  const dependencyOptions = tasks.filter(
    (task) => selectedRepoId === undefined || task.repo_id === selectedRepoId
  );
  const canAnalyze = Boolean(selectedRepoId && userRequest.trim() && !analyzing);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-end overflow-y-auto bg-slate-950/20 p-6 sm:items-center sm:justify-center">
      <div className="flex max-h-[calc(100vh-3rem)] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">New Task</h2>
            <p className="mt-1 text-sm text-slate-500">
              Describe the work in natural language and let AI draft the task fields.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
            aria-label="Close new task dialog"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="space-y-4 overflow-y-auto pr-1">
            <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Repository</label>
            {reposLoading ? (
              <Loader2 className="animate-spin text-gray-400" size={20} />
            ) : (
              <select
                value={repoId}
                onChange={(event) => {
                  setRepoId(event.target.value ? Number(event.target.value) : "");
                  setWorkspaceId("");
                  setWorkspaceMode("existing");
                  setNewWorkspaceName("");
                  setBlockedByTaskId("");
                  setFollowUpAnswer("");
                  setIntakeTurns([]);
                  setIntakeQuestions([]);
                  setIntakeNotes([]);
                  setIntakeError(null);
                  setHasAnalyzed(false);
                }}
                required
                disabled={Boolean(repoFilter)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-50"
              >
                <option value="">Select a repository...</option>
                {repos?.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
            )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">AI Intake</h3>
                <p className="mt-1 text-xs text-slate-500">
                  Analyze a natural-language request, then review the structured task draft.
                </p>
              </div>
              <button
                type="button"
                onClick={handleAnalyze}
                disabled={!canAnalyze}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
              >
                {analyzing && <Loader2 className="animate-spin" size={16} />}
                Analyze
              </button>
            </div>

            <textarea
              value={userRequest}
              onChange={(event) => setUserRequest(event.target.value)}
              rows={4}
              placeholder={
                selectedRepoId
                  ? "Describe the work request. AI will fill the task fields below."
                  : "Select a repository first, then describe the work."
              }
              className="w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />

            {intakeTurns.length > 0 && (
              <div className="mt-4 space-y-2">
                {intakeTurns.map((turn, index) => (
                  <div
                    key={`${turn.role}-${index}`}
                    className={`rounded-2xl px-3 py-2 text-sm ${
                      turn.role === "assistant"
                        ? "border border-sky-100 bg-sky-50 text-sky-900"
                        : "border border-slate-200 bg-white text-slate-700"
                    }`}
                  >
                    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {turn.role === "assistant" ? "AI" : "You"}
                    </div>
                    <div className="whitespace-pre-wrap">{turn.message}</div>
                  </div>
                ))}
              </div>
            )}

            {intakeNotes.length > 0 && (
              <div className="mt-3 rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                {intakeNotes.join(" ")}
              </div>
            )}

            {intakeQuestions.length > 0 && (
              <div className="mt-3 space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-3">
                <div className="text-sm font-medium text-amber-900">
                  The AI needs a little more detail before the draft is final.
                </div>
                <ul className="list-disc space-y-1 pl-5 text-sm text-amber-900">
                  {intakeQuestions.map((question) => (
                    <li key={question}>{question}</li>
                  ))}
                </ul>
                <textarea
                  value={followUpAnswer}
                  onChange={(event) => setFollowUpAnswer(event.target.value)}
                  rows={3}
                  placeholder="Answer the follow-up questions here"
                  className="w-full rounded-2xl border border-amber-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={handleRefine}
                    disabled={analyzing || !followUpAnswer.trim()}
                    className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-amber-600 disabled:opacity-50"
                  >
                    {analyzing && <Loader2 className="animate-spin" size={16} />}
                    Update Draft
                  </button>
                </div>
              </div>
            )}

            {intakeError && (
              <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {intakeError}
              </div>
            )}
            </div>

            <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Workspace</label>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setWorkspaceMode("existing")}
                className={`rounded-2xl border px-3 py-2 text-sm font-medium ${
                  workspaceMode === "existing"
                    ? "border-sky-500 bg-sky-50 text-sky-700"
                    : "border-slate-200 text-slate-600"
                }`}
              >
                Use existing workspace
              </button>
              <button
                type="button"
                onClick={() => setWorkspaceMode("new")}
                className={`rounded-2xl border px-3 py-2 text-sm font-medium ${
                  workspaceMode === "new"
                    ? "border-sky-500 bg-sky-50 text-sky-700"
                    : "border-slate-200 text-slate-600"
                }`}
              >
                Create new workspace
              </button>
            </div>
            </div>

            {workspaceMode === "existing" ? (
              <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Existing workspace
              </label>
              {selectedRepoId && workspacesLoading ? (
                <Loader2 className="animate-spin text-gray-400" size={20} />
              ) : (
                <select
                  value={workspaceId}
                  onChange={(event) =>
                    setWorkspaceId(event.target.value ? Number(event.target.value) : "")
                  }
                  required
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="">Select a workspace...</option>
                  {workspaces?.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name} ({workspace.branch_name})
                    </option>
                  ))}
                </select>
              )}
              </div>
            ) : (
              <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                New workspace name
              </label>
              <input
                type="text"
                value={newWorkspaceName}
                onChange={(event) => setNewWorkspaceName(event.target.value)}
                placeholder="feature/tetris"
                required
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              </div>
            )}

            <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Title</label>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              placeholder="What should be done?"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            </div>

            <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Description</label>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={5}
              placeholder="Detailed description of the task"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Start after time
              </label>
              <input
                type="datetime-local"
                value={toDateTimeLocalValue(scheduledFor)}
                onChange={(event) => setScheduledFor(event.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              </div>
              <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                After task
              </label>
              <select
                value={blockedByTaskId}
                onChange={(event) =>
                  setBlockedByTaskId(event.target.value ? Number(event.target.value) : "")
                }
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="">Run as soon as possible</option>
                {dependencyOptions.map((task) => (
                  <option key={task.id} value={task.id}>
                    #{task.id} {task.title}
                  </option>
                ))}
              </select>
              </div>
            </div>

            {submitError && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {submitError}
              </div>
            )}
          </div>

          <div className="mt-4 flex items-center justify-end gap-3 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                submitting ||
                !repoId ||
                !title.trim() ||
                (workspaceMode === "existing" ? !workspaceId : !newWorkspaceName.trim())
              }
              className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:opacity-50"
            >
              {submitting && <Loader2 className="animate-spin" size={16} />}
              Create Task
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TasksBoardContent() {
  const searchParams = useSearchParams();
  const activeRepoId = searchParams.get("repo_id");
  const repoFilter = activeRepoId ? Number(activeRepoId) : undefined;
  const { data: tasks, error, isLoading } = useTasks(
    repoFilter ? { repo_id: repoFilter } : undefined
  );
  const { data: repos, isLoading: reposLoading } = useRepos();
  const { data: workspaces, isLoading: workspacesLoading } = useWorkspaces(repoFilter);
  const { mutate } = useSWRConfig();
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useWebSocket(undefined, (msg) => {
    if (msg.type === "task_state_changed" || msg.type === "task_deleted") {
      mutate((key: unknown) => Array.isArray(key) && (key[0] === "tasks" || key[0] === "workspaces"));
    }
  });

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 30000);

    return () => window.clearInterval(timer);
  }, []);

  if (isLoading || (repoFilter && workspacesLoading)) {
    return <TasksLoadingState />;
  }

  if (error) {
    return (
      <div className="text-red-500 p-4">
        Failed to load tasks. Is the backend running?
      </div>
    );
  }

  const allTasks = tasks ?? [];
  const activeRepo = repos?.find((repo) => repo.id === repoFilter);
  const queuedTasks = sortQueuedTasks(filterTasks(allTasks, ["PENDING", "PREPARING_WORKSPACE"]));

  const tasksByWorkspace = allTasks.reduce<Record<number, TaskSummary[]>>((groups, task) => {
    if (!task.workspace_id) {
      return groups;
    }
    groups[task.workspace_id] = groups[task.workspace_id] ?? [];
    groups[task.workspace_id].push(task);
    return groups;
  }, {});

  return (
    <div className="relative pb-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {activeRepo ? `${activeRepo.name} Tasks` : "Task Board"}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {activeRepo
              ? "Workspace rows for one repository."
              : "Overall flow view across all repositories."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">
            {allTasks.length} task{allTasks.length !== 1 ? "s" : ""}
          </span>
          <button
            type="button"
            onClick={() => setIsComposerOpen(true)}
            className="inline-flex items-center gap-2 rounded-full bg-sky-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-sky-700"
          >
            <Plus size={16} />
            Add Task
          </button>
        </div>
      </div>

      {!repoFilter ? (
        <>
          <section className="mb-6 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Queued</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Tasks line up here until an agent picks up the leftmost item.
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                {queuedTasks.length}
              </span>
            </div>

            <div className="overflow-x-auto pb-2">
              <div className="flex min-h-[164px] min-w-max items-stretch gap-3">
                {queuedTasks.length === 0 ? (
                  <div className="flex w-full min-w-[320px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 text-sm text-slate-400">
                    Queue is empty. Add the next task here.
                  </div>
                ) : (
                  queuedTasks.map((task) => (
                    <div key={task.id} className="w-72 shrink-0">
                      <TaskCard task={task} now={now} onClick={setSelectedTaskId} />
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          <div className="overflow-x-auto">
            <div className="grid min-w-[1100px] grid-cols-5 gap-4">
              {BOARD_COLUMNS.map((column) => {
                const columnTasks = filterTasks(allTasks, column.statuses);
                return (
                  <div key={column.title} className="flex flex-col">
                    <div
                      className={`flex items-center justify-between rounded-t-lg border-t-2 ${column.color} bg-white px-3 py-2`}
                    >
                      <h2 className="text-sm font-semibold text-gray-700">{column.title}</h2>
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-400">
                        {columnTasks.length}
                      </span>
                    </div>
                    <div className="min-h-[200px] space-y-2 rounded-b-lg bg-gray-100/50 p-2">
                      {columnTasks.length === 0 ? (
                        <p className="py-8 text-center text-xs text-gray-400">No tasks</p>
                      ) : (
                        columnTasks.map((task) => (
                          <TaskCard
                            key={task.id}
                            task={task}
                            now={now}
                            onClick={setSelectedTaskId}
                          />
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      ) : (
        <div className="space-y-4">
          {workspaces && workspaces.length > 0 ? (
            workspaces.map((workspace) => (
              <WorkspaceRow
                key={workspace.id}
                workspace={workspace}
                tasks={tasksByWorkspace[workspace.id] ?? []}
                now={now}
                onSelectTask={setSelectedTaskId}
              />
            ))
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
              No workspaces yet. Create a task to start with the main workspace or a new workspace.
            </div>
          )}
        </div>
      )}

      <TaskComposer
        isOpen={isComposerOpen}
        onClose={() => setIsComposerOpen(false)}
        repos={repos}
        reposLoading={reposLoading}
        tasks={allTasks}
        repoFilter={repoFilter}
        onCreated={setSelectedTaskId}
      />

      {selectedTaskId !== null && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/40 p-4 backdrop-blur-[1px] sm:p-6"
          onClick={() => setSelectedTaskId(null)}
        >
          <div
            className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-slate-50 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Task Details</h2>
                <p className="text-sm text-slate-500">
                  Review progress without leaving the board.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedTaskId(null)}
                className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
                aria-label="Close task details"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              <TaskDetailContent
                taskId={selectedTaskId}
                showBackLink={false}
                className="space-y-6"
                onDeleted={() => setSelectedTaskId(null)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function TasksBoard() {
  return (
    <Suspense fallback={<TasksLoadingState />}>
      <TasksBoardContent />
    </Suspense>
  );
}
