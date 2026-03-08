"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { LayoutDashboard, GitFork, BookOpen } from "lucide-react";
import { useRepos } from "@/hooks/useTasks";

const navItems = [
  { href: "/tasks", label: "Tasks", icon: LayoutDashboard },
  { href: "/repos", label: "Repos", icon: GitFork },
  { href: "/manual", label: "User Manual", icon: BookOpen },
];

export function Sidebar() {
  return (
    <Suspense fallback={<SidebarShell />}>
      <SidebarContent />
    </Suspense>
  );
}

function SidebarShell() {
  return (
    <aside className="w-56 bg-gray-900 text-gray-100 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight">AI Dev Dashboard</h1>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.href}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-gray-400"
            >
              <Icon size={18} />
              {item.label}
            </div>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-700 text-xs text-gray-500">
        AI Dev Automation
      </div>
    </aside>
  );
}

function SidebarContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: repos } = useRepos();
  const activeRepoId = searchParams.get("repo_id");

  return (
    <aside className="w-56 bg-gray-900 text-gray-100 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight">AI Dev Dashboard</h1>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <div key={item.href}>
              <Link
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${active
                    ? "bg-gray-700 text-white"
                    : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                  }`}
              >
                <Icon size={18} />
                {item.label}
              </Link>
              {item.href === "/tasks" && repos && repos.length > 0 && (
                <div className="mt-1 ml-4 space-y-1 border-l border-gray-800 pl-3">
                  {repos
                    .slice()
                    .sort((a, b) => a.name.localeCompare(b.name))
                    .map((repo) => {
                      const repoActive =
                        pathname === "/tasks" && activeRepoId === String(repo.id);
                      return (
                        <Link
                          key={repo.id}
                          href={`/tasks?repo_id=${repo.id}`}
                          className={`block rounded-md px-3 py-1.5 text-xs transition-colors ${repoActive
                              ? "bg-gray-800 text-white"
                              : "text-gray-500 hover:bg-gray-800 hover:text-gray-200"
                            }`}
                        >
                          {repo.name}
                        </Link>
                      );
                    })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="p-4 border-t border-gray-700 text-xs text-gray-500">
        AI Dev Automation
      </div>
    </aside>
  );
}
