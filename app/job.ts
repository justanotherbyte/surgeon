// One request = one Codex thread whose MCP tools are scoped to the target window.
import { Codex, type ThreadEvent } from "@openai/codex-sdk";
import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { Helper, REPO, cleanEnv } from "./helper.js";

const SCHEMA = JSON.parse(fs.readFileSync(path.join(REPO, "contracts/manifest.schema.json"), "utf8"));
const DATA = path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local/share"), "app-surgeon");

export type Manifest = {
  feasible: boolean; summary: string; steps: any[]; verification: any[]; undo: any[];
  routes_tried: { rank: number; route: string; outcome: string }[]; verified: boolean;
};
export type Status = { phase: "investigating" | "testing" | "fixing"; text: string };
export type JobResult = { jobId: string; manifest: Manifest | null; verified: boolean; error?: string; seconds: number };

function prompt(app: string, title: string, request: string) {
  return `You are Application Surgeon. The user is looking at ${app} (window "${title}") and asked:
"${request}"

You can't reach the desktop from the shell. Use only the surgeon MCP tools, which are scoped to this one window. The screenshot shows it.

Write a manifest that does what the user asked in this app. Use the highest route that covers the request:
1. gtk_action: GTK actions from describe_app, by exact name (win.zoom-in). Check enabled and the parameter type.
2. frame_action: GTK 4 window actions from describe_app frame_actions.
4. cli: the app's own binary (cli_argv0_allowed), no shell. For Alacritty, "alacritty msg config -w {window_id} font.size=20" changes the open window and "alacritty msg config -w {window_id} --reset" undoes it.
5. activate, set_text, wait_for, confirm_if_present: controls by role and exact name from find_elements.

Rules:
- Call describe_app first.
- Call test_manifest with the full manifest before answering. It runs the steps on the real app, checks verification, then runs undo. You get 3 tests.
- Include a verification check that proves the result: action_state for a stateful GTK action that the change flips, file_created for exports, window_appears for dialogs. If no check fits, use an empty list.
- Fill undo with steps that reverse the change. For exports, undo is empty.
- Set verified=true only if test_manifest passed for exactly the steps, verification and undo you return. Return them unchanged after a pass.
- If no route works, return feasible=false, empty steps, the reason in summary, and every route you tried in routes_tried.
- Never use blocked actions (delete, trash, quit, kill, clear history).
- Save files under {documents} with a new name each run, for example "{documents}/{stem}-{date}-{time}.pdf", so no "Replace?" dialog appears. Use the same path in set_text and file_created.
- Labels are short and plain, like "Zoom to 200%". The summary is one line for the user.`;
}

function toolStatus(tool: string, args: any, tests: number): Status {
  switch (tool) {
    case "describe_app": return { phase: "investigating", text: "Reading the app" };
    case "find_elements": return { phase: "investigating", text: `Looking for ${args?.query ?? ""} controls`.replace("  ", " ") };
    case "get_tree": return { phase: "investigating", text: "Reading the window" };
    case "inspect_element": return { phase: "investigating", text: `Checking ${args?.name ?? "a control"}` };
    case "test_manifest": return { phase: "testing", text: tests > 1 ? `Testing, attempt ${tests} of 3` : "Testing on the real app" };
    default: return { phase: "investigating", text: "Investigating" };
  }
}

export async function runJob(opts: {
  xid: string; app: string; title: string; request: string; helper: Helper;
  onStatus: (s: Status) => void; signal?: AbortSignal;
}): Promise<JobResult> {
  const t0 = Date.now();
  const jobId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${Math.random().toString(36).slice(2, 6)}`;
  const jobDir = path.join(DATA, "jobs", jobId);
  fs.mkdirSync(jobDir, { recursive: true });
  const seconds = () => Math.round((Date.now() - t0) / 1000);

  const input: any[] = [{ type: "text", text: prompt(opts.app, opts.title, opts.request) }];
  try {
    await promisify(execFile)("import", ["-window", opts.xid, path.join(jobDir, "shot.png")], { timeout: 10000 });
    input.push({ type: "local_image", path: path.join(jobDir, "shot.png") });
  } catch { /* screenshot is context only */ }

  const env = cleanEnv();
  const pick = (keys: string[]) => Object.fromEntries(keys.map((k) => [k, env[k] ?? ""]));
  const codex = new Codex({
    env,
    config: {
      mcp_servers: {
        surgeon: {
          command: "/usr/bin/python3",
          args: ["-m", "surgeon.mcp", "--xid", opts.xid, "--job", jobId],
          env: pick(["DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "HOME", "PATH", "PYTHONPATH"]),
          default_tools_approval_mode: "approve", // MCP tools fail under approvalPolicy "never" without this
          tool_timeout_sec: 90,
        },
      },
    },
  });
  const thread = codex.startThread({
    workingDirectory: jobDir, sandboxMode: "read-only", networkAccessEnabled: false, webSearchMode: "disabled",
    approvalPolicy: "never", skipGitRepoCheck: true, modelReasoningEffort: "low",
  });

  let final = "";
  let tests = 0;
  try {
    const { events } = await thread.runStreamed(input, { outputSchema: SCHEMA, signal: opts.signal });
    for await (const e of events as AsyncGenerator<ThreadEvent>) {
      if (e.type === "item.started" && e.item.type === "mcp_tool_call") {
        if (e.item.tool === "test_manifest") tests++;
        opts.onStatus(toolStatus(e.item.tool, e.item.arguments, tests));
      } else if (e.type === "item.completed" && e.item.type === "mcp_tool_call" && e.item.tool === "test_manifest") {
        const text = (e.item.result?.content?.[0] as any)?.text ?? "{}";
        let passed = false;
        try { passed = JSON.parse(text).passed; } catch { /* error text */ }
        if (!passed && tests < 3) opts.onStatus({ phase: "fixing", text: `Fixing, attempt ${tests + 1} of 3` });
      } else if (e.type === "item.completed" && e.item.type === "agent_message") {
        final = e.item.text;
      } else if (e.type === "turn.failed") {
        return { jobId, manifest: null, verified: false, error: e.error.message, seconds: seconds() };
      } else if (e.type === "error") {
        return { jobId, manifest: null, verified: false, error: e.message, seconds: seconds() };
      }
    }
  } catch (err: any) {
    const msg = opts.signal?.aborted ? "Stopped" : String(err?.message ?? err);
    return { jobId, manifest: null, verified: false, error: msg, seconds: seconds() };
  }

  let manifest: Manifest;
  try { manifest = JSON.parse(final); } catch {
    return { jobId, manifest: null, verified: false, error: "Codex returned no manifest", seconds: seconds() };
  }
  fs.writeFileSync(path.join(jobDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  // Codex's verified flag is a claim. Trust only a passing test_manifest in our own log with the same hash.
  const { verified } = manifest.feasible
    ? await opts.helper.call<{ verified: boolean }>("check", { job: jobId, manifest })
    : { verified: false };
  return { jobId, manifest, verified, seconds: seconds() };
}

// Command line: node app/dist/job.js <xid> <request...>
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [xid, ...words] = process.argv.slice(2);
  const helper = new Helper();
  const t = await helper.call("target", { xid });
  const r = await runJob({
    xid: t.ident.xid, app: t.app, title: t.ident.title, request: words.join(" "), helper,
    onStatus: (s) => console.log(`[${s.phase}] ${s.text}`),
  });
  console.log(JSON.stringify(r, null, 2));
  helper.close();
}
