import { access, mkdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { mkdtemp } from "node:fs/promises";
import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  buildAllowlistEnv,
  buildCodexOptions,
  buildRunStreamOptions,
  buildThreadOptions,
  createSidecarServer,
  hasProjectAuth,
  localCodexPathCandidates,
  parseArgs,
} from "../server.mjs";

async function makeFixtureAuth() {
  const dir = await mkdtemp(path.join(os.tmpdir(), "codex-sidecar-"));
  const file = path.join(dir, "auth.json");
  await writeFile(
    file,
    JSON.stringify({ access_token: "oauth-token" }),
    "utf8"
  );
  return { dir, file };
}

async function makeFixtureRuntime() {
  const runtimeFile = fileURLToPath(new URL("../node_modules/@openai/codex/bin/codex.js", import.meta.url));
  let existed = true;
  try {
    await access(runtimeFile);
  } catch {
    existed = false;
    await mkdir(path.dirname(runtimeFile), { recursive: true });
    await writeFile(runtimeFile, "#!/usr/bin/env node\n", "utf8");
  }

  return async () => {
    if (existed) {
      return;
    }
    await rm(fileURLToPath(new URL("../node_modules", import.meta.url)), {
      recursive: true,
      force: true,
    });
  };
}

test("parseArgs parses --runtime-home and --port", () => {
  const args = parseArgs(["--runtime-home=/tmp/codex-home", "--port=8123"]);
  assert.equal(args["runtime-home"], "/tmp/codex-home");
  assert.equal(args.port, "8123");
});

test("buildAllowlistEnv contains only allowlisted variables", () => {
  const originalExtra = process.env.EXTRA_VAR;
  const originalOpenAiApiKey = process.env.OPENAI_API_KEY;
  const originalCodexApiKey = process.env.CODEX_API_KEY;
  const originalPath = process.env.PATH;
  const originalHome = process.env.HOME;
  const originalSystemRoot = process.env.SystemRoot;
  process.env.EXTRA_VAR = "should-not-pass";
  process.env.OPENAI_API_KEY = "should-not-pass";
  process.env.CODEX_API_KEY = "should-not-pass";
  process.env.PATH = "/bin";
  process.env.SystemRoot = "C:\\Windows";

  const env = buildAllowlistEnv("/isolation");
  assert.equal(env.PATH, "/bin");
  assert.equal(env.HOME, "/isolation");
  assert.equal(env.USERPROFILE, "/isolation");
  assert.equal(env.CODEX_HOME, "/isolation");
  assert.match(env.APPDATA, /AppData[\\/]Roaming$/);
  assert.match(env.LOCALAPPDATA, /AppData[\\/]Local$/);
  assert.equal(env.SystemRoot, "C:\\Windows");
  assert.equal(env.EXTRA_VAR, undefined);
  assert.equal(env.OPENAI_API_KEY, undefined);
  assert.equal(env.CODEX_API_KEY, undefined);

  if (originalExtra === undefined) {
    delete process.env.EXTRA_VAR;
  } else {
    process.env.EXTRA_VAR = originalExtra;
  }
  if (originalOpenAiApiKey === undefined) {
    delete process.env.OPENAI_API_KEY;
  } else {
    process.env.OPENAI_API_KEY = originalOpenAiApiKey;
  }
  if (originalCodexApiKey === undefined) {
    delete process.env.CODEX_API_KEY;
  } else {
    process.env.CODEX_API_KEY = originalCodexApiKey;
  }
  if (originalPath === undefined) {
    delete process.env.PATH;
  } else {
    process.env.PATH = originalPath;
  }
  if (originalHome === undefined) {
    delete process.env.HOME;
  } else {
    process.env.HOME = originalHome;
  }
  if (originalSystemRoot === undefined) {
    delete process.env.SystemRoot;
  } else {
    process.env.SystemRoot = originalSystemRoot;
  }
});

