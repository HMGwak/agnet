export type TaskStatus =
  | "PENDING"
  | "PREPARING_WORKSPACE"
  | "PLANNING"
  | "AWAIT_PLAN_APPROVAL"
  | "IMPLEMENTING"
  | "TESTING"
  | "AWAIT_MERGE_APPROVAL"
  | "MERGING"
  | "DONE"
  | "FAILED"
  | "CANCELLED";

export interface Repo {
  id: number;
  name: string;
  path: string;
  default_branch: string;
  created_at: string;
}

export interface RepoCreate {
  name: string;
  path: string;
  default_branch?: string;
}

export interface RepoPathPickResponse {
  path: string | null;
}

export interface Task {
  id: number;
  repo_id: number;
  title: string;
  description: string;
  status: TaskStatus;
  branch_name: string | null;
  workspace_path: string | null;
  plan_text: string | null;
  diff_text: string | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface TaskSummary {
  id: number;
  repo_id: number;
  title: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  repo_id: number;
  title: string;
  description?: string;
}

export interface ApprovalReq {
  decision: "approved" | "rejected";
  comment?: string;
}

export interface Approval {
  id: number;
  task_id: number;
  phase: string;
  decision: string;
  comment: string | null;
  decided_at: string;
}
