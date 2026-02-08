import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const PID_FILE = resolve(process.cwd(), ".playwright", "servers.json");

function tryKill(pid: number) {
  try {
    process.kill(pid, "SIGTERM");
  } catch {
    // ignore
  }
}

export default async function globalTeardown() {
  try {
    const raw = readFileSync(PID_FILE, "utf-8");
    const parsed = JSON.parse(raw) as { frontendPid: number | null; backendPid: number | null };
    if (parsed.frontendPid) tryKill(parsed.frontendPid);
    if (parsed.backendPid) tryKill(parsed.backendPid);
  } catch {
    // ignore
  }
}

