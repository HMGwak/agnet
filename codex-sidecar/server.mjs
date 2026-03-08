import { createServer } from "node:http";
import { access } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const DEFAULT_PORT = 3001;
const HEALTH_PATH = "/health";
const RUNS_PATH = "/runs";
const INTAKE_PATH = "/intake";
const ALLOWED_ENV_KEYS = [
  "PATH",
  "HOME",
  "USERPROFILE",
  "APPDATA",
  "LOCALAPPDATA",
  "HOMEDRIVE",
  "HOMEPATH",
  "SystemRoot",
  "SYSTEMROOT",
  "PATHEXT",
  "COMSPEC",
  "TEMP",
  "TMP",
  "TMPDIR",
  "LD_LIBRARY_PATH",
];
const DEFAULT_OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    output: { type: "string" },
  },
  required: ["output"],
};
const DEFAULT_MODEL = "gpt-5.4";

export function parseArgs(argv = process.argv.slice(2)) {
  const args = {};
  for (const arg of argv) {
    if (arg === "--help") {
      args.help = true;
      continue;
    }
    const [rawName, rawValue] = arg.split("=");
    if (!rawName.startsWith("--")) {
      continue;
    }
    const name = rawName.slice(2);
    if (!rawValue) {
      continue;
    }
    args[name] = rawValue;
  }
  return args;
}

function authFilePath(runtimeHome) {
  return join(runtimeHome, "auth.json");
}

export async function hasProjectAuth(runtimeHome) {
  try {
    await access(authFilePath(runtimeHome));
    return true;
  } catch {
    return false;
  }
}

export function buildAllowlistEnv(runtimeHome) {
  const env = {};
  for (const key of ALLOWED_ENV_KEYS) {
    if (process.env[key]) {
      env[key] = process.env[key];
    }
  }
  if (runtimeHome) {
    env.HOME = runtimeHome;
    env.USERPROFILE = runtimeHome;
    env.CODEX_HOME = runtimeHome;
    env.APPDATA = join(runtimeHome, "AppData", "Roaming");
    env.LOCALAPPDATA = join(runtimeHome, "AppData", "Local");
    const driveMatch = /^[A-Za-z]:/.exec(runtimeHome);
    if (driveMatch) {
      env.HOMEDRIVE = driveMatch[0];
      env.HOMEPATH = runtimeHome.slice(driveMatch[0].length) || "\\";
    }
  }
  return env;
}

function getBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      if (chunks.length === 0) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", (error) => reject(error));
  });
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(payload));
}

function createRunRecord(payload) {
  return {
    status: "starting",
    prompt: payload.prompt,
    outputSchema: payload.outputSchema || null,
    events: [],
    subscribers: new Set(),
    exitCode: null,
    result: null,
    abortController: new AbortController(),
  };
}

function buildCodexOptions(payload, runtimeHome, codexPathOverride) {
  const options = {
    codexPathOverride,
    env: buildAllowlistEnv(runtimeHome),
  };
  if (payload.config && typeof payload.config === "object" && !Array.isArray(payload.config)) {
    options.config = payload.config;
  }
  return options;
}

export function buildThreadOptions(payload, fallbackModel) {
  const options = {
    model: payload.model || fallbackModel,
    sandboxMode: payload.sandboxMode || "workspace-write",
    workingDirectory: payload.workingDirectory || process.cwd(),
    approvalPolicy: payload.approvalPolicy || "never",
    skipGitRepoCheck: true,
  };
  if (payload.modelReasoningEffort) {
    options.modelReasoningEffort = payload.modelReasoningEffort;
  }
  return options;
}

export function buildRunStreamOptions(runRecord) {
  const options = {
    signal: runRecord.abortController.signal,
  };
  if (
    runRecord.outputSchema &&
    typeof runRecord.outputSchema === "object" &&
    !Array.isArray(runRecord.outputSchema)
  ) {
    options.outputSchema = runRecord.outputSchema;
  }
  return options;
}

function formatEvent(event) {
  return `data: ${JSON.stringify(event)}\n\n`;
}

