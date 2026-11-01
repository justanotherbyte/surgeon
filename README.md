# Application Surgeon

Press Ctrl+Alt+Space over a desktop app and type what you want done in it. Codex inspects the app through Surgeon's accessibility and D-Bus tools, writes a manifest of steps, and tests it on the real window. Surgeon shows the plan, runs it, and can save it as a GNOME shortcut that works with Surgeon closed.

The build follows [docs/hackathon-plan.md](docs/hackathon-plan.md). It runs on Ubuntu 24.04, GNOME 46, X11 only.

## Setup

Requirements already on this machine: Node 24 (nvm), `/usr/bin/python3` 3.12 with `gi` and `jsonschema`, the `codex` CLI logged in with ChatGPT, and `xprop`, `wmctrl` and ImageMagick's `import`.

```bash
npm install
node node_modules/electron/install.js   # only if node_modules/electron/dist is missing
npm run build
```

npm on this machine skips install scripts, so Electron's binary needs the second line once.

## Run

```bash
npm run dev                  # builds, then starts Surgeon as the systemd user unit surgeon-dev
scripts/demo-apps.sh         # Image Viewer, Writer with a demo document, GNOME Terminal, Alacritty
systemctl --user stop surgeon-dev
```

Click an app, press Ctrl+Alt+Space, type a request and press Enter. When the plan appears, Enter runs it. "Save as shortcut" binds the next free Ctrl+Alt+1 to 9.

Always launch Surgeon and the demo apps through these scripts, never from a T3 Code terminal. T3 Code sets `ELECTRON_RUN_AS_NODE`, `NO_AT_BRIDGE` and `GTK_MODULES`, and its AppArmor label blocks AT-SPI calls to snap apps. `systemd-run --user` starts from the user manager's environment instead. The dev script also passes `--no-sandbox`, because Ubuntu 24.04 refuses Chromium's SUID sandbox unless `chrome-sandbox` is owned by root.

Run one Codex job without the UI:

```bash
systemd-run --user --wait --pipe -E DISPLAY -E DBUS_SESSION_BUS_ADDRESS -E XDG_RUNTIME_DIR -E HOME -E PATH \
  --working-directory="$PWD" node app/dist/job.js <window-id> "Make this bigger"
```

Get window ids from `wmctrl -lx`.

## Tests

```bash
npm test                                         # schema, denylist, matcher, hash, keybinding install
SURGEON_DESKTOP_TESTS=1 npm test                 # also drives a real Image Viewer (run outside T3 Code)
```

## Layout

| Path | What it does |
| --- | --- |
| `surgeon/desktop.py` | Window identity from X properties, the bounded AT-SPI walker, the control matcher, GTK and frame actions |
| `surgeon/manifest.py` | Schema check, denylist, the executor and its verification checks. `test_manifest`, Run and `surgeon-run` all use it |
| `surgeon/mcp.py` | The seven MCP tools Codex gets, scoped to one window. Logs every call to `jobs/<id>/inspection.jsonl` |
| `surgeon/daemon.py` | JSON-lines helper process for Electron |
| `surgeon/install.py`, `surgeon/run.py` | GNOME keybinding install and uninstall, and what the keybinding runs |
| `surgeon/subapps.py`, `surgeon/sandbox.py` | Sub-app install gate, storage and watcher, and the script sandbox |
| `contracts/manifest.schema.json` | The manifest contract. Python validates with it and Codex gets it as `outputSchema` |
| `app/` | Electron main process, Codex job, panel |
| `ui/` | Design tokens and components, see [docs/interface.md](docs/interface.md) |

Data lives in `~/.local/share/app-surgeon/`: `jobs/<id>/` holds each request's screenshot, inspection log and manifest, and `extensions/<id>/manifest.json` holds saved shortcuts.

## Apps Surgeon can't see into

Electron apps (VS Code, Obsidian, Typora) show Surgeon their controls only when started with `--force-renderer-accessibility`, and Firefox-family browsers (Firefox, Zen) only with `GNOME_ACCESSIBILITY=1`. When you summon Surgeon over one, the panel offers **Restart <app>**:

1. Surgeon closes the app's windows the normal way, so the app can still ask about unsaved work or open tabs.
2. It waits for the app to exit, then starts it again as it was: the same command line and folder, plus the fix. Flatpaks such as Zen go through their `.desktop` launcher with `flatpak run --env=...`. Electron overwrites its own `/proc/<pid>/environ`, so in that case the app gets the session's environment.
3. It checks that the new window really shows Surgeon its controls.

If any step fails, for example because the app is waiting on a "Save changes?" question, the panel says why and shows a command to paste into a terminal after quitting the app, with a Copy button. "Not now" hides the offer for that app until Surgeon restarts. Watch and title helpers don't need accessibility.

## How a plan earns "Tested"

Codex's `verified: true` is only a claim. Surgeon marks a plan as tested only if the job's `inspection.jsonl` holds a passing `test_manifest` entry whose hash matches the steps, checks and undo that Codex returned. Codex's sandbox is read-only, so it can't write that log. Plans that fail this check show "Not verified" and can't be saved.

## Sub-apps: new features for an app

