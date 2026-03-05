"use client";

export function DiffViewer({ diff }: { diff: string }) {
  const lines = diff.split("\n");

  return (
    <div className="bg-gray-900 rounded-lg overflow-auto max-h-[500px] text-xs font-mono">
      <pre className="p-4">
        {lines.map((line, i) => {
          let className = "text-gray-300";
          if (line.startsWith("+") && !line.startsWith("+++")) {
            className = "text-green-400 bg-green-900/30";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            className = "text-red-400 bg-red-900/30";
          } else if (line.startsWith("@@")) {
            className = "text-blue-400";
          } else if (line.startsWith("diff ") || line.startsWith("index ")) {
            className = "text-gray-500";
          }
          return (
            <div key={i} className={className}>
              {line}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
