// The Python helper (surgeon.daemon) over stdin/stdout, one JSON object per line.
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

// T3 Code leaks these into child processes; they hide apps from AT-SPI or break Electron apps.
export function cleanEnv(extra: Record<string, string> = {}): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined && !["ELECTRON_RUN_AS_NODE", "NO_AT_BRIDGE", "GTK_MODULES", "CHROME_DESKTOP"].includes(k)) env[k] = v;
  }
  return { ...env, PYTHONPATH: REPO, ...extra };
}

type Pending = { resolve: (v: any) => void; reject: (e: Error) => void; onEvent?: (e: any) => void };

export class Helper {
  private proc: ChildProcessWithoutNullStreams;
  private next = 1;
  private pending = new Map<number, Pending>();

  constructor() {
    this.proc = spawn("/usr/bin/python3", ["-m", "surgeon.daemon"], { cwd: REPO, env: cleanEnv() });
    this.proc.stderr.on("data", (d) => process.stderr.write(`[helper] ${d}`));
    this.proc.on("exit", (code) => {
      for (const p of this.pending.values()) p.reject(new Error(`Surgeon's helper exited (${code})`));
      this.pending.clear();
    });
    readline.createInterface({ input: this.proc.stdout }).on("line", (line) => {
      let msg: any;
      try { msg = JSON.parse(line); } catch { return; }
      const p = this.pending.get(msg.id);
      if (!p) return;
      if (msg.event) return p.onEvent?.(msg.event);
      this.pending.delete(msg.id);
      msg.ok ? p.resolve(msg.result) : p.reject(new Error(msg.error));
    });
  }

  call<T = any>(cmd: string, args: Record<string, unknown> = {}, onEvent?: (e: any) => void): Promise<T> {
    const id = this.next++;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onEvent });
      this.proc.stdin.write(JSON.stringify({ id, cmd, ...args }) + "\n");
    });
  }

  close() { this.proc.kill(); }
}
