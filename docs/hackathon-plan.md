# Application Surgeon: 4-hour hackathon plan

Nov 1, 2026

## Summary

This plan merges the four Surgeon threads into one build for the remaining four hours. The sources are the original spec and proof of concept, [app-compatibility.md](app-compatibility.md), [demo-ideas.md](demo-ideas.md), [interface.md](interface.md) with the design system in `ui/`, and the sub-app docs.

What ships is one vertical slice that matches the spec's acceptance test. The user points at a running app and types a request. Codex investigates the app through Surgeon's tools, writes a manifest, and tests it against the real app. Surgeon runs it, and the user can save it as a shortcut that keeps working after Surgeon and Codex exit.

What we cut to fit four hours:

- The sub-app runtime (daemon watchers, `script` step, bwrap sandbox). The design docs stay as the roadmap and get one line in the pitch.
- Voice, unless an OpenAI API key turns up in the first two hours.
- Image generation, tray menu, companion pointer at 60 Hz, Wayland.

No Surgeon code exists yet. The reusable pieces are the proof of concept in `/tmp/surgeon-poc/` (MCP server, SDK script, Writer export) and the CSS in `ui/`.

## Decisions carried over

These were settled in earlier threads. This plan does not revisit them.

| Decision | Source |
| --- | --- |
| Electron and TypeScript for the shell, plain HTML and CSS, no UI framework | Design system thread, PRODUCT.md |
| Python helper on `/usr/bin/python3` with `gi` does all AT-SPI and D-Bus work | PoC, compatibility tests |
| Codex reaches the desktop only through Surgeon's MCP tools. `codex sandbox` can't reach the accessibility bus anyway | PoC |
| Route order: GTK actions, frame actions, other D-Bus, CLI and URIs, controls by name. Sub-apps last, with consent | Compatibility doc, sub-app docs |
| No screenshots-and-clicks control. Screenshots are context for Codex only | PRODUCT.md |
| Teal, violet and graphite route chips. Irreversible steps need Ctrl+Enter | interface.md |
| X11 only | Every test ran on X11 |
| Docs live in this repo as markdown | Project memory |

## Tech stack

| Part | Choice | Notes |
| --- | --- | --- |
| Shell | Electron, TypeScript compiled with `tsc` | Main process holds `globalShortcut`, the Codex SDK and the panel window |
| UI | `ui/tokens.css` and `ui/surgeon.css` as they are | One focusable panel window. A click-through layer window for the mark is P1 |
| Agent | `@openai/codex-sdk` 0.166.0, ChatGPT login | Same version the PoC ran |
| Helper | Python package `surgeon/` on `/usr/bin/python3` 3.12 | `gi` (Atspi, Gio), `jsonschema` 4.10 is already installed, no new Python deps |
| Contract | `contracts/manifest.schema.json` | One file. Python validates with it, and Codex gets it as `outputSchema` |
| Electron to helper | Helper stdin and stdout, one JSON object per line | Same pattern as the sub-app implementation doc |
| Persistence | GNOME custom keybinding that runs `surgeon-run <id>` | GNOME stores and fires it, so it works with Surgeon closed. gsettings writes were verified in the PoC |
| Storage | `~/.local/share/app-surgeon/extensions/<id>/manifest.json`, jobs in `~/.local/share/app-surgeon/jobs/<id>/` | XDG paths |
| Window capture | `import -window <xid>` | GNOME Shell's screenshot API refuses outside callers |
| Target window | `xprop -root _NET_ACTIVE_WINDOW` read before the panel takes focus | `xdotool` isn't installed. Tab to aim at a control uses AT-SPI `get_accessible_at_point` |

### Repo layout

```
surgeon/              Python helper
  desktop.py          window identity, bounded walker, control matcher, gtk/frame actions
  manifest.py         schema check, denylist, executor, verification checks
  install.py          gsettings keybinding install and uninstall
  mcp.py              Codex tools, scoped to one app, writes the inspection log
  daemon.py           stdin/stdout JSON-lines loop for Electron
  run.py              surgeon-run <id>, what the keybinding executes
contracts/manifest.schema.json
app/                  Electron
  main.ts             shortcut, windows, helper process, Codex job
  job.ts              Codex thread, event mapping, result check
  panel.html, panel.ts
ui/                   existing tokens, components, fonts
tests/
```

## Approach to the main problems

### Launch environment

