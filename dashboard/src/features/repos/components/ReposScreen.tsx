"use client";

import { useState } from "react";
import { FolderOpen, FolderPlus, GitBranch, LayoutList } from "lucide-react";
import { useRepos } from "@/hooks/useTasks";
import { createRepo, deleteRepo, pickRepoPath } from "@/lib/api";
import { formatKSTDate } from "@/lib/time";

function normalizeRepoPath(value: string): string {
  let cleaned = value.trim();
  while (
    cleaned.length >= 2 &&
    cleaned[0] === cleaned[cleaned.length - 1] &&
    (cleaned[0] === '"' || cleaned[0] === "'")
  ) {
    cleaned = cleaned.slice(1, -1).trim();
  }
  return cleaned;
}

export function ReposScreen() {
  const { data: repos, mutate, isLoading } = useRepos();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [createIfMissing, setCreateIfMissing] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [deletingRepoId, setDeletingRepoId] = useState<number | null>(null);
  const repoCount = repos?.length ?? 0;

  async function handleBrowse() {
    setError("");
    setBrowsing(true);
    try {
      const result = await pickRepoPath();
      if (result.path) {
        setPath(result.path);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open folder picker");
    } finally {
      setBrowsing(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const normalizedPath = normalizeRepoPath(path);
      setPath(normalizedPath);
      await createRepo({
        name: name.trim(),
        path: normalizedPath,
        default_branch: defaultBranch.trim() || "main",
        create_if_missing: createIfMissing,
      });
      setName("");
      setPath("");
      setDefaultBranch("main");
      setCreateIfMissing(false);
      mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create repo");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(repoId: number, repoName: string) {
    const confirmed = window.confirm(
      `Remove ${repoName} from this tool?\n\nThe local folder will not be deleted.`
    );
    if (!confirmed) {
      return;
    }

    setError("");
    setDeletingRepoId(repoId);
    try {
      await deleteRepo(repoId);
      await mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete repo");
    } finally {
      setDeletingRepoId(null);
    }
  }

  return (
    <div className="space-y-8">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-sky-50/70 p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">
              <FolderPlus size={14} />
              Repository Workspace
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-900">
              Register repositories without slowing down intake
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Keep repository setup light here, then let the first task gather any repo-specific
              profile detail inside the project itself.
            </p>
          </div>

          <div className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
            <LayoutList size={16} className="text-slate-400" />
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-slate-400">Registered</div>
              <div className="text-lg font-semibold text-slate-900">{repoCount}</div>
            </div>
          </div>
        </div>
      </section>

      <form
        onSubmit={handleSubmit}
        className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm"
      >
        <div className="border-b border-slate-200 bg-slate-50/80 px-6 py-5">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Register Repository</h2>
              <p className="mt-1 text-sm text-slate-500">
                Name the repo, point to the local path, and optionally bootstrap a new folder.
              </p>
            </div>

            <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-500 shadow-sm ring-1 ring-slate-200">
              <GitBranch size={14} className="text-sky-600" />
              Repo profile moves to first task intake
            </div>
          </div>
        </div>

        <div className="space-y-5 px-6 py-6">
          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          <div className="grid gap-5 xl:grid-cols-12">
            <div className="xl:col-span-3">
              <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="my-project"
                className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              />
            </div>

            <div className="xl:col-span-2">
              <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Default Branch
              </label>
              <input
                type="text"
                value={defaultBranch}
                onChange={(e) => setDefaultBranch(e.target.value)}
                className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              />
            </div>

            <div className="xl:col-span-7">
              <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Path
              </label>
              <div className="flex flex-col gap-3 lg:flex-row">
                <input
                  type="text"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  onBlur={() => setPath((current) => normalizeRepoPath(current))}
                  required
                  placeholder="D:\\Python\\agent\\dashboard"
                  className="min-w-0 flex-1 rounded-2xl border border-slate-300 px-4 py-3 font-mono text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                />
                <button
                  type="button"
                  onClick={handleBrowse}
                  disabled={browsing || submitting}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-300 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  <FolderOpen size={16} />
                  {browsing ? "Opening..." : "Browse..."}
                </button>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <label className="flex items-start gap-3 cursor-pointer text-sm text-slate-700">
              <input
                type="checkbox"
                checked={createIfMissing}
                onChange={(e) => setCreateIfMissing(e.target.checked)}
                className="mt-0.5 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
              />
              <span>
                <span className="block font-medium text-slate-900">
                  Create the folder and initialize Git if the path does not exist
                </span>
                <span className="mt-1 block text-xs text-slate-500">
                  If the path already exists, it is treated as the parent folder and a child
                  directory named after the repo is created inside it.
                </span>
              </span>
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-sky-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-sky-700 disabled:opacity-50"
            >
              <FolderPlus size={16} />
              {submitting ? "Registering..." : "Register Repo"}
            </button>
          </div>

          <p className="text-xs text-slate-500">
            Pasted paths like <span className="font-mono">{'"D:\\Python\\agent\\dashboard"'}</span>{" "}
            are accepted.
          </p>
        </div>
      </form>

      <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-2 border-b border-slate-200 bg-slate-50/80 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Registered Repositories</h2>
            <p className="mt-1 text-sm text-slate-500">
              Local repositories already wired into the task board.
            </p>
          </div>

          <div className="text-sm text-slate-400">
            {repoCount} repo{repoCount === 1 ? "" : "s"}
          </div>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-white">
            <tr className="border-b border-slate-200">
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Path
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Branch
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Registered
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-slate-500">
                  Loading repositories...
                </td>
              </tr>
            )}

            {repos && repos.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-16 text-center">
                  <div className="mx-auto max-w-sm">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                      <LayoutList size={20} />
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-700">
                      No repositories registered yet.
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      Add the first repository above to start routing workspaces and tasks.
                    </p>
                  </div>
                </td>
              </tr>
            )}

            {repos?.map((repo) => (
              <tr key={repo.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/70">
                <td className="px-6 py-4 font-medium text-slate-900">{repo.name}</td>
                <td className="px-6 py-4 font-mono text-xs text-slate-600">{repo.path}</td>
                <td className="px-6 py-4 text-slate-700">{repo.default_branch}</td>
                <td className="px-6 py-4 text-slate-500">{formatKSTDate(repo.created_at)}</td>
                <td className="px-6 py-4">
                  <button
                    type="button"
                    onClick={() => handleDelete(repo.id, repo.name)}
                    disabled={deletingRepoId === repo.id || submitting || browsing}
                    className="rounded-full border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-50 disabled:opacity-50"
                  >
                    {deletingRepoId === repo.id ? "Removing..." : "Remove"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
