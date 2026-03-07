"use client";

import useSWR from "swr";
import { getTasks, getTask, getRepos, getWorkspaces } from "@/lib/api";

export function useTasks(params?: { status?: string; repo_id?: number }) {
  return useSWR(["tasks", params], () => getTasks(params));
}

export function useTask(id: number) {
  return useSWR(["task", id], () => getTask(id));
}

export function useRepos() {
  return useSWR("repos", getRepos);
}

export function useWorkspaces(repoId?: number) {
  return useSWR(repoId ? ["workspaces", repoId] : null, () => getWorkspaces(repoId!));
}