async function runCodexRun(runRecord, payload, runtimeHome, fallbackModel) {
  const { Codex } = await import("@openai/codex-sdk");
  const localCodexPath = await resolveLocalCodexPath();
  const codex = new Codex(buildCodexOptions(payload, runtimeHome, localCodexPath));
  const thread = codex.startThread(buildThreadOptions(payload, fallbackModel));
  const streamed = await thread.runStreamed(runRecord.prompt, buildRunStreamOptions(runRecord));
  let finalText = "";
  for await (const event of streamed.events) {
    runRecord.events.push(event);
    if (event.type === "item.completed" && event.item?.type === "agent_message") {
      finalText = event.item.text || finalText;
    }
    if (event.type === "turn.completed") {
      break;
    }
    if (event.type === "turn.failed") {
      throw new Error(event.error?.message || "turn.failed");
    }
  }
  return finalText;
}

async function runSession(runs, runId, payload, runtimeHome, fallbackModel) {
  const runRecord = runs.get(runId);
  if (!runRecord) return;
  runRecord.status = "running";
  try {
    const result = await runCodexRun(runRecord, payload, runtimeHome, fallbackModel);
    runRecord.result = result;
    runRecord.exitCode = 0;
    runRecord.status = "done";
  } catch (error) {
    if (runRecord.abortController.signal.aborted) {
      runRecord.status = "cancelled";
      runRecord.exitCode = 130;
      runRecord.result = "cancelled";
    } else {
      runRecord.status = "failed";
      runRecord.exitCode = 1;
      runRecord.result = String(error.message || error);
    }
  }
  for (const stream of runRecord.subscribers) {
    stream.write(formatEvent({ type: "state", id: runId, status: runRecord.status }));
    stream.end();
  }
  runRecord.subscribers.clear();
}

export function createSidecarServer({
  runtimeHome = process.cwd(),
  host = "127.0.0.1",
  port = DEFAULT_PORT,
}) {
  const runs = new Map();

  const server = createServer(async (req, res) => {
    if (req.method === "GET" && req.url === HEALTH_PATH) {
      try {
        const codexPath = await resolveLocalCodexPath();
        if (!(await hasProjectAuth(runtimeHome))) {
          sendJson(res, 500, {
            status: "AUTH_REQUIRED",
            detail: `Missing project-local auth cache at ${authFilePath(runtimeHome)}`,
          });
          return;
        }
        sendJson(res, 200, { status: "READY", service: "codex-sidecar", codexPath });
      } catch (runtimeError) {
        sendJson(res, 500, { status: "RUNTIME_NOT_FOUND", detail: String(runtimeError.message || runtimeError) });
      }
      return;
    }

    if (req.method === "POST" && req.url === RUNS_PATH) {
      let body = {};
      try {
        body = await getBody(req);
      } catch {
        sendJson(res, 400, { error: "invalid_json" });
        return;
      }
      if (!body.prompt || typeof body.prompt !== "string") {
        sendJson(res, 400, { error: "prompt_required" });
        return;
      }
      if (!(await hasProjectAuth(runtimeHome))) {
        sendJson(res, 500, { error: "auth_required", detail: `Missing auth cache at ${authFilePath(runtimeHome)}` });
        return;
      }
      const runId = randomUUID();
      const runRecord = createRunRecord(body);
      runs.set(runId, runRecord);
      runSession(runs, runId, body, runtimeHome, DEFAULT_MODEL);
      sendJson(res, 200, { runId, run_id: runId, status: runRecord.status });
      return;
    }

    if (req.method === "GET" && req.url?.startsWith("/runs/") && req.url?.endsWith("/events")) {
      const runId = req.url.split("/")[2]?.split("?")[0];
      const runRecord = runs.get(runId);
      if (!runRecord) {
        sendJson(res, 404, { error: "run_not_found" });
        return;
      }
      if (req.headers.accept === "text/event-stream") {
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        });
        for (const event of runRecord.events) {
          res.write(formatEvent(event));
        }
        if (["done", "failed", "cancelled"].includes(runRecord.status)) {
          res.end(formatEvent({ type: "state", id: runId, status: runRecord.status }));
          return;
        }
        runRecord.subscribers.add(res);
        req.on("close", () => {
          runRecord.subscribers.delete(res);
        });
        return;
      }
      sendJson(res, 200, {
        runId,
        status: runRecord.status,
        events: runRecord.events,
        result: runRecord.result,
        exitCode: runRecord.exitCode,
      });
      return;
    }

    if (req.method === "POST" && req.url?.match(/^\/runs\/[^/]+\/cancel$/)) {
      const runId = req.url.split("/")[2];
      const runRecord = runs.get(runId);
      if (!runRecord) {
        sendJson(res, 404, { error: "run_not_found" });
        return;
      }
      runRecord.abortController.abort();
      runRecord.status = "cancelled";
      for (const stream of runRecord.subscribers) {
        stream.write(formatEvent({ type: "state", id: runId, status: "cancelled" }));
        stream.end();
      }
      runRecord.subscribers.clear();
      sendJson(res, 200, { runId, run_id: runId, status: "cancelled" });
      return;
    }

    if (req.method === "POST" && req.url === INTAKE_PATH) {
      let body = {};
      try {
        body = await getBody(req);
      } catch {
        sendJson(res, 400, { error: "invalid_json" });
        return;
      }
      if (!body.prompt || typeof body.prompt !== "string") {
        sendJson(res, 400, { error: "prompt_required" });
        return;
      }
      if (!(await hasProjectAuth(runtimeHome))) {
        sendJson(res, 500, { error: "auth_required", detail: `Missing auth cache at ${authFilePath(runtimeHome)}` });
        return;
      }
      try {
        const { Codex } = await import("@openai/codex-sdk");
        const localCodexPath = await resolveLocalCodexPath();
        const codex = new Codex(buildCodexOptions(body, runtimeHome, localCodexPath));
        const thread = codex.startThread({
          model: body.model || DEFAULT_MODEL,
          sandboxMode: body.sandboxMode || "workspace-write",
          workingDirectory: body.workingDirectory || process.cwd(),
          approvalPolicy: body.approvalPolicy || "never",
          skipGitRepoCheck: true,
        });
        const result = await thread.run(body.prompt, {
          outputSchema: body.outputSchema || DEFAULT_OUTPUT_SCHEMA,
          signal: new AbortController().signal,
        });

        let responsePayload = {};
        try {
          responsePayload = JSON.parse(result.finalResponse || "{}");
        } catch {
          sendJson(res, 500, {
            error: "intake_non_json_response",
            detail: result.finalResponse || "",
          });
          return;
        }
        sendJson(res, 200, { status: "ok", response: responsePayload });
      } catch (error) {
        sendJson(res, 500, { error: "intake_failed", detail: String(error.message || error) });
      }
      return;
    }

    sendJson(res, 404, { error: "not_found" });
  });

  return {
    server,
    start: () =>
      new Promise((resolve) => {
        server.listen(port, host, () => {
          const actualPort = server.address()?.port ?? port;
          resolve(actualPort);
        });
      }),
    stop: () => new Promise((resolve) => server.close(resolve)),
    getUrl: () => `http://127.0.0.1:${server.address()?.port ?? port}`,
    runs,
  };
}