T3 Code's shell sets `ELECTRON_RUN_AS_NODE=1`, which makes Electron itself run as plain Node. It also sets `NO_AT_BRIDGE`, `GTK_MODULES` and `CHROME_DESKTOP`, and its AppArmor label blocks AT-SPI calls to snap apps. Every dev launch goes through one script:

```bash
systemd-run --user --collect --unit=surgeon-dev --working-directory="$PWD" \
  -E DISPLAY -E XAUTHORITY -E DBUS_SESSION_BUS_ADDRESS -E XDG_RUNTIME_DIR -E PATH \
  "$PWD/node_modules/.bin/electron" app/dist/main.js
```

`systemd-run` starts from the user manager's environment, so the T3 variables don't carry over. `-E NAME` with no value copies it from the calling shell. `PATH` is passed so the nvm Node and `codex` binaries resolve. Demo apps launch the same way, with temp `XDG_DATA_HOME` and LibreOffice's own `-env:UserInstallation`, so nothing lands in the real recent-files list.

### App identity

The accessible app name and PID lie for some apps (Pinta reports as `dotnet` with a proxy PID, VLC registers twice). Surgeon starts from the X window id and reads, in order:

1. `_GTK_APPLICATION_ID`, plus `_GTK_UNIQUE_BUS_NAME` and the object paths, which give the D-Bus address for `gtk_action` directly.
2. `_NET_WM_PID`, then `/proc/<pid>/exe`.
3. `WM_CLASS`, plus the title suffix for LibreOffice modules.

The matching AT-SPI frame is the one whose app PID and title match the window. For flatpak apps, fall back to title alone.

### Walking the tree safely

- Walk the target window only, never the whole desktop.
- Cap at 500 children per node and 20,000 nodes. Calc's sheet reports 2,147,483,647 children.
- Re-fetch from the app root after any window closes. A stale walk crashed STM32CubeIDE.
- Drop "Recent Documents", "Open Recent" and file chooser subtrees, and send no document, terminal or page text to Codex.

### Manifest and executor

The executor implements the step types the demos need, not all ten from the compatibility doc:

| Step | Needed by |
| --- | --- |
| `gtk_action {name, param}` (calls `Describe` first, since disabled actions do nothing) | Image Viewer and GNOME Terminal zoom, Pinta |
| `frame_action {name}` | Text Editor zoom |
| `cli {argv}`, argv[0] must be the target app's own binary, no shell | Alacritty font size, `soffice --convert-to` |
| `activate {role, name, within}` | Writer export, Calculator tutor |
| `set_text {role, name, text}` with `{date}`, `{documents}`, `{stem}` placeholders only | Export filename |
| `wait_for {window, timeout}` and `confirm_if_present {window, button}` | Late and optional dialogs |

Verification checks: `window_appears`, `file_created` (exists and is bigger than zero bytes), `action_state` (a GTK action state changed). The control matcher strips mnemonic underscores and shortcut text, reads the `labelled-by` target and the first line of the description, and keeps only showing controls. The denylist from the compatibility doc runs before any step, on action ids and labels.

`select`, `dbus_call` and `open_uri` wait until a demo needs them. `dbus_call` for `FileManager1.ShowItems` is the first to add, so exports can end with the file selected in Files.

### Codex SDK usage

One Codex instance and one thread per request. The MCP server is configured per instance, so each job's tools are scoped to the target app from the start.

```ts
const codex = new Codex({
  config: {
    mcp_servers: {
      surgeon: {
        command: "/usr/bin/python3",
        args: ["-m", "surgeon.mcp", "--xid", xid, "--job", jobId],
        env: { DISPLAY, DBUS_SESSION_BUS_ADDRESS, XDG_RUNTIME_DIR, HOME, PATH },
        default_tools_approval_mode: "approve", // tools fail under approvalPolicy "never" without this
      },
    },
  },
});
const thread = codex.startThread({
  workingDirectory: jobDir,          // empty per-job dir
  sandboxMode: "read-only",
  networkAccessEnabled: false,
  webSearchMode: "disabled",
  approvalPolicy: "never",
  skipGitRepoCheck: true,
  modelReasoningEffort: "low",       // the PoC finished in 22 s at low
});
const { events } = await thread.runStreamed(
  [{ type: "text", text: prompt }, { type: "local_image", path: shotPath }],
  { outputSchema: manifestSchema, signal: abort.signal },
);
```

