"use client";

import { useState } from "react";
import { useRepos } from "@/hooks/useTasks";
import { createRepo, pickRepoPath } from "@/lib/api";

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
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [browsing, setBrowsing] = useState(false);

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
      });
      setName("");
      setPath("");
      setDefaultBranch("main");
      mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create repo");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Repositories</h1>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg border p-4 space-y-4 max-w-lg">
        <h2 className="text-lg font-semibold">Register Repository</h2>
        {error && (
          <div className="bg-red-50 text-red-700 px-3 py-2 rounded text-sm">{error}</div>
        )}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="my-project"
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Path (server local)</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onBlur={() => setPath((current) => normalizeRepoPath(current))}
              required
              placeholder="D:\\Python\\agent\\dashboard"
              className="flex-1 border rounded px-3 py-2 text-sm font-mono"
            />
            <button
              type="button"
              onClick={handleBrowse}
              disabled={browsing || submitting}
              className="border rounded px-3 py-2 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
            >
              {browsing ? "Opening..." : "Browse..."}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Pasted paths like <span className="font-mono">{'"D:\\Python\\agent\\dashboard"'}</span>{" "}
            are accepted.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Default Branch</label>
          <input
            type="text"
            value={defaultBranch}
            onChange={(e) => setDefaultBranch(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Registering..." : "Register Repo"}
        </button>
      </form>

      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Path</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Branch</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Registered</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">Loading...</td>
              </tr>
            )}
            {repos && repos.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                  No repositories registered yet.
                </td>
              </tr>
            )}
            {repos?.map((repo) => (
              <tr key={repo.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium">{repo.name}</td>
                <td className="px-4 py-3 font-mono text-gray-600 text-xs">{repo.path}</td>
                <td className="px-4 py-3">{repo.default_branch}</td>
                <td className="px-4 py-3 text-gray-500">
                  {new Date(repo.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
