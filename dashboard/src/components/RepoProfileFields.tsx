"use client";

import type { RepoProfile } from "@/lib/types";

export const EMPTY_REPO_PROFILE: RepoProfile = {
  language: "",
  frameworks: [],
  package_manager: "",
  dev_commands: [],
  test_commands: [],
  build_commands: [],
  lint_commands: [],
  deploy_considerations: "",
  main_branch_protection: "",
  deployment_sensitivity: "",
  environment_notes: [],
  safety_rules: [],
};

const FIELD_LABELS: Record<string, string> = {
  language: "Language",
  frameworks: "Frameworks",
  package_manager: "Runtime / Package Manager",
  dev_commands: "Dev Commands",
  test_commands: "Test Commands",
  build_commands: "Build Commands",
  lint_commands: "Lint Commands",
  deploy_considerations: "Deploy Considerations",
  main_branch_protection: "Main Branch Protection",
  deployment_sensitivity: "Deployment Sensitivity",
  environment_notes: "Environment Notes",
  safety_rules: "Safety Rules",
};

type Props = {
  value: RepoProfile;
  onChange: (next: RepoProfile) => void;
  missingFields?: string[];
};

export function RepoProfileFields({ value, onChange, missingFields = [] }: Props) {
  function hasError(field: string): boolean {
    return missingFields.includes(field);
  }

  function inputClass(field: string): string {
    const base =
      "w-full rounded-xl border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500";
    return hasError(field)
      ? `${base} border-amber-300 bg-amber-50`
      : `${base} border-slate-300`;
  }

  function setText(field: keyof RepoProfile, next: string) {
    onChange({ ...value, [field]: next });
  }

  function setLines(field: keyof RepoProfile, next: string) {
    onChange({
      ...value,
      [field]: next
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    });
  }

  function setCommaSeparated(field: keyof RepoProfile, next: string) {
    onChange({
      ...value,
      [field]: next
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  function renderLabel(field: keyof RepoProfile) {
    return (
      <label className="mb-1 block text-sm font-medium text-slate-700">
        {FIELD_LABELS[field]}
        {hasError(field) && <span className="ml-2 text-xs text-amber-700">Required</span>}
      </label>
    );
  }

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">Repo Profile</h3>
        <p className="mt-1 text-xs text-slate-500">
          This data is written into the repo-local AGENTS.md profile block and reused by task
          intake.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("language")}
          <input
            type="text"
            value={value.language}
            onChange={(event) => setText("language", event.target.value)}
            placeholder="Python, TypeScript"
            className={inputClass("language")}
          />
        </div>
        <div>
          {renderLabel("frameworks")}
          <input
            type="text"
            value={value.frameworks.join(", ")}
            onChange={(event) => setCommaSeparated("frameworks", event.target.value)}
            placeholder="FastAPI, Next.js"
            className={inputClass("frameworks")}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("package_manager")}
          <input
            type="text"
            value={value.package_manager}
            onChange={(event) => setText("package_manager", event.target.value)}
            placeholder="uv, npm"
            className={inputClass("package_manager")}
          />
        </div>
        <div>
          {renderLabel("main_branch_protection")}
          <select
            value={value.main_branch_protection}
            onChange={(event) => setText("main_branch_protection", event.target.value)}
            className={inputClass("main_branch_protection")}
          >
            <option value="">Select...</option>
            <option value="protected">Protected</option>
            <option value="guarded">Guarded</option>
            <option value="relaxed">Relaxed</option>
          </select>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("deployment_sensitivity")}
          <select
            value={value.deployment_sensitivity}
            onChange={(event) => setText("deployment_sensitivity", event.target.value)}
            className={inputClass("deployment_sensitivity")}
          >
            <option value="">Select...</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <div>
          {renderLabel("deploy_considerations")}
          <input
            type="text"
            value={value.deploy_considerations}
            onChange={(event) => setText("deploy_considerations", event.target.value)}
            placeholder="Local only, staging first, production critical"
            className={inputClass("deploy_considerations")}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("dev_commands")}
          <textarea
            value={value.dev_commands.join("\n")}
            onChange={(event) => setLines("dev_commands", event.target.value)}
            rows={4}
            placeholder={"cd backend && uv sync --extra dev\ncd dashboard && npm run dev"}
            className={inputClass("dev_commands")}
          />
        </div>
        <div>
          {renderLabel("test_commands")}
          <textarea
            value={value.test_commands.join("\n")}
            onChange={(event) => setLines("test_commands", event.target.value)}
            rows={4}
            placeholder={"cd backend && uv run pytest\ncd dashboard && npm run lint"}
            className={inputClass("test_commands")}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("build_commands")}
          <textarea
            value={value.build_commands.join("\n")}
            onChange={(event) => setLines("build_commands", event.target.value)}
            rows={3}
            placeholder="npm run build"
            className={inputClass("build_commands")}
          />
        </div>
        <div>
          {renderLabel("lint_commands")}
          <textarea
            value={value.lint_commands.join("\n")}
            onChange={(event) => setLines("lint_commands", event.target.value)}
            rows={3}
            placeholder="npm run lint"
            className={inputClass("lint_commands")}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          {renderLabel("environment_notes")}
          <textarea
            value={value.environment_notes.join("\n")}
            onChange={(event) => setLines("environment_notes", event.target.value)}
            rows={3}
            placeholder={"Needs .env\nUses local SQLite"}
            className={inputClass("environment_notes")}
          />
        </div>
        <div>
          {renderLabel("safety_rules")}
          <textarea
            value={value.safety_rules.join("\n")}
            onChange={(event) => setLines("safety_rules", event.target.value)}
            rows={3}
            placeholder={"Do not deploy from feature branches\nRun tests before merge"}
            className={inputClass("safety_rules")}
          />
        </div>
      </div>
    </div>
  );
}
