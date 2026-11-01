# Application Surgeon: sub-app implementation

Nov 1, 2026

## Summary

This doc says how to build the sub-app fallback described in [sub-app-fallback.md](sub-app-fallback.md). No Surgeon code exists yet, so every module name and message below is a proposal. The facts it relies on come from [app-compatibility.md](app-compatibility.md) and the trigger probe in the fallback doc.

The build has five parts:

1. A sub-app manifest format: one target app, one trigger, and a list of steps.
2. An install gate in the helper that refuses a sub-app unless Surgeon's own inspection log shows ranks 1 to 5 were checked for that app and that request. The gate runs before Surgeon offers the sub-app.
3. A consent screen in the overlay that shows what failed, what the sub-app does, what it reads, and any script in full.
4. A watcher loop in the helper that arms a sub-app while its app is open and runs its steps when the trigger fires.
5. Two new step types, `script` and `panel`, for the work the app can't do.

## Where the code goes

PRODUCT.md fixes the stack. The Electron main process (TypeScript) owns the overlay, global shortcuts and the Codex SDK. The Python helper (`/usr/bin/python3` with `gi`) owns AT-SPI and D-Bus.

The helper needs two entry points from one Python package:

| Entry point | Started by | Lifetime | Job |
| --- | --- | --- | --- |
| `surgeon-helper mcp` | Codex, as a stdio MCP server | One Codex thread | Read-only inspection tools for Codex. Writes the inspection log |
| `surgeon-helper daemon` | Electron main, once at startup | The whole session | Runs manifests, hosts sub-app watchers |

Sub-apps must live in the daemon, because the MCP process exits when its Codex thread ends. Electron starts the daemon with `NO_AT_BRIDGE`, `GTK_MODULES`, `ELECTRON_RUN_AS_NODE` and `CHROME_DESKTOP` removed from its environment, for the reasons in the compatibility doc. Electron itself must start from GNOME or `systemd-run --user`, never from inside T3 Code.

Electron and the daemon talk over the daemon's stdin and stdout, one JSON object per line. The daemon writes logs to stderr only.

Proposed files:

| File | Contents |
| --- | --- |
| `helper/surgeon_helper/subapps.py` | Manifest validation, the install gate, storage, arm and disarm |
| `helper/surgeon_helper/triggers.py` | systemd, file, AT-SPI and hotkey trigger sources |
| `helper/surgeon_helper/inspect_log.py` | The append-only log of inspection calls, shared by both entry points |
| `app/src/main/subapps.ts` | RPC to the daemon, hotkey registration, the consent screen and panels |

## Sub-app manifest

A sub-app is a JSON file. Codex writes it. The daemon validates it and stores it at `~/.config/surgeon/subapps/<id>.json`, with its scripts in `~/.local/share/surgeon/subapps/<id>/`.

```json
{
  "kind": "subapp",
  "id": "baobab-top-folders",
  "request_id": "req-0091",
  "request": "show me the biggest folders",
  "app": { "gtk_application_id": "org.gnome.baobab", "wm_class": "baobab" },
  "exhausted": [
    { "rank": 1, "log": "insp-0412", "outcome": "unsuitable", "reason": "43 actions, none lists folder sizes" },
    { "rank": 2, "log": "insp-0413", "outcome": "unsuitable", "reason": "16 frame actions, none lists folder sizes" },
    { "rank": 3, "log": "insp-0414", "outcome": "unavailable", "reason": "No D-Bus API besides org.gtk.*" },
    { "rank": 4, "log": "insp-0415", "outcome": "unavailable", "reason": "baobab is not on the CLI allowlist" },
    { "rank": 5, "log": "insp-0416", "outcome": "no_match", "reason": "0 controls matched 'size'. The results list is not in the tree" }
  ],
  "reads": ["folder sizes under the folder you pick"],
  "trigger": { "type": "hotkey", "accelerator": "Ctrl+Alt+D" },
  "steps": [
    { "id": "sizes", "type": "script", "file": "top_folders.py", "args": ["{window.title}"] },
    { "id": "show", "type": "panel", "title": "Biggest folders", "source": "sizes" }
  ]
}
```

The `app` block uses the identity order from the compatibility doc: `_GTK_APPLICATION_ID`, then the window's PID and `/proc/<pid>/exe`, then WM_CLASS, then the flatpak id. Fields Codex leaves out are not checked.

