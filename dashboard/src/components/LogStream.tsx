"use client";

import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getTaskLogs } from "@/lib/api";

export function LogStream({ taskId }: { taskId: number }) {
  const [lines, setLines] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    getTaskLogs(taskId).then((text) => {
      if (text) {
        setLines(text.split("\n").filter(Boolean));
      }
    }).catch(() => {});
  }, [taskId]);

  useWebSocket(taskId, (msg) => {
    if (msg.type === "task_log_line") {
      setLines((prev) => [...prev, msg.data.line]);
    }
  });

  useEffect(() => {
    if (autoScrollRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines]);

  function handleScroll() {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 50;
  }

  return (
    <div className="bg-gray-900 rounded-lg">
      <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400">Logs</span>
        <span className="text-xs text-gray-500">{lines.length} lines</span>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="p-3 max-h-[400px] overflow-y-auto font-mono text-xs text-gray-300 space-y-0.5"
      >
        {lines.length === 0 ? (
          <p className="text-gray-500">No logs yet.</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
