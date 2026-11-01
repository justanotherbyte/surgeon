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
| `surgeon/mcp.py` | The five MCP tools Codex gets, scoped to one window. Logs every call to `jobs/<id>/inspection.jsonl` |
| `surgeon/daemon.py` | JSON-lines helper process for Electron |
| `surgeon/install.py`, `surgeon/run.py` | GNOME keybinding install and uninstall, and what the keybinding runs |
| `contracts/manifest.schema.json` | The manifest contract. Python validates with it and Codex gets it as `outputSchema` |
| `app/` | Electron main process, Codex job, panel |
| `ui/` | Design tokens and components, see [docs/interface.md](docs/interface.md) |

Data lives in `~/.local/share/app-surgeon/`: `jobs/<id>/` holds each request's screenshot, inspection log and manifest, and `extensions/<id>/manifest.json` holds saved shortcuts.

## How a plan earns "Tested"

Codex's `verified: true` is only a claim. Surgeon marks a plan as tested only if the job's `inspection.jsonl` holds a passing `test_manifest` entry whose hash matches the steps, checks and undo that Codex returned. Codex's sandbox is read-only, so it can't write that log. Plans that fail this check show "Not verified" and can't be saved.

## Remove a saved shortcut

```bash
echo '{"id":1,"cmd":"uninstall","ext_id":"<id>"}' | PYTHONPATH=. /usr/bin/python3 -m surgeon.daemon
```

Ids are the directory names under `~/.local/share/app-surgeon/extensions/`.