Argument templates allow only these names. The daemon substitutes them into argv strings and never runs a shell.

| Name | Value |
| --- | --- |
| `{window.title}` | Title of the matched app window when the trigger fired |
| `{trigger.path}` | The file path, for `file_saved` triggers |
| `{app.id}` | The matched `_GTK_APPLICATION_ID` or WM_CLASS |

### New step types

`script {file, args}` runs `/usr/bin/python3 -I <subapp dir>/<file> <args>` with no shell, the sub-app dir as cwd, a 30-second timeout and a 64 KB cap on stdout. A non-zero exit code fails the run. Python only, so the consent screen shows one language.

Scripts are read-only and can't talk to other processes. The daemon wraps every script in `bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-net --unshare-pid --die-with-parent --clearenv --seccomp <fd>`. Each flag closes one way out:

| Flag | Blocks |
| --- | --- |
| `--ro-bind / /` | Writes anywhere except the private `/tmp` |
| `--unshare-net` | The network, and abstract Unix sockets such as X11's `@/tmp/.X11-unix/X0` |
| `--unshare-pid`, `--proc /proc` | Signals to host processes. Without it, a script could `os.kill()` the target app or Surgeon |
| `--clearenv` | `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS` and other inherited addresses |
| `--seccomp` | Creating any `AF_UNIX` socket. Without it, a read-only bind still lets a script connect to socket files: the session bus, the system bus, Docker, IBus (in `~/.cache`), Codex's IPC socket and Orca's daemon socket all accepted connections |

The seccomp filter is one rule: `socket(AF_UNIX, ...)` returns `EACCES`. The daemon builds it once at startup with `ctypes` against `libseccomp.so.2` (installed: 2.5.5) using `seccomp_rule_add_array` and `seccomp_export_bpf`, and passes it to `bwrap` on a file descriptor. Hiding socket directories with `--tmpfs` does not work, because sockets live all over `$HOME`.

On this machine, under that wrapper, a write into `$HOME` failed with "Read-only file system". Connecting to all six sockets named above failed with "Permission denied", a TCP connect failed with "Network is unreachable", and `os.kill()` on a host PID failed with "No such process". Reading `$HOME` still worked.

Only a script's stdout leaves the sandbox, and only into a `panel`, never to the model. A sub-app changes the app or files only through the other steps, which go through the executor's denylist.

`panel {title, source}` shows the stdout of an earlier step in an overlay panel beside the app window. If stdout parses as a JSON list of strings, the panel shows a list of at most 50 rows. Otherwise it shows plain text. The renderer sets `textContent`, never HTML.

A sub-app may also use the existing step types, except that the install gate rejects any step that hits the denylist and any step marked irreversible. A sub-app runs unattended, so it can't ask for the per-run confirm that PRODUCT.md principle 3 requires.

## The install gate

Codex could claim it tried every route without doing so. The gate checks the claim against a record Codex can't write.

**The inspection log.** Every MCP inspection tool appends one entry to `~/.local/state/surgeon/inspect.log` (JSON lines) before it returns. Each entry has an id, the request id, a timestamp, the tool name, the query, the target app identity and a short result, such as "43 actions" or "0 controls matched 'size'". Codex sees the entry id in the tool result and cites it in `exhausted`.

Electron gives each user request an id and puts it in the MCP server's `env` as `SURGEON_REQUEST_ID` when it starts that request's Codex thread. The tools read the id from their environment, so Codex can't attach an inspection to a different request. This assumes one Codex thread per request.

Each `exhausted` entry records one outcome:

| Outcome | Meaning | What the gate checks |
| --- | --- | --- |
| `unavailable` | The route does not exist for this app | The log entry shows the rank's not-applicable condition from the table below |
| `no_match` | The route exists, but nothing matched the request | The log entry's query is non-empty and its result has 0 matches |
| `unsuitable` | Matches exist, but none does the job | Nothing mechanical. The consent screen marks the reason as Codex's judgment |
| `failed` | Surgeon ran the route and it did not work | The executor logged a failed step for this request and this route |

| Rank | Inspection tool that counts | Counts as not applicable when |
| --- | --- | --- |
| 1 | `list_gtk_actions` | The window has no `_GTK_UNIQUE_BUS_NAME` |
| 2 | `list_frame_actions` | The accessible frame exposes no `win.*` or `page.*` actions |
| 3 | `list_dbus_names` | Never. The tool checks the app's bus names and the known APIs (MPRIS, `FileManager1`, search providers) |
| 4 | `list_cli_routes` | The app has no binary on the CLI allowlist and no URI scheme |
| 5 | `find_controls` | Never |

