# Application Surgeon: the sub-app fallback

Nov 1, 2026

## Summary

A sub-app is a small helper that Surgeon runs beside one app. It starts when that app opens, watches for a trigger, and does a feature the app itself can't be made to do. Surgeon only offers one after every route in [app-compatibility.md](app-compatibility.md) has failed for the request, and it tells the user before installing it.

The idea works on this machine. A probe today confirmed three of the trigger sources a sub-app needs. The design questions are what a sub-app may do when it fires, and how Surgeon proves the other routes failed first.

- **Watching and the fallback are separate features.** "When I open Alacritty, start the test watcher" needs a trigger, but rank 4 (the CLI) does the work. A trigger can sit in front of any route. Only a sub-app that does the work outside the app is the last resort.
- **A sub-app acts on the app through the same routes as everything else.** It does not add screenshots or synthetic mouse clicks. PRODUCT.md rules those out. If a feature can only be reached by clicking pixels, a sub-app won't make it reachable.
- **What a sub-app adds is its own work and its own UI.** For example, it can run `du` on the folder Disk Usage Analyzer scanned and list the results in a Surgeon panel, because the app's results list is not in the tree.

## Where it sits in the route order

The compatibility doc ranks six routes, plus config-file edits as an untested seventh. The sub-app is eighth.

| Rank | Route | Status |
| --- | --- | --- |
| 1 to 5 | GTK actions, frame actions, other D-Bus, CLI and URIs, accessibility controls | Tested, see app-compatibility.md |
| Enabler | Relaunch with `--force-renderer-accessibility` (Electron) or `GNOME_ACCESSIBILITY=1` (Firefox) | Tested. This comes before a sub-app, because it opens ranks 2 to 5 |
| 7 | Config-file edits with backup and restore | Untested |
| 8 | Sub-app beside the app | This doc |

### Proving the other routes were tried

Codex writes the manifest, so Codex could reach for a sub-app too early. Surgeon should reject a sub-app manifest unless it carries one entry per earlier route, each with the reason it failed. The reasons come from what Surgeon read, not from Codex's guess:

- "No GTK action or frame action matches", from the action list Surgeon fetched.
- "The control is not in the tree", for example Disk Usage Analyzer's results list.
- "The menu won't open", for example a GTK 4 popover.
- "The CLI needs a saved file, and this document is unsaved."

Characters shows why this check matters. Its grid is missing from the tree, which looks like a sub-app case, but its search provider (rank 3) already returns characters by name.

### Telling the user

Before installing a sub-app, Surgeon shows one line on what failed and one line on what the sub-app will do and see:

> Disk Usage Analyzer doesn't show its results to Surgeon. Surgeon can run a helper beside it that lists the biggest folders itself. It reads folder sizes only.

The user confirms explicitly, the same as an irreversible step. While a sub-app runs, a small marker beside the app names it, and Surgeon lists installed sub-apps with an off switch. This follows principles 2, 3 and 4 in PRODUCT.md.

## Trigger sources

All of these are open to an unprivileged user process on X11. The probe ran through `systemd-run --user` and launched Calculator with a clean environment.

| Trigger | Source | Status |
| --- | --- | --- |
| App opened or closed | systemd `UnitNew` and `UnitRemoved` for `app-<desktop-id>-<pid>.scope`. GNOME starts every app it launches in a scope like this | Verified. The signal arrived as the app started |
| Control focus, text, state | AT-SPI event listeners (`object:state-changed:focused`, `object:text-changed:insert`) | Verified. Events arrived from Calculator, and filtering by app name worked |
| File written | `Gio.FileMonitor` (inotify) | Verified. It reported `created`, `changed` and `changes-done-hint` |
| Window focus | `_NET_ACTIVE_WINDOW` on the root window | Untested. AT-SPI `window:activate` did not fire for a window that opened without focus |
| App state signals | D-Bus `PropertiesChanged` (MPRIS), `org.gtk.Actions.Changed` | Untested |
| User hotkey | Electron `globalShortcut`, already in the stack for Surgeon's own shortcut | Not probed |

Apps started from a terminal may not get an `app-*.scope`. Surgeon can fall back to watching `_NET_CLIENT_LIST` and matching windows by the identity order in the compatibility doc.

### Triggers to rule out

- **Every keystroke.** XInput2 and the AT-SPI keystroke listener both see all typing in all apps. That is a keylogger. Use a hotkey instead.
- **Text-change events in private apps.** `object:text-changed:insert` carries each inserted string. A sub-app may subscribe to text events only in the app it belongs to, and never send the text to the model by default (principle 5).

## What a sub-app is made of

A sub-app should be a manifest, not free code: one trigger, then steps from the existing ten step types. Two new pieces cover the work the app can't do:

- A `panel` step that shows a list, a button or a short message in Surgeon's overlay beside the app.
- A `script` step that runs a Codex-written script for the work itself. `cli` can't do this, because it only runs the app's own binary. Demo 8 already needs one (the XDot stepping script). Surgeon shows the script to the user before installing it.

The Python helper runs every sub-app. It already holds the AT-SPI connection and can use Gio. It registers a sub-app's watchers when the app's scope appears and drops them when the scope goes away, so a sub-app costs nothing while its app is closed. The Electron process draws the panels.

## Candidates from the compatibility gaps

| App and gap | Sub-app | Verdict |
| --- | --- | --- |
| Disk Usage Analyzer: results list not in the tree | On a hotkey, run `du` on the scanned folder and list the top items in a panel. Folder from the window title | Good candidate. Every earlier route failed in testing |
| Xournal++: "export a PDF every time I save" | `FileMonitor` on the `.xopp` file, then `cli xournalpp --create-pdf` | A trigger plus rank 4. Not a fallback, though it uses the same watcher |
| Typora: Export > PDF opened no dialog | Watch the `.md` file and convert it on save | Blocked. No converter is installed (no `pandoc`) |
| GTKWave: no zoom state in the tree | None. The Tcl script at launch (rank 4) covers it | Not a sub-app case |
| Electron app open without the flag | None. Relaunch first | Not a sub-app case |
| Alacritty: no tree at all | Only for work `alacritty msg` can't do, which nobody has asked for yet | Not needed yet |

## Risks

- **Event load.** Registering an AT-SPI listener makes every accessible app on the bus emit events, not only the target. Register narrow event types and only while the target app is open.
- **Crashes.** A tree walk crashed STM32CubeIDE. A sub-app must follow the walker safety rules in the compatibility doc, and re-fetch from the app root after any window closes.
- **Wayland.** systemd scopes, AT-SPI and Gio work there. `_NET_ACTIVE_WINDOW`, `_NET_CLIENT_LIST` and the `_GTK_*` window properties do not.
- **Probe leftover.** A launched app inherits its launcher's stdout. A watcher that spawns an app must detach its output, or the watcher's caller waits for the app to exit.

## Open questions

- [ ] Does a sub-app need any step beyond `panel` and `cli` scripts, or does that cover every gap found so far?
- [ ] Should triggers in front of ranks 1 to 5 (the Xournal++ case) ship in the same release, since they reuse the sub-app's watchers but need no fallback warning?
- [ ] Do sub-app scripts run in a sandbox, and if so, which one? `codex sandbox` can't reach the accessibility bus, but a script that only reads files doesn't need it.
