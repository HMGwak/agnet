export type TaskStatus =
  | "PENDING"
  | "PREPARING_WORKSPACE"
  | "PLANNING"
  | "AWAIT_PLAN_APPROVAL"
  | "IMPLEMENTING"
  | "TESTING"
  | "AWAIT_MERGE_APPROVAL"
  | "MERGING"
  | "NEEDS_ATTENTION"
  | "DONE"
  | "FAILED"
  | "CANCELLED";

export type WorkspaceKind = "MAIN" | "FEATURE";

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

export interface Workspace {
  id: number;
  repo_id: number;
  name: string;
  kind: WorkspaceKind;
  base_branch: string;
  branch_name: string;
  workspace_path: string | null;
  is_active: boolean;
  task_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreate {
  name: string;
}

export interface Task {
  id: number;
  repo_id: number;
  workspace_id: number | null;
  workspace_name: string | null;
  workspace_kind: WorkspaceKind | null;
  workspace_task_count: number;
  title: string;
  description: string;
  scheduled_for: string | null;
  blocked_by_task_id: number | null;
  blocked_by_title: string | null;
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
  workspace_id: number | null;
  workspace_name: string | null;
  workspace_kind: WorkspaceKind | null;
  workspace_task_count: number;
  title: string;
  scheduled_for: string | null;
  blocked_by_task_id: number | null;
  blocked_by_title: string | null;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  repo_id: number;
  title: string;
  description?: string;
  scheduled_for?: string;
  blocked_by_task_id?: number;
  workspace_id?: number;
  create_workspace?: WorkspaceCreate;
}

export type TaskIntakeRole = "user" | "assistant";

export interface TaskIntakeTurn {
  role: TaskIntakeRole;
  message: string;
}

export interface TaskIntakeDraft {
  workspace_mode: "existing" | "new" | "unspecified";
  workspace_id: number | null;
  new_workspace_name: string | null;
  title: string;
  description: string;
  blocked_by_task_id: number | null;
  scheduled_for: string | null;
}

export interface TaskIntakeRequest {
  repo_id: number;
  user_request: string;
  conversation?: TaskIntakeTurn[];
  draft?: TaskIntakeDraft;
}

export interface TaskIntakeResponse {
  draft: TaskIntakeDraft;
  questions: string[];
  needs_confirmation: boolean;
  notes: string[];
}

export interface TaskResumeReq {
  comment?: string;
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