test("buildCodexOptions forwards project config overrides", () => {
  const options = buildCodexOptions(
    {
      config: {
        model: "gpt-5.4",
        model_instructions_file: "/tmp/planner.md",
        features: { multi_agent: true },
      },
    },
    "/isolation",
    "/runtime/codex.js"
  );

  assert.equal(options.codexPathOverride, "/runtime/codex.js");
  assert.equal(options.env.CODEX_HOME, "/isolation");
  assert.deepEqual(options.config, {
    model: "gpt-5.4",
    model_instructions_file: "/tmp/planner.md",
    features: { multi_agent: true },
  });
});

test("buildThreadOptions leaves reasoning effort unset unless provided", () => {
  const plannerOptions = buildThreadOptions(
    {
      model: "gpt-5.4",
      sandboxMode: "workspace-write",
      approvalPolicy: "never",
      workingDirectory: "/repo",
    },
    "gpt-5.4"
  );
  assert.equal(plannerOptions.modelReasoningEffort, undefined);

  const explicitOptions = buildThreadOptions(
    {
      model: "gpt-5.4",
      sandboxMode: "workspace-write",
      approvalPolicy: "never",
      workingDirectory: "/repo",
      modelReasoningEffort: "high",
    },
    "gpt-5.4"
  );
  assert.equal(explicitOptions.modelReasoningEffort, "high");
});

test("buildRunStreamOptions omits outputSchema when not provided", () => {
  const withoutSchema = buildRunStreamOptions({
    outputSchema: null,
    abortController: new AbortController(),
  });
  assert.equal(withoutSchema.outputSchema, undefined);

  const withSchema = buildRunStreamOptions({
    outputSchema: { type: "object" },
    abortController: new AbortController(),
  });
  assert.deepEqual(withSchema.outputSchema, { type: "object" });
});

test("localCodexPathCandidates prefers windows-safe entrypoints on win32", () => {
  const candidates = localCodexPathCandidates();
  if (process.platform === "win32") {
    assert.match(candidates[0], /codex\.exe$/);
    assert.match(candidates[1], /codex\.cmd$/);
    return;
  }
  assert.match(candidates[0], /node_modules[\\/]\.bin[\\/]codex$/);
});

test("hasProjectAuth detects project-local auth cache", async () => {
  const { dir } = await makeFixtureAuth();
  const hasAuth = await hasProjectAuth(dir);
  assert.equal(hasAuth, true);
  await rm(dir, { recursive: true, force: true });
});

test("GET /health returns ready when auth cache and runtime are available", async () => {
  const { dir } = await makeFixtureAuth();
  const cleanupRuntime = await makeFixtureRuntime();
  const server = createSidecarServer({ port: 0, runtimeHome: dir });
  const port = await server.start();
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`);
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.status, "READY");
    assert.equal(body.service, "codex-sidecar");
    assert.ok(body.codexPath);
  } finally {
    await server.stop();
    await rm(dir, { recursive: true, force: true });
    await cleanupRuntime();
  }
});

test("GET /health returns auth error when auth cache is missing", async () => {
  const server = createSidecarServer({ port: 0, runtimeHome: path.join(os.tmpdir(), "missing-codex-auth-home") });
  const port = await server.start();
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`);
    const body = await response.json();
    assert.equal(response.status, 500);
    assert.equal(body.status, "AUTH_REQUIRED");
  } finally {
    await server.stop();
  }
});

test("POST /runs validates request body", async () => {
  const { dir } = await makeFixtureAuth();
  const server = createSidecarServer({ port: 0, runtimeHome: dir });
  const port = await server.start();
  try {
    const response = await fetch(`http://127.0.0.1:${port}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    assert.equal(response.status, 400);
    const body = await response.json();
    assert.equal(body.error, "prompt_required");
  } finally {
    await server.stop();
    await rm(dir, { recursive: true, force: true });
  }
});
