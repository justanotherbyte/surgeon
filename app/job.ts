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
const MAX_TESTS = 5; // keep in step with MAX_TESTS in surgeon/mcp.py
const DATA = path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local/share"), "app-surgeon");

export type Manifest = {
  feasible: boolean; summary: string; steps: any[]; verification: any[]; undo: any[]; subapp: any | null;
  routes_tried: { rank: number; route: string; outcome: string }[]; verified: boolean;
};
export type Status = { phase: "investigating" | "testing" | "fixing"; text: string };
export type JobResult = {
  jobId: string; manifest: Manifest | null; verified: boolean; error?: string; seconds: number;
  gate?: string[]; // sub-apps only: why Surgeon refuses to offer it, empty if it may
};

function prompt(app: string, title: string, request: string) {
  return `You are Application Surgeon. The user is looking at ${app} (window "${title}") and asked:
"${request}"

You can't reach the desktop from the shell. Use only the surgeon MCP tools, which are scoped to this one window. The screenshot shows it.

Write a manifest that does what the user asked in this app. Use the highest route that covers the request:
1. gtk_action: GTK actions from describe_app, by exact name (win.zoom-in). Check enabled and the parameter type.
2. frame_action: GTK 4 window actions from describe_app frame_actions.
4. cli: the app's own binary (cli_argv0_allowed), no shell. launch: open an installed app through its own .desktop entry ("app": a desktop id from list_apps, or null for the target app's launcher from describe_app, which also works for flatpaks). launch args may only be http(s) URLs, existing file paths, {created}, or --new-window, --new-tab, --new-instance, --private-window. Terminal emulators can't be launched. For Alacritty, "alacritty msg config -w {window_id} font.size=20" changes the open window and "alacritty msg config -w {window_id} --reset" undoes it.
5. activate, set_text, wait_for, confirm_if_present: controls by role and exact name from find_elements.

Rules:
- Call describe_app first.
- Call test_manifest with the full manifest before answering. It runs the steps on the real app, checks verification, then runs undo. You get ${MAX_TESTS} tests. If one fails, read the error, fix the plan and test again.
- Include a verification check that proves the result: action_state for a stateful GTK action that the change flips, file_created for exports, window_appears for dialogs. If no check fits, use an empty list.
- Fill undo with steps that reverse the change. For exports, undo is empty.
- Set verified=true only if test_manifest passed for exactly the steps, verification and undo you return. Return them unchanged after a pass.
- Always deliver a working solution. If the exact request can't be done, build the closest version that does work and say in the summary what differs, for example "Zen can't be told how long you spent on X, so this opens a new window after 10 seconds with X's title in front". Consider every tool you have before settling: a different route, a sub-app (toolbar, hotkey, file_saved, title, watch trigger), a sandboxed script, launching another installed app that can do the job, creating files, a panel or notification.
- Return feasible=false only when even the closest version is impossible or would need a blocked action, after you have used your tests. Then give the reason in summary and every route you tried in routes_tried.
- Never use blocked actions (delete, trash, quit, kill, clear history).
- When a save or export dialog is involved, use a new file name each run, for example "{documents}/{stem}-{date}-{time}.pdf", so no "Replace?" dialog appears. Use the same path in set_text and file_created. A cli step can write a fixed name next to the document, such as "{document.dir}/{stem}.pdf".
- Labels are short and plain, like "Zoom to 200%". The summary is one line for the user.
- Set subapp to null for a normal plan.

Sub-apps extend the app with features it doesn't have. Return one (feasible=true, subapp filled) when the user asks for a new feature, button, toolbar, automation or helper, rather than a one-off action. Kinds, by subapp.trigger.type:
- "toolbar": new buttons beside the app, shown while its window is active. Put 1 to 6 buttons in subapp.buttons, each with a short label, its own steps and its own undo. Top-level steps stay empty. Good for actions buried in menus or dialogs, or several steps in one click, for example "Shrink to 800 px" as gtk_action resize, set_text, confirm_if_present. trigger.accelerator may name a key that focuses the toolbar for keyboard users.
- "file_saved": run steps each time the user saves the file at trigger.path, usually "{document.path}". For example "export a PDF every time I save" as a cli step with the app's own binary. {document.path} and {document.dir} are the open file's path and folder; describe_app's placeholders show whether Surgeon could resolve them.
- "hotkey": run steps when the user presses trigger.accelerator in the app.
- "app_opened": run steps when the app opens. Every step must be reversible.
- "title": fires once per visit when the app's active window title matches trigger.title.pattern (a case-insensitive regular expression) continuously for trigger.title.seconds. For "after 10 seconds on X in Zen", match the page title shown in the window title, for example "/ X" before " — Zen Browser". Only time while that window is active counts.
- "watch": sample the app window every trigger.watch.interval seconds (2 to 60). mode "changed" fires when the window's pixels change; "settled" fires once they stop changing after a change, for "tell me when the render, export or download finishes". Only the app window can be watched, never the whole screen. Pair it with a "notify" step.
Two more sub-app steps: "capture" saves a screenshot of the app window (source "window") or the whole screen (source "screen") into the run's working directory, where a later script opens it by file name (PIL and numpy are available). Use "screen" only when the user asks about other windows or the whole screen; the user sees a warning. "notify" shows a desktop notification, with an earlier script's stdout as the body if source is set. The capture_window tool shows you the app window now, to plan a watch or a pixel-reading script.
Pick keys the app doesn't use. Steps use the same routes and rank order as a normal plan.
Scripts are the last resort (rank 8): only when ranks 1 to 5 can't do the work at all (for example the app's results aren't in the accessibility tree), add "script" steps. A script is Python you write in subapp.scripts. It runs sandboxed: it can read files and /proc, but has no network, no sockets, no D-Bus or X11, and can't write outside its temp dir. To create files, a script writes them into ./out/ and sets outputs_to on its step to a folder such as "{document.dir}" or "{documents}" (inside the home folder, not hidden). Surgeon copies them there without overwriting anything, then {created} is the first new file's path for later steps, for example a launch step that opens it, or a file_created check. Name new files after the original, such as "out/<stem>-inverted.png"; the original's path is {document.path}. Tests delete created files and close windows launched by the test. A script prints its result to stdout: a JSON list of strings for a list, or plain text. test_manifest tells you only how many rows or characters a panel got, never the text, so print a clear message when the script finds nothing. A "panel" step shows that output beside the app. Script args may use {window.title}, {app.id}, {pid}, {document.path}. The window title is often only a file or folder name; /proc/{pid}/cmdline may hold the path the app was opened with.
Only when a script step exists: call describe_app (ranks 1 to 4) and find_elements with a real query (rank 5) first, and fill subapp.exhausted with one entry per rank 1 to 5. Outcomes: "unavailable" only when describe_app listed none of that route (rank 1 gtk_actions, 2 frame_actions, 3 dbus_names are empty), "no_match" only for rank 5 when a find_elements search returned nothing, "failed" when a test of that route failed, otherwise "unsuitable" with the reason. Without scripts, exhausted is empty.
Say in subapp.reads what the sub-app reads or changes, in plain words. Buttons is empty unless the trigger is "toolbar". Test the whole sub-app with test_manifest (it runs every toolbar button and its undo), and set verified=true only on a pass. Return the tested trigger, steps, buttons and scripts unchanged. Surgeon checks every claim against its own log and shows the user every step and script before installing.`;
}

function toolStatus(tool: string, args: any, tests: number): Status {
  switch (tool) {
    case "describe_app": return { phase: "investigating", text: "Reading the app" };
    case "find_elements": return { phase: "investigating", text: `Looking for ${args?.query ?? ""} controls`.replace("  ", " ") };
    case "get_tree": return { phase: "investigating", text: "Reading the window" };
    case "inspect_element": return { phase: "investigating", text: `Checking ${args?.name ?? "a control"}` };
    case "test_manifest": return { phase: "testing", text: tests > 1 ? `Testing, attempt ${tests} of ${MAX_TESTS}` : "Testing on the real app" };
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
        if (!passed && tests < MAX_TESTS) opts.onStatus({ phase: "fixing", text: `Fixing, attempt ${tests + 1} of ${MAX_TESTS}` });
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
  const gate = manifest.feasible && manifest.subapp
    ? (await opts.helper.call<{ reasons: string[] }>("subapp_check", { job: jobId, manifest, xid: opts.xid })).reasons
    : undefined;
  return { jobId, manifest, verified, seconds: seconds(), gate };
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