Ask for a feature the app doesn't have, and Codex returns a sub-app: something that runs beside the app with a trigger and steps. Four kinds:

| Kind | Example request | What it does |
| --- | --- | --- |
| Toolbar | "Give me a toolbar with buttons to rotate clockwise, rotate counter-clockwise and flip horizontally" in Pinta | Buttons docked inside the app window's top-right corner while it's active. Each button runs its own steps |
| Save trigger | "Every time I save this notebook, also export it as a PDF next to it" in Xournal++ | Runs steps each time you save the open file |
| Hotkey | "Give me a hotkey that lists the 10 largest files under the folder I'm scanning" in Disk Usage Analyzer | Runs steps on a key, only while that app is active |
| App opened | "When Image Viewer opens, zoom to 100%" | Runs steps when the app opens. Every step must be reversible |
| Title | "After 10 seconds on X in Zen, open a new Zen window" | Runs steps once per visit when the app's window title matches a pattern for N seconds while that window is in front |
| Watch | "Notify me when this terminal stops changing, so I know my command finished" | Samples the app window every 2 to 60 s and runs steps when it changes, or when it stops changing after a change |

Steps use the app's own actions, controls and command line, the same as a normal plan. For work the app can't do at all, a sub-app can run a Python script and show its output in a panel beside the app or as a desktop notification.

### Opening apps and creating files

- **`launch` step.** Opens any installed app through its own `.desktop` entry, with no shell, including flatpaks such as Zen (found by `StartupWMClass`). Arguments may only be http(s) URLs, existing file paths, `{created}`, or `--new-window`, `--new-tab`, `--new-instance` and `--private-window`. Terminal emulators are refused. Codex finds desktop ids with the `list_apps` tool.
- **Files from scripts.** A script still can't write outside its temp folder. It writes new files to `./out/`, and its step's `outputs_to` names where Surgeon copies them, for example `{document.dir}`. The destination must be a visible folder inside your home folder, so nothing can go to `~/.config` or outside home. Existing files are never overwritten: a clash gets `-1`. At most 20 files and 500 MB per run. `{created}` is then the first new file's path. Tests delete the files they create and close windows their `launch` steps opened.
- **`{document.path}`** comes from the app's command line or, for single-instance apps that got the file over D-Bus, from the app's latest matching entry in the recent-files list. Only that one path is used.

Example: "Give me a hotkey that inverts the colours of this image and opens the result" in Image Viewer becomes a script that writes `out/<name>-inverted.png`, delivered to the image's folder, then `launch org.gnome.eog {created}`.

### Watching windows and the screen

- **`watch` trigger.** Only the app's own window, never the whole screen. A window capture holds that window's pixels only, so Surgeon's panels and GNOME's notifications don't show up in it. A screen watcher would trigger on Surgeon's own output. A change is at least 3 pixels of a 32x32 grayscale sample moving by more than 24 levels: on GNOME Terminal a printed line moved 4 to 17 and a cursor blink 2.
- **`capture` step.** Saves a screenshot of the app window, or the whole screen, into the run's temp folder for a later script to read. Scripts have PIL and numpy. The consent view tags a whole-screen capture "Sees your whole screen".
- **`capture_window` tool.** While building, Codex can take a fresh screenshot of the target window, for example to see the app after a test. It has no whole-screen tool.
- **Nothing a script outputs goes to Codex.** During a test, Codex learns only how many rows or characters each panel got.

- **Install gate.** Surgeon offers a sub-app only if its own test passed for exactly that sub-app, testing every toolbar button and its undo. A sub-app with a script must also prove that the app's own routes can't do the work: the job's inspection log has to show `describe_app` and `find_elements` ran and agree with each claimed outcome. "Unsuitable" outcomes can't be checked mechanically, so the consent view marks them "Codex judged".
- **Consent.** The panel shows the trigger, every step with its route and any "Can't undo" tag, what the sub-app reads, and any script in full. Enter doesn't install; press Install or Ctrl+Enter.
- **Sandbox.** Scripts run under Landlock and seccomp (`surgeon/sandbox.py`). They can read files and `/proc`, but can't open any socket, write outside a temp dir, or signal another process. Ubuntu 24.04 blocks user namespaces for unconfined processes, so `bwrap` can't run from Surgeon's daemon.
- **Runtime.** The daemon checks the window list and watched files once a second. Sub-apps arm on an app's main windows, not its dialogs. A save fires once the file's modification time holds for a second, and changes during the sub-app's own run don't count. Three failed runs in a row turn a sub-app off.
- **Manage.** Installed sub-apps appear in the command bar's saved list for their app, with Turn off and Remove.

`{document.path}` and `{document.dir}` are the open file, found from the app's command line and matched against the window title. They are empty when the file was opened from inside the app. Sub-apps run only while Surgeon is running, unlike saved shortcuts. They live in `~/.local/share/app-surgeon/subapps/<id>/subapp.json`.

## Remove a saved shortcut

```bash
echo '{"id":1,"cmd":"uninstall","ext_id":"<id>"}' | PYTHONPATH=. /usr/bin/python3 -m surgeon.daemon
```

Ids are the directory names under `~/.local/share/app-surgeon/extensions/`.
