"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTasks } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useRepos } from "@/hooks/useTasks";
import { createTask } from "@/lib/api";
import { TaskCard } from "@/components/TaskCard";
import { TaskDetailContent } from "@/components/TaskDetailContent";
import type { TaskStatus, TaskSummary } from "@/lib/types";
import { useSWRConfig } from "swr";
import { Loader2, Plus, X } from "lucide-react";

type Column = {
  title: string;
  statuses: TaskStatus[];
  color: string;
};

const COLUMNS: Column[] = [
  {
    title: "Working",
    statuses: ["PLANNING", "IMPLEMENTING", "TESTING", "MERGING"],
    color: "border-blue-400",
  },
  {
    title: "Needs Approval",
    statuses: ["AWAIT_PLAN_APPROVAL", "AWAIT_MERGE_APPROVAL"],
    color: "border-yellow-400",
  },
  {
    title: "Needs Attention",
    statuses: ["NEEDS_ATTENTION", "FAILED"],
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

function filterTasks(tasks: TaskSummary[], statuses: TaskStatus[]) {
  return tasks.filter((t) => statuses.includes(t.status));
}

function sortQueuedTasks(tasks: TaskSummary[]) {
  return [...tasks].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

function toDateTimeLocalValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

export default function TasksPage() {
  return (
    <Suspense fallback={<TasksLoadingState />}>
      <TasksPageContent />
    </Suspense>
  );
}

function TasksLoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin text-gray-400" size={32} />
    </div>
  );
}

function TasksPageContent() {
  const searchParams = useSearchParams();
  const activeRepoId = searchParams.get("repo_id");
  const repoFilter = activeRepoId ? Number(activeRepoId) : undefined;
  const { data: tasks, error, isLoading } = useTasks(
    repoFilter ? { repo_id: repoFilter } : undefined
  );
  const { data: repos, isLoading: reposLoading } = useRepos();
  const { mutate } = useSWRConfig();
  const router = useRouter();
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [repoId, setRepoId] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [scheduledFor, setScheduledFor] = useState("");
  const [blockedByTaskId, setBlockedByTaskId] = useState<number | "">("");
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useWebSocket(undefined, (msg) => {
    if (msg.type === "task_state_changed" || msg.type === "task_deleted") {
      mutate((key: unknown) => Array.isArray(key) && key[0] === "tasks");
    }
  });

  useEffect(() => {
    if (!isComposerOpen) {
      setSubmitError(null);
    }
  }, [isComposerOpen]);

  useEffect(() => {
    if (repoFilter) {
      setRepoId(repoFilter);
    }
  }, [repoFilter]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 30000);

    return () => window.clearInterval(timer);
  }, []);

  async function handleCreateTask(e: React.FormEvent) {
    e.preventDefault();
    if (!repoId || !title.trim()) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      const task = await createTask({
        repo_id: Number(repoId),
        title: title.trim(),
        description: description.trim() || undefined,
        scheduled_for: scheduledFor || undefined,
        blocked_by_task_id: blockedByTaskId ? Number(blockedByTaskId) : undefined,
      });
      setRepoId("");
      setTitle("");
      setDescription("");
      setScheduledFor("");
      setBlockedByTaskId("");
      setIsComposerOpen(false);
      await mutate((key: unknown) => Array.isArray(key) && key[0] === "tasks");
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-red-500 p-4">
        Failed to load tasks. Is the backend running?
      </div>
    );
  }

  const allTasks = tasks ?? [];
  const queuedTasks = sortQueuedTasks(filterTasks(allTasks, ["PENDING", "PREPARING_WORKSPACE"]));
  const dependencyOptions = allTasks.filter(
    (task) =>
      repoId === "" || task.repo_id === Number(repoId)
  );
  const activeRepo = repos?.find((repo) => repo.id === repoFilter);

  return (
    <div className="relative pb-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {activeRepo ? `${activeRepo.name} Tasks` : "Task Board"}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            {activeRepo
              ? "Filtered view for one repository."
              : "Overall flow view across all repositories."}
          </p>
        </div>
        <span className="text-sm text-gray-500">
          {allTasks.length} task{allTasks.length !== 1 ? "s" : ""}
        </span>
      </div>

      <section className="mb-6 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Queued</h2>
            <p className="mt-1 text-xs text-slate-500">
              Tasks line up here until an agent picks up the leftmost item.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
              {queuedTasks.length}
            </span>
            <button
              type="button"
              onClick={() => setIsComposerOpen(true)}
              className="inline-flex items-center gap-2 rounded-full bg-sky-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-sky-700"
            >
              <Plus size={16} />
              Add to Queue
            </button>
          </div>
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
          {COLUMNS.map((col) => {
            const colTasks = filterTasks(allTasks, col.statuses);
            return (
              <div key={col.title} className="flex flex-col">
                <div
                  className={`border-t-2 ${col.color} bg-white rounded-t-lg px-3 py-2 flex items-center justify-between`}
                >
                  <h2 className="text-sm font-semibold text-gray-700">
                    {col.title}
                  </h2>
                  <span className="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
                    {colTasks.length}
                  </span>
                </div>
                <div className="bg-gray-100/50 rounded-b-lg p-2 space-y-2 min-h-[200px]">
                  {colTasks.length === 0 ? (
                    <p className="text-xs text-gray-400 text-center py-8">
                      No tasks
                    </p>
                  ) : (
                    colTasks.map((task) => (
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

      {isComposerOpen && (
        <div className="fixed inset-0 z-40 flex items-end justify-end bg-slate-950/20 p-6 sm:items-center sm:justify-center">
          <div className="w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">New Task</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Queue work without leaving the board.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsComposerOpen(false)}
                className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
                aria-label="Close new task dialog"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Repository
                </label>
                {reposLoading ? (
                  <Loader2 className="animate-spin text-gray-400" size={20} />
                ) : (
                  <select
                    value={repoId}
                    onChange={(e) => setRepoId(e.target.value ? Number(e.target.value) : "")}
                    required
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
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

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  placeholder="What should be done?"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
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
                    onChange={(e) => setScheduledFor(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    After task
                  </label>
                  <select
                    value={blockedByTaskId}
                    onChange={(e) =>
                      setBlockedByTaskId(e.target.value ? Number(e.target.value) : "")
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

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsComposerOpen(false)}
                  className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !repoId || !title.trim()}
                  className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-700 disabled:opacity-50"
                >
                  {submitting && <Loader2 className="animate-spin" size={16} />}
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

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
