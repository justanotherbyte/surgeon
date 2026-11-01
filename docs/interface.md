# Application Surgeon: interface and stack

Nov 1, 2026

## Summary

Surgeon's UI is a small companion that sits beside the cursor and grows into one panel only when you call it. You press Ctrl+Alt+Space, type a request about the app under the cursor, read the plan, and press Enter. The companion moves to each control as Surgeon acts on it, then one line confirms the result and offers an undo.

The UI is plain HTML and CSS in Electron overlay windows. The Electron main process owns shortcuts, cursor tracking and the Codex SDK. The existing Python helper keeps doing AT-SPI and D-Bus work as an MCP server.

The visual system is in [ui/tokens.css](../ui/tokens.css) and [ui/surgeon.css](../ui/surgeon.css). Open [ui/specimen.html](../ui/specimen.html) in Chrome to see every surface in both themes and a replay of demo 5.

## Interaction model

### One request, start to finish

1. **Summon.** Tap Ctrl+Alt+Space. The command bar opens below and to the right of the cursor, aimed at the window under it. The target chip shows the app icon, name and document, for example "Pinta photo.png".
2. **Aim.** Tab switches the target from the whole window to the control under the cursor, for requests like "what does this do".
3. **Ask.** Type the request. Up and Down pick a saved or recent command for this app instead.
4. **Plan.** Enter sends the request. The companion spins while Codex writes the manifest, then the bar becomes a plan: each step in plain words, with a route chip showing how Surgeon will do it.
5. **Run.** Enter runs the plan. For each step the companion moves to the control and a mark brackets it. Steps check off as they finish. Esc stops after the current step.
6. **Confirm.** The plan closes into a toast: "Rotated and resized photo.png. Undo Ctrl+Alt+Z". The toast closes after 4 seconds.

### Keys

| Keys | Action | When |
| --- | --- | --- |
| Ctrl+Alt+Space | Open the command bar aimed at the window under the cursor | Anywhere |
| Hold Ctrl+Alt+Space | Talk instead of type, release to send | Once voice ships |
| Tab | Aim at the control under the cursor. In a plan, edit the request | Bar or plan open |
| Up, Down | Pick a saved or recent command | Bar open |
| Enter | Plan the request, then run the plan | Bar or plan open |
| Ctrl+Enter | Run a plan that has a step that can't be undone | Plan open |
| Esc | Close, or stop a running plan after the current step | Any panel |
| Ctrl+Alt+Z | Undo Surgeon's last run | Anywhere |
| Ctrl+Alt+1 to 9 | Run a saved command for the app in front | Anywhere |

GNOME already uses Super+Space to switch input sources, so the summon key avoids Super. Every key is a default and can be changed from the tray menu.

### Voice later

Voice uses the same key: tap to type, hold to talk. While the key is held, the command bar shows the words as they are transcribed, and release sends them. Electron's `globalShortcut` reports key presses but not releases, so hold-to-talk needs a key listener in the Python helper (XRecord on X11). Without an API key, whisper.cpp running locally is the likely engine.

### What each surface is for

| Surface | Shows | Leaves when |
| --- | --- | --- |
| Companion | Surgeon's state at the cursor: idle, aiming, planning, acting, done, blocked | Never. It can be hidden when idle from the tray menu |
| Command bar | Target chip, text field, saved commands for this app | Enter or Esc |
| Plan | Steps with route chips, undo status, Run or Confirm | The run ends, or Esc |
| Mark | Corner brackets on the control Surgeon is acting on, with the step's route | The step ends |
| Toast | One line of result and the undo key | After 4 s or on the next summon |
| Notice | What Surgeon can't do and the fix: restart an Electron app, blocked action, command-line only | A button or Esc |
| Tray menu | Helper status, recent requests, the summon key, privacy switches | Click outside |

### Rules the plan follows

- **Route chips have three colours.** Teal is a named action (`gtk_action`, `frame_action`, `dbus_call`). Violet is the app's own command line or URI (`cli`, `open_uri`). Graphite with a hollow square is pressing a control by name (`activate`, `select`, `set_value`, `confirm_if_present`). Graphite is the most fragile route, so the user can see when a plan depends on button labels.
- **Undoable plans run on Enter.** A step that can't be undone, such as overwriting a file, gets an amber "Can't undo" tag, and the plan needs Ctrl+Enter.
- **Blocked actions never reach the plan.** A request that hits the denylist gets a red notice naming the action and saying the user can still do it in the app.
- **Electron apps that started without the accessibility flag** get an amber notice offering to restart them. This matches the restart step in [app-compatibility.md](app-compatibility.md).

## Stack

| Part | Choice | Why |
| --- | --- | --- |
| Shell | Electron, TypeScript | Hosts the Codex TypeScript SDK in the main process. Transparent always-on-top windows and `globalShortcut` work on X11 |
| UI | Plain HTML and CSS, no framework | There are seven small surfaces with little state. CSS `light-dark()` follows the GNOME colour scheme through `nativeTheme` |
| Fonts | Inter (variable, bundled), Ubuntu Sans Mono for route names | Inter is the open face closest to SF Pro. Both ship in `ui/fonts` |
| Desktop access | Existing Python helper (`/usr/bin/python3`, `gi`, AT-SPI), run as an MCP server | Already tested against 31 apps. Must run from GNOME or `systemd-run --user` |
| Hold-to-talk keys | Python helper with XRecord | `globalShortcut` has no key-up event |

### Windows

| Window | Settings | Holds |
| --- | --- | --- |
| Layer | Full-screen, `transparent: true`, `focusable: false`, `alwaysOnTop` at level `screen-saver`, `setIgnoreMouseEvents(true)` | Companion, mark, toast |
| Panel | Small, `transparent: true`, frameless, `alwaysOnTop`, focusable, moved to the cursor each time it opens | Command bar, plan, notices |
| Tray | Electron `Tray` with a popover window | Tray menu. Ubuntu ships the AppIndicator extension; stock GNOME needs it installed |

The main process polls `screen.getCursorScreenPoint()` at 60 Hz while the companion is visible and sends the position to the layer window. Electron has no global mouse-move event. Control positions for the mark come from AT-SPI extents, which the helper returns with each step.

Panels open below and to the right of the cursor and flip left or up when they would cross a screen edge. They grow from the corner nearest the cursor.

### Limits

- **No blur.** Mutter doesn't blur behind transparent windows, so panels are solid at 96 to 97 percent opacity. CSS `backdrop-filter` inside the window can't see the desktop.
- **X11 only.** Wayland blocks global shortcuts, cursor polling and always-on-top placement for ordinary clients. A Wayland version would need a GNOME Shell extension.
- **Focus.** The panel window has to take focus for typing. On close, Surgeon has to give focus back to the target app, or GTK 4 popovers and Electron menus in that app won't respond. See the focus findings in [app-compatibility.md](app-compatibility.md).

## Open questions

- [ ] Does Ctrl+Alt+Space clash with anything the user already binds?
- [ ] Should the companion show when idle by default? The specimen shows it at 55 percent opacity.
- [ ] How long are saved commands kept per app, and can they be shared as manifest files?
