"use client";

import { useState } from "react";
import { useRepos } from "@/hooks/useTasks";
import { createRepo } from "@/lib/api";

export default function ReposPage() {
  const { data: repos, mutate, isLoading } = useRepos();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await createRepo({ name, path, default_branch: defaultBranch });
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

      {/* Registration Form */}
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
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            required
            placeholder="/home/user/projects/my-project"
            className="w-full border rounded px-3 py-2 text-sm font-mono"
          />
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

      {/* Repo List */}
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