Each request becomes one thread, so an inspection log entry tagged with the job id belongs to that request. This settles the assumption in the sub-app implementation doc.

**Tools.** Five, all scoped to one window, all returning JSON with actionable errors:

| Tool | Returns |
| --- | --- |
| `describe_app` | Identity, toolkit, GTK actions with enabled state, frame actions, app binary path, whether the app needs a relaunch flag |
| `find_elements {query, roles?}` | Matching showing controls: role, name, description, actions, containing window |
| `get_tree {depth?}` | Bounded, pruned tree of the target window |
| `inspect_element {role, name}` | States, actions, extents |
| `test_manifest {manifest}` | Runs the real executor and its verification checks, then undoes what it can. Three calls per job at most |

`test_manifest` uses the same executor that `surgeon-run` uses, so a passing test is evidence about the installed extension. Every tool call appends to `jobs/<id>/inspection.jsonl`. Codex can't write there, because its sandbox is read-only.

**Prompt.** It names the target, includes the request, lists the route order, and sets four rules. Use the highest route that covers the request. Call `test_manifest` before answering. Set `verified` only from a passing test. Return `feasible: false` with the reason when no route works. The PoC showed Codex does return an honest `feasible: false`.

**Output schema.** The manifest schema holds `feasible`, `summary`, `steps`, `verification`, `undo`, `routes_tried` (rank and outcome for each) and `verified`. Strict structured output needs every property required and `additionalProperties: false`. Steps are an `anyOf` of one object per step type. Test this in the first hour. If `anyOf` is rejected, fall back to a single step object with nullable fields.

**Trust.** Electron does not believe `verified: true` from Codex. It accepts the manifest only if `inspection.jsonl` has a passing `test_manifest` entry whose manifest hash matches the returned one. Otherwise the plan shows "Not verified" and offers no install. This is the spec's rule that a failed verification never looks like success.

**Progress.** Event mapping to the status line, with no fake percentages and no reasoning text:

| SDK event | Status |
| --- | --- |
| `item.started` for `describe_app`, `find_elements`, `get_tree`, `inspect_element` | Investigating, with the tool's query: "Looking for Export controls" |
| `item.started` for `test_manifest` | Testing |
| `item.completed` for `test_manifest` with a failure | Fixing, attempt 2 of 3 |
| `turn.completed` | Ready, or Can't do this |
| `turn.failed`, `error` | Failed, with the message under Details |

Esc aborts through the `AbortSignal`.

### Persistence

"Save as shortcut" writes the manifest to the extensions dir and adds a GNOME custom keybinding (`Ctrl+Alt+1` to `9`) whose command is `/usr/bin/python3 -m surgeon.run <id>`. `install.py` saves the previous keybinding list so uninstall restores it exactly. `surgeon-run` finds the target window by the stored identity, prefers the active window, and runs the executor. No LLM is involved. The demo proves it by quitting Surgeon and pressing the shortcut.

### Apps Surgeon can't see, and the fallback

- Electron app without the flag: the amber notice from interface.md, "Surgeon needs to restart this app to see inside it", with a relaunch button that adds `--force-renderer-accessibility`.
- Alacritty: `describe_app` reports no tree and a CLI, so Codex only proposes `cli` steps.
- Every other route failed: Codex returns `feasible: false` and the `routes_tried` list, and the panel shows what was tried in one line. The sub-app offer comes after the hackathon. Its gate design is in [sub-app-implementation.md](sub-app-implementation.md).

## Demo

Three beats, about 90 seconds of action. All three use routes that passed in testing.

| Beat | Request | Route shown | Status |
| --- | --- | --- | --- |
| 1. Make it bigger | "Make this bigger" in Image Viewer, then GNOME Terminal, then Alacritty | Teal chip twice, then violet `cli` for an app with no accessibility tree | Each route verified |
| 2. Export shortcut | "Give me a shortcut that exports this as a PDF" in Writer | Graphite `activate` steps, verified by `file_created` | Verified in the PoC |
| 3. It still works | Quit Surgeon, press `Ctrl+Alt+1` in Writer, the PDF appears | `surgeon-run`, no Codex | Untested. GNOME firing the keybinding hasn't been observed yet |

Backup beat if time allows: the Calculator tutor from demo-ideas.md (`activate` 7, ×, 6, = with the mark on each button).

Codex takes about 20 seconds per request. On stage, narrate the status line while it works. Record a full run as a backup video at 3:30.

## Schedule

