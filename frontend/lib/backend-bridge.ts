import { spawnSync } from "node:child_process";
import path from "node:path";

const cwd = process.cwd();
const repoRoot = path.basename(cwd) === "frontend" ? path.resolve(cwd, "..") : cwd;
const bridgePath = path.join(repoRoot, "scripts", "frontend_backend_bridge.py");
const localUcloudRoot = path.join(repoRoot, ".local-ucloud", "data");
const defaultContentUrl = `sqlite:///${path.join(localUcloudRoot, "viewtube_content.sqlite")}`;
const defaultBehaviorUrl = `sqlite:///${path.join(localUcloudRoot, "viewtube_behavior.sqlite")}`;
let cachedPythonDepsPath: string | undefined;

function pythonDepsPath(): string {
  if (cachedPythonDepsPath) return cachedPythonDepsPath;
  const result = spawnSync("python3", [path.join(repoRoot, "scripts", "python_deps_path.py")], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  cachedPythonDepsPath = result.status === 0 && result.stdout.trim() ? result.stdout.trim() : path.join(repoRoot, ".python_deps");
  return cachedPythonDepsPath;
}

type BridgeResponse<T> = { ok: true; status: number; data: T } | { ok: false; status: number; error: string };

function backendMode(): "http" | "subprocess" {
  const mode = process.env.VIEWTUBE_BACKEND_MODE;
  if (mode === "http" || mode === "subprocess") return mode;
  if (process.env.BACKEND_URL || process.env.NODE_ENV === "production") return "http";
  return "subprocess";
}

function backendUrl(): string {
  return (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function throwBridgeError(response: BridgeResponse<unknown>): never {
  const message = response.ok ? "unexpected bridge response" : response.error;
  const error = new Error(message);
  if (!response.ok) {
    (error as Error & { status?: number }).status = response.status;
  }
  throw error;
}

export function runBridge<T>(action: string, payload: Record<string, unknown> = {}): T {
  const result = spawnSync("python3", [bridgePath], {
    cwd: repoRoot,
    input: JSON.stringify({ action, payload }),
    encoding: "utf8",
    maxBuffer: 50 * 1024 * 1024,
    env: {
      ...process.env,
      PYTHONPATH: `${pythonDepsPath()}:${path.join(repoRoot, ".python_deps")}:${repoRoot}${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ""}`,
      DATABASE_URL: process.env.DATABASE_URL ?? defaultContentUrl,
      CONTENT_DATABASE_URL:
        process.env.CONTENT_DATABASE_URL ?? (process.env.DATABASE_URL ? process.env.DATABASE_URL : defaultContentUrl),
      BEHAVIOR_DATABASE_URL:
        process.env.BEHAVIOR_DATABASE_URL ?? (process.env.DATABASE_URL ? process.env.DATABASE_URL : defaultBehaviorUrl),
    },
  });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(result.stderr || `backend bridge exited with ${result.status}`);
  }

  const raw = result.stdout.trim().split("\n").at(-1) ?? "";
  const response = JSON.parse(raw) as BridgeResponse<T>;
  if (!response.ok) {
    throwBridgeError(response);
  }
  return response.data;
}

async function runHttpBridge<T>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch(`${backendUrl()}/bridge`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action, payload }),
    cache: "no-store",
  });
  const body = (await response.json().catch(() => ({
    ok: false,
    status: response.status,
    error: `backend HTTP ${response.status}`,
  }))) as BridgeResponse<T>;
  if (!body.ok) {
    throwBridgeError(body);
  }
  return body.data;
}

export async function backendAction<T>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  if (backendMode() === "http") {
    return runHttpBridge<T>(action, payload);
  }
  return runBridge<T>(action, payload);
}
