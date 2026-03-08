"use client";

import { useState } from "react";
import { approveMerge } from "@/lib/api";
import { DiffViewer } from "./DiffViewer";
import { Loader2, GitMerge, X } from "lucide-react";

interface Props {
  taskId: number;
  diffText: string;
  onApproved: () => void;
}

export function MergeApproval({ taskId, diffText, onApproved }: Props) {
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(decision: "approved" | "rejected") {
    setLoading(true);
    setError(null);
    try {
      await approveMerge(taskId, {
        decision,
        comment: comment.trim() || undefined,
      });
      onApproved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="border border-yellow-300 bg-yellow-50 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-yellow-800 mb-3">
        Merge Approval Required
      </h3>
      <div className="mb-3">
        {diffText.trim() ? (
          <DiffViewer diff={diffText} />
        ) : (
          <div className="rounded-md border border-yellow-200 bg-white/70 px-3 py-2 text-sm text-yellow-900">
            No diff snapshot was captured for this task. Approving will still merge the workspace
            branch changes into the base branch.
          </div>
        )}
      </div>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Comment (optional)"
        rows={2}
        className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-yellow-400"
      />
      {error && (
        <p className="text-sm text-red-600 mb-2">{error}</p>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => handleDecision("approved")}
          disabled={loading}
          className="flex items-center gap-1 bg-green-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="animate-spin" size={16} /> : <GitMerge size={16} />}
          Approve Merge
        </button>
        <button
          onClick={() => handleDecision("rejected")}
          disabled={loading}
          className="flex items-center gap-1 bg-red-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-red-700 disabled:opacity-50"
        >
          <X size={16} />
          Reject
        </button>
      </div>
    </div>
  );
}