Times are from now. The freeze at 3:30 is fixed. Cut features to protect it.

| Time | Work | Done when |
| --- | --- | --- |
| 0:00 to 0:20 | Skeleton. `npm i electron @openai/codex-sdk typescript`, the launch script, one empty transparent panel opened by `Ctrl+Alt+Space` | The panel opens from a `systemd-run` launch. Electron isn't cached, so start the download first |
| 0:20 to 1:20 | Helper: identity, walker, matcher, executor with the six step groups, checks, denylist. Port from the PoC | Hand-written manifests for beats 1 and 2 run from the command line and pass their checks |
| 1:20 to 2:00 | `mcp.py` with the five tools and the log, `job.ts`, the schema | A command-line job on Writer returns a manifest that passes the hash check |
| 2:00 to 2:20 | `install.py`, `run.py`, uninstall | Beat 3 works by hand: quit everything, press the key, get the PDF |
| 2:20 to 3:10 | Panel UI: command bar, status line, plan with chips, Run, toast, "Save as shortcut", Details | Beats 1 to 3 run from the panel |
| 3:10 to 3:30 | One P1 item: the mark layer window, or voice if a key exists | |
| 3:30 to 4:00 | Freeze. Two runs from a fresh login session, backup video, README, pitch | |

### Running tracks in parallel

The helper and the panel UI don't share code until 2:20, apart from the JSON-lines messages. A second agent can build the panel from `ui/specimen.html` and `ui/surgeon.css` against a fake helper that replays recorded events, while the main track does the helper and the Codex job. The message list is the contract between them:

| Electron to helper | Helper to Electron |
| --- | --- |
| `target {xid}` | `target {app, title, icon, needs_relaunch}` |
| `run {manifest}` | `step {index, state, extents, message}`, then `done {ok, undo}` |
| `install {manifest, accelerator}`, `uninstall {id}`, `list` | `installed {id, accelerator}`, `extensions [...]` |

### Cut order if behind

1. At 2:00 with no working job: drop to the PoC's single `activate` step and show beat 2 only.
2. Voice, then the mark layer, then the backup beat.
3. The Details view, then "Can't undo" handling (no demo step needs it).

Never cut the hash check on `verified`, the denylist, or the privacy pruning.

## Tests

- `tests/test_manifest.py`: schema rejects unknown step types and a `cli` argv[0] that isn't the app's binary. The denylist blocks `move-trash` and "Clear List". The matcher normalises `_Stopwatch` and "Save Ctrl+S".
- `tests/test_install.py`: install then uninstall restores the original keybinding list, with gsettings stubbed.
- One real desktop test: launch Image Viewer through `systemd-run` with temp XDG dirs, run `gtk_action zoom-set 2.0`, and check the zoom state.

## Voice and image generation

**Voice.** No `OPENAI_API_KEY` exists, and the ChatGPT login doesn't cover transcription. If the hackathon hands out a key, add push-to-talk as a mic button in the command bar: record with `pw-record` on press, stop on second press, send to OpenAI's transcription endpoint, fill the field, and let the user press Enter. Check the model id against the docs when the key arrives. Hold-to-talk on the shortcut needs XRecord in the helper and isn't worth it today. Without a key, the mic button stays hidden.

**Image generation.** `codex features list` shows `image_generation` as stable, and `~/.codex/generated_images/` has output from October. Nobody has tested it through the SDK. It stays out of this build. The planned use is a preview of a companion toolbar before Codex builds it.

## Before the demo

- [ ] Launch Surgeon and every demo app through `systemd-run --user`, never from a T3 terminal.
- [ ] Dismiss Writer's "Tip of the Day" ahead of time. Use demo files only, since trees and the projector show recent files.
- [ ] Check `Ctrl+Alt+Space` and `Ctrl+Alt+1` against the 7 existing custom keybindings.
- [ ] Remove the 6 temp export paths the compatibility tests added to `~/.local/share/recently-used.xbel`, or they show in Writer's recent list.
- [ ] Pitch line on the sub-app fallback and on Wayland (needs a GNOME Shell extension).

## Open questions

- [ ] Will the hackathon provide an OpenAI API key? It decides whether voice is in.
- [ ] Does strict `outputSchema` accept `anyOf` for step types? Answer in the first hour.
- [ ] Does GNOME fire a custom keybinding whose command is a Python module, with the right `DISPLAY` and bus? Answer at 2:00.