The gate accepts a manifest only if all of these hold:

1. `exhausted` has one entry for each of ranks 1 to 5.
2. Each entry's `log` id exists, names the rank's tool, carries the manifest's `request_id`, matches the manifest's `app`, and passes the check for its outcome.
3. The app is not an Electron or Firefox window that is missing its accessibility enabler. The test is the compatibility doc's: the tree shows only the app and one frame. In that case the gate refuses and Electron offers the relaunch.
4. Every step passes the denylist, and no step is marked irreversible.

The gate runs twice. Electron sends `subapp.check` before it shows the consent screen, so Surgeon never offers a sub-app that fails the gate. `subapp.install` runs the gate again, because the log could have changed in between.

The gate proves Surgeon checked each route for this request. It can't prove an `unsuitable` judgment is right. Characters is the case to watch: its search provider matches a request for a character, so rank 3 has to come back `unsuitable` with a reason the user can reject on the consent screen.

Rank 7 (config-file edits) is not part of the gate, because nobody has tested it. When it ships, it gets a row in the table.

## Consent and UI

The plan surface in `ui/` gets a sub-app variant with four parts:

- One line naming the gap, built from the `exhausted` reasons. Reasons with outcome `unsuitable` show "Codex judged".
- One line on what the sub-app does, and the `reads` list.
- The trigger, in words: "When you press Ctrl+Alt+D in Disk Usage Analyzer".
- Each `script` file in full, scrollable, in the mono font.

Enter does not install. The user presses an explicit Install button, as for irreversible steps. The overlay needs a fourth route chip, `helper`, next to the existing action, command and control chips. Its colour needs a new token in `ui/tokens.css`.

While a sub-app is armed, a small marker with its name sits at the app window's top-right corner. A settings list shows every installed sub-app with an on/off switch and a Remove button.

## Runtime

### Arming

The daemon calls `org.freedesktop.systemd1.Manager.Subscribe`, then listens for `UnitNew` and `UnitRemoved`. At startup it also calls `ListUnitsByPatterns` with `["active"]` and `["app-*.scope"]` to catch apps that are already open.

Scope names follow the systemd desktop-app convention, `app[-<launcher>]-<app id>-<random>.scope`. The probe saw `app-gnome-org.gnome.Software-4479.scope` and `app-flatpak-app.zen_browser.zen-5294.scope`. To get the app id, the parser removes `app-` and the `-<digits>.scope` suffix, removes a leading `gnome-` or `flatpak-`, then unescapes `\xNN`, which turns `Evolution\x2dalarm\x2dnotify` into `Evolution-alarm-notify`.

The scope only says an app started. When a scope's app id matches an installed sub-app, the daemon waits up to 10 seconds for a window whose identity matches the `app` block, then arms the sub-app on that window's XID. Windows are matched by identity, not by PID, because flatpak apps such as Pinta report a proxy PID.

Apps started outside GNOME's launcher may not get a scope. As a fallback, the daemon reads `_NET_CLIENT_LIST` on the root window at startup, then watches `PropertyNotify` for it, and checks each window against installed sub-apps.

The daemon disarms a sub-app when its window is destroyed or its scope is removed. Disarming removes every listener the sub-app registered.

### Trigger types

| Type | Fields | Source | Notes |
| --- | --- | --- | --- |
| `app_opened` | none | Arming | Fires once per arm |
| `file_saved` | `path` | `Gio.FileMonitor` on the parent folder with `WATCH_MOVES` | Fires on `CHANGES_DONE_HINT` for the path, or on a move or rename onto the path, because many editors save to a temp file and rename it. Debounced by 500 ms |
| `hotkey` | `accelerator` | Electron `globalShortcut` | A global shortcut takes the keys from every app, so Electron registers it only while the armed window is active and unregisters it when focus leaves. The daemon watches `_NET_ACTIVE_WINDOW` on the root window and sends `subapp.focus`. If `register` returns false, the marker says the keys are taken |
| `atspi_event` | `event` from an allowlist | One `Atspi.EventListener` per event type, shared, dispatched by app | Allowlist: `object:state-changed:focused`, `object:state-changed:checked`, `object:state-changed:selected`, `window:create` |