export async function startSidecar(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    return { help: true };
  }
  const port = Number.parseInt(args.port || process.env.SIDECAR_PORT || String(DEFAULT_PORT), 10);
  const host = args.host || process.env.SIDECAR_HOST || "127.0.0.1";
  const runtimeHome = args["runtime-home"] || args.runtimeHome || process.env.CODEX_RUNTIME_HOME || process.cwd();
  const { start } = createSidecarServer({ runtimeHome, host, port });
  const actualPort = await start();
  return { status: "started", port: actualPort };
}

export { buildCodexOptions };

async function resolveLocalCodexPath() {
  const candidates = localCodexPathCandidates();
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // continue
    }
  }
  throw new Error("local @openai/codex runtime was not found");
}

export function localCodexPathCandidates() {
  const windowsCandidates = [
    fileURLToPath(
      new URL(
        "./node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe",
        import.meta.url
      )
    ),
    fileURLToPath(new URL("./node_modules/.bin/codex.cmd", import.meta.url)),
    fileURLToPath(new URL("./node_modules/@openai/codex/bin/codex.js", import.meta.url)),
    fileURLToPath(new URL("./node_modules/.bin/codex", import.meta.url)),
  ];
  const posixCandidates = [
    fileURLToPath(new URL("./node_modules/.bin/codex", import.meta.url)),
    fileURLToPath(new URL("./node_modules/@openai/codex/bin/codex.js", import.meta.url)),
    fileURLToPath(new URL("./node_modules/.bin/codex.cmd", import.meta.url)),
  ];
  return process.platform === "win32" ? windowsCandidates : posixCandidates;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  startSidecar().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
