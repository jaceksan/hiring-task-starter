import { spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const PID_DIR = resolve(process.cwd(), ".playwright");
const PID_FILE = resolve(PID_DIR, "servers.json");

async function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForHttp(url: string, timeoutMs: number) {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const res = await fetch(url, { method: "GET" });
      if (res.ok) return;
    } catch {
      // ignore
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error(`Timed out waiting for ${url}`);
    }
    await sleep(250);
  }
}

function startServer(command: string, args: string[], cwd: string): ChildProcess {
  const cp = spawn(command, args, {
    cwd,
    stdio: "inherit",
    env: { ...process.env },
  });
  if (!cp.pid) throw new Error(`Failed to start: ${command} ${args.join(" ")}`);
  return cp;
}

export default async function globalSetup() {
  mkdirSync(PID_DIR, { recursive: true });

  // Reuse existing servers if they are already running.
  const frontendUrl = "http://127.0.0.1:3000";
  const backendUrl = "http://127.0.0.1:8000/docs";

  const reuseOnly = process.env.E2E_REUSE_ONLY === "1";

  let startedFrontend: ChildProcess | null = null;
  let startedBackend: ChildProcess | null = null;

  // Detect running frontend.
  try {
    await waitForHttp(frontendUrl, 1_000);
  } catch {
    if (reuseOnly) {
      throw new Error(
        "Frontend is not running on :3000 and E2E_REUSE_ONLY=1 is set. Start it manually: npm run dev"
      );
    }
    startedFrontend = startServer(
      "npm",
      ["run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"],
      process.cwd()
    );
  }

  // Detect running backend.
  try {
    await waitForHttp(backendUrl, 1_000);
  } catch {
    if (reuseOnly) {
      throw new Error(
        "Backend is not running on :8000 and E2E_REUSE_ONLY=1 is set. Start it manually: cd ../backend && uv run fastapi dev main.py"
      );
    }
    const backendCwd = resolve(process.cwd(), "..", "backend");
    startedBackend = startServer(
      "uv",
      ["run", "python", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
      backendCwd
    );
  }

  // Wait until both are ready.
  await waitForHttp(frontendUrl, 60_000);
  await waitForHttp(backendUrl, 60_000);

  writeFileSync(
    PID_FILE,
    JSON.stringify(
      {
        frontendPid: startedFrontend?.pid ?? null,
        backendPid: startedBackend?.pid ?? null,
      },
      null,
      2
    ),
    "utf-8"
  );
}