`object:text-changed:*` is not on the `atspi_event` allowlist. Those events carry the inserted text, and PRODUCT.md principle 5 says private text stays private by default. Nothing found so far needs them.

### Running

- Each sub-app runs one trigger at a time. A trigger that arrives during a run is dropped, not queued.
- Events from a sub-app's own run don't count, so a `file_saved` sub-app that rewrites its own file can't loop. The daemon ignores triggers until 2 seconds after the run ends.
- Steps run through the same executor as normal manifests, with the same denylist and walker caps (500 children per node, 20,000 nodes, re-fetch from the app root after a window closes).
- A failed step stops the run. Electron shows one line naming the sub-app and the step.
- Three failed runs in a row turn the sub-app off. Electron says so, and the settings list shows it as off.

### Messages

Electron to daemon:

| Message | Fields |
| --- | --- |
| `subapp.check` | `manifest`, `scripts` (file name to content) |
| `subapp.install` | `manifest`, `scripts` (file name to content) |
| `subapp.set_enabled` | `id`, `enabled` |
| `subapp.remove` | `id` |
| `subapp.trigger` | `id`, `xid` (sent for hotkeys) |

Daemon to Electron:

| Message | Fields |
| --- | --- |
| `subapp.checked`, `subapp.installed` or `subapp.rejected` | `id`, and `reasons` for a rejection |
| `subapp.armed` and `subapp.disarmed` | `id`, `xid`, `accelerator` if any |
| `subapp.focus` | `id`, `active` |
| `subapp.step` | `id`, `step`, `state` (`running`, `done` or `failed`), `message` |
| `subapp.panel` | `id`, `xid`, `title`, `rows` or `text` |
| `subapp.disabled` | `id`, `reason` |

If the daemon exits, Electron restarts it once. The daemon reloads enabled sub-apps from `~/.config/surgeon/subapps/` and re-arms those whose app is open. A second exit within a minute leaves sub-apps off and tells the user.

## Testing

Unit tests, with no desktop needed:

- The scope-name parser, on the four names the probe saw, including the `\x2d` escape and the `gnome-` and `flatpak-` prefixes.
- The install gate: a missing rank, a log id from another request, a log id for another app, `no_match` on an entry with matches, an Electron window without its flag, and a denylisted step each cause a rejection.
- Argument templates: unknown names are rejected, and a title containing spaces or `;` stays one argv entry.
- The `file_saved` debounce and the 2-second self-trigger guard, with a fake clock.
- The script sandbox: inside the wrapper, connecting to the session bus socket and to a socket file in `$HOME`, writing to `$HOME`, a TCP connect, and signalling a host PID must all fail, while reading `$HOME` works.

Desktop tests, run through `systemd-run --user` with the launch rules from the compatibility doc (temp XDG dirs, `GSETTINGS_BACKEND=memory`):

1. Arming. Launch Calculator in an `app-*.scope`, check that `subapp.armed` arrives with its XID, close it, and check `subapp.disarmed`. Then start Calculator without a scope before the daemon starts, and check that it still arms.
2. A file trigger. A Xournal++ sub-app runs `cli xournalpp --create-pdf` on save. Save twice and check two PDFs and no loop.
3. The demo case. The Disk Usage Analyzer sub-app above, with a hotkey and a panel.

A spawned test app inherits its launcher's stdout, which hung the earlier probe. Tests must redirect a launched app's output.

## Build order

1. The daemon entry point and the line-based RPC, with the existing manifest executor.
2. The inspection log in the MCP tools. It helps debugging even before sub-apps exist.
3. Arming from systemd scopes, and the `app_opened` trigger.
4. `file_saved` and `hotkey`, then `script` and `panel`.
5. The install gate and the consent screen. Nothing installs before these exist.
6. `atspi_event`, last, because nothing found so far needs it.

## Open questions

- [ ] Where does the Disk Usage Analyzer sub-app get the scanned folder? Nobody has checked whether the window title or the tree holds its full path. If neither does, `top_folders.py` needs another source, and the demo case is not ready.
- [ ] Should Codex be able to update an installed sub-app, or does every change go through the gate and consent again? This doc assumes the second.
- [ ] While the armed window is active, Surgeon's shortcut takes its keys from that app too. Codex should pick keys the app doesn't use, but nobody has checked how to list an app's shortcuts.
