"use client";

import { useTasks } from "@/hooks/useTasks";
import { useWebSocket } from "@/hooks/useWebSocket";
import { TaskCard } from "@/components/TaskCard";
import type { TaskStatus, TaskSummary } from "@/lib/types";
import { useSWRConfig } from "swr";
import { Loader2 } from "lucide-react";

type Column = {
  title: string;
  statuses: TaskStatus[];
  color: string;
};

const COLUMNS: Column[] = [
  {
    title: "Queued",
    statuses: ["PENDING", "PREPARING_WORKSPACE"],
    color: "border-gray-300",
  },
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
    title: "Done",
    statuses: ["DONE"],
    color: "border-green-400",
  },
  {
    title: "Failed",
    statuses: ["FAILED", "CANCELLED"],
    color: "border-red-400",
  },
];

function filterTasks(tasks: TaskSummary[], statuses: TaskStatus[]) {
  return tasks.filter((t) => statuses.includes(t.status));
}

export default function TasksPage() {
  const { data: tasks, error, isLoading } = useTasks();
  const { mutate } = useSWRConfig();

  useWebSocket(undefined, (msg) => {
    if (msg.type === "task_state_changed") {
      mutate((key: unknown) => Array.isArray(key) && key[0] === "tasks");
    }
  });

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

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Task Board</h1>
        <span className="text-sm text-gray-500">
          {allTasks.length} task{allTasks.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="grid grid-cols-5 gap-4">
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
                    <TaskCard key={task.id} task={task} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
