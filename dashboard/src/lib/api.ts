import type {
  Repo,
  RepoCreate,
  Task,
  TaskSummary,
  TaskCreate,
  ApprovalReq,
  Approval,
} from "./types";

const API_BASE = "http://localhost:8000/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Repos
export const getRepos = () => fetchAPI<Repo[]>("/repos");
export const createRepo = (data: RepoCreate) =>
  fetchAPI<Repo>("/repos", { method: "POST", body: JSON.stringify(data) });

// Tasks
export const getTasks = (params?: { status?: string; repo_id?: number }) => {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.repo_id) sp.set("repo_id", String(params.repo_id));
  return fetchAPI<TaskSummary[]>(`/tasks?${sp}`);
};

export const getTask = (id: number) => fetchAPI<Task>(`/tasks/${id}`);

export const createTask = (data: TaskCreate) =>
  fetchAPI<Task>("/tasks", { method: "POST", body: JSON.stringify(data) });

export const approvePlan = (id: number, data: ApprovalReq) =>
  fetchAPI<Approval>(`/tasks/${id}/approve-plan`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const approveMerge = (id: number, data: ApprovalReq) =>
  fetchAPI<Approval>(`/tasks/${id}/approve-merge`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const cancelTask = (id: number) =>
  fetchAPI<void>(`/tasks/${id}/cancel`, { method: "POST" });

export const getTaskLogs = (id: number) =>
  fetch(`${API_BASE}/tasks/${id}/logs`).then((r) => r.text());
