# Application Surgeon: app compatibility findings

Nov 1, 2026

## Summary

Surgeon can extend 22 of the 31 apps tested on this machine. Four of those (VS Code, Chrome, Obsidian, Cursor) work only after a relaunch with an accessibility flag. Eight are partial, and only Alacritty is invisible to accessibility tools, though its IPC socket works.

- **Most GNOME and GTK apps publish their commands by name.** Pinta's `rotatecw` and Files' `new-tab` work over D-Bus, with no menu clicking. Surgeon should try these named actions first and fall back to clicking controls by name.
- **Clicking controls by name works but is fragile.** LibreOffice, Xournal++, Calculator and the Chromium apps all passed real tests. Unnamed icon buttons, stale labels and GTK 4 menus that won't open broke it elsewhere.
- **The manifest needs about ten step types**, not one. It also needs a control matcher that reads descriptions and checked states, and an app identity based on window properties.
- **Inspection is not harmless.** A walk crashed STM32CubeIDE, Calc's sheet hung an unbounded walk, and trees expose recent files, document text and terminal text.
- **Surgeon's helper must run outside T3 Code.** T3 Code's AppArmor label blocks access to snap apps, and the environment it passes down hides other apps from accessibility tools.

## Method

Five parallel test agents each took one group of installed apps and probed them the same way Surgeon would. Machine: Ubuntu 24.04, GNOME 46, X11 session.

| Group | Apps |
| --- | --- |
| GNOME and GTK core | Text Editor, Files, Calculator, Clocks, Characters, Image Viewer, Document Viewer, Disk Usage Analyzer |
| Office and documents | LibreOffice Calc, Impress, Draw (Writer already proven), Xournal++, Typora |
| Media and graphics | VLC, Pinta (flatpak), GTKWave, XDot, PulseAudio Volume Control |
| Electron and browsers | VS Code, Obsidian, Firefox (snap), Google Chrome, Cursor |
| Terminals and other toolkits | GNOME Terminal, Ghostty, Alacritty, Sublime Text, KiCad, System Monitor, STM32CubeIDE |

For each app the agents checked:

1. Whether it registers on the accessibility bus, and which enabler it needs if not.
2. Tree size, walk time, and how many controls expose actions.
3. One harmless control activated semantically, with an observed result.
4. Native routes: D-Bus names, GTK actions, MPRIS, CLI flags, URI schemes, keybinding config files.
5. Stable identity (WM\_CLASS, desktop id, accessible name), window screenshot capture, and what private data the tree exposes.

Safety rules for every agent: fresh instances with temp profiles and disposable files in /tmp, no contact with apps the user already had open, only reversible actions such as opening About dialogs, no settings changes, and no Codex runs. Messaging, password and account apps (Signal, WhatsApp, HEY, Basecamp, ChatGPT, Passwords and Keys, Zoom) were left out on purpose because their trees would expose private messages or credentials.

## Compatibility matrix

22 of 31 apps tested are good targets, 4 of them only when launched with an accessibility flag. 8 are partial and 1 is poor on accessibility. "Best route" is the integration that worked most reliably in testing.

| App | Toolkit | Visible by default | Best route | Verdict |
| --- | --- | --- | --- | --- |
| LibreOffice Writer | VCL / GTK 3 | Yes | Accessibility: "Export Directly as PDF" | Good |
| LibreOffice Calc | VCL / GTK 3 | Yes | Accessibility menus, `soffice --convert-to` | Good |
| LibreOffice Impress | VCL / GTK 3 | Yes | Accessibility menus | Good |
| LibreOffice Draw | VCL / GTK 3 | Yes | Accessibility menus | Good |
| Xournal++ | GTK 3 | Yes | Accessibility, or `--create-pdf` | Good |
| Text Editor | GTK 4 | Yes | Window actions by name | Good |
| Files | GTK 4 | Yes | GTK actions over D-Bus, `FileManager1` | Good |
| Calculator | GTK 4 | Yes | Accessibility buttons, `--solve` | Good |
| Clocks | GTK 4 | Yes | Accessibility tabs and buttons | Good |
| Image Viewer | GTK 3 | Yes | GTK actions over D-Bus | Good |
| Document Viewer | GTK 3 | Yes | GTK actions over D-Bus | Good |
| Pinta (flatpak) | GTK 4 | Yes | GTK actions over D-Bus (`rotatecw`, `resize`) | Good |
| VLC | Qt 5 | Yes | MPRIS over D-Bus | Good |
| XDot | GTK 3 | Yes | Accessibility toolbar | Good |
| GNOME Terminal | GTK 3 | Yes | GTK actions over D-Bus | Good |
| Ghostty | GTK 4 | Yes | Window actions by name | Good |
| KiCad (launcher) | wxWidgets / GTK 3 | Yes | `kicad-cli` | Good |
| System Monitor | GTK 4 | Yes | Accessibility tabs, with a denylist | Good |
| VS Code | Electron | No | CLI and command IDs | Good with launch flag |
| Google Chrome | Chromium | No | CLI, accessibility for tabs | Good with launch flag |
| Obsidian | Electron | No | `obsidian://` URIs | Good with launch flag |
| Cursor | Electron | No | CLI | Good with launch flag |
| Characters | GTK 4 (gjs) | Yes, grid missing | Search provider over D-Bus | Partial |
| Disk Usage Analyzer | GTK 4 | Yes, results missing | GTK actions over D-Bus | Partial |
| GTKWave | GTK 3 | Yes | Tcl script at launch | Partial |
| PulseAudio Volume Control | GTK 3 | Yes | `-t N` to open a tab | Partial |
| Sublime Text | Custom, GTK 3 menubar | Menubar only | `sublime_text --command` | Partial |
| STM32CubeIDE | Eclipse SWT | Yes, crashed once | SWT `FileOpen` over D-Bus | Partial |
| Typora | Electron | No | None found | Partial |
| Firefox (snap) | Gecko | No | `firefox --new-tab` | Partial |
| Alacritty | winit | Never | `alacritty msg` socket | Poor |

## Findings by app group

### GNOME and GTK core apps

All eight apps were visible without any enabler, and every walk finished in under 0.25 s. The test agent used an in-memory settings backend and temp XDG dirs, so nothing was written to your settings or recent files.

| App | Toolkit | Nodes / controls with actions | Native route | Test result | Verdict |
| --- | --- | --- | --- | --- | --- |
| Text Editor | GTK 4 | 65 / 13 | 7 app actions, 35 window actions on the accessible frame | Frame action `win.show-preferences` opened Preferences | Good |
| Files | GTK 4 | 228 / 50 | 9 app and 29 window actions, `org.freedesktop.FileManager1` | D-Bus `new-tab` opened a tab. `FileManager1.ShowItems` selected a file | Good |
| Calculator | GTK 4 | 99 / 60 | `--solve` CLI | Pressing 7, ×, 6, = displayed 42. `--solve '7*6+sqrt(16)'` printed 46 | Good |
| Clocks | GTK 4 | 92 / 17 | `add-location`, `stop-alarm` app actions | Stopwatch tab, Start, then the display read 00:00:01.3 | Good |
| Image Viewer | GTK 3 | 119 / 32 | 43 window actions, including `zoom-set` | "Zoom In" took the zoom from 100% to 133%. D-Bus `zoom-set 2.0` gave 200% | Good |
| Document Viewer | GTK 3 | 136 / 56 | About 60 window actions | Side pane toggled. D-Bus `go-last-page` moved from page 1 to 2 | Good |
| Characters | GTK 4 (gjs) | 138 / 28 | Search provider returns characters by name | The character grid is not in the tree. Categories switch only through the Selection interface | Partial |
| Disk Usage Analyzer | GTK 4 | 105 / 23 | 16 window actions, some stateful | "Treemap Chart" tab worked. The results list is not in the tree | Partial |

- **GTK 4 lets Surgeon call actions by name through accessibility.** Each window's accessible frame lists actions such as `win.show-preferences`, `page.zoom-in` and `settings.wrap-text`. This works even when the window exports nothing on D-Bus. Action indexes shift, so resolve them by name each time.
- **Every GTK window carries its D-Bus address.** The X window properties `_GTK_UNIQUE_BUS_NAME`, `_GTK_APPLICATION_OBJECT_PATH` and `_GTK_WINDOW_OBJECT_PATH` are present even for apps with no well-known bus name, such as Calculator.
- **GTK 4 popovers did not open reliably.** One menu opened while the window had focus right after launch, and five attempts failed while it was unfocused. Surgeon should call the underlying action and never depend on opening a GTK 4 menu.
- **Names hide in three places.** Popover menu items have empty names, with the label on the `labelled-by` target. GTK 3 icon buttons carry only a description. Labels carry mnemonic underscores, such as `_Stopwatch`.
- **Results don't always appear as new windows.** Libadwaita dialogs sit inside the main frame, and the shortcuts window is an unnamed `panel`. Surgeon must diff the whole subtree, not only the top-level window list.
- **Disabled actions fail silently.** The Files action `toggle-sidebar` is disabled on wide windows, and activating it does nothing. Surgeon should call D-Bus `Describe` before `Activate`.
- **Destructive actions are exported.** Examples include `move-trash`, `delete`, `row.format`, `row.empty-trash`, `set-wallpaper`, `clear-recent` and `clear-history`.
- **Privacy.** Text Editor exposes the whole document text and its file path. Files exposes folder contents and bookmarks. Calculator exposes its calculation history.

### Office and documents

Calc, Impress, Draw and Xournal++ each completed a real export through accessibility, and the test agent checked every output file. Typora's tree is usable, but its PDF export opened nothing.

| App | Toolkit | Controls with actions | Native route | Test result | Verdict |
| --- | --- | --- | --- | --- | --- |
| LibreOffice Calc | VCL on GTK 3 | 1410 of 1949 nodes | `soffice --convert-to`, UNO scripting | PDF, PNG and CSV exports produced correct files | Good |
| LibreOffice Impress | VCL on GTK 3 | Shares Calc's process | Same as Calc | "Export Directly as PDF" produced a 1-page PDF | Good |
| LibreOffice Draw | VCL on GTK 3 | Shares Calc's process | Same as Calc | Export to PNG gave a 794x1123 image | Good |
| Xournal++ 1.2.2 | GTK 3 | 273 of 493 | `--create-pdf`, `--create-img`, Lua plugins | "Export as PDF" produced the same 6030-byte file as the CLI | Good |
| Typora | Electron 42 | 41 at rest, 75 with a menu open | None found | "Source Code Mode" toggled only with window focus. Export > PDF opened no dialog | Partial |

- **Calc's sheet reports 2,147,483,647 children.** The first unbounded walk hung for over 2 minutes. Every walk needs a cap per node and a total cap.
- **Exports are multi-step.** PNG export needs a format choice in an unnamed combo box, then Export, then an OK in a "PNG Options" dialog. CSV sits under "Save a Copy" and adds an "Export Text File" dialog. Manifests need optional confirm steps for these follow-up dialogs.
- **One LibreOffice process holds every module.** Walking all three windows took 2.36 s. Surgeon should walk one window, picked by WM\_CLASS (`libreoffice-calc`, `libreoffice-impress`) or by the title suffix "LibreOffice Calc". All modules share the app id `org.libreoffice`.
- **The command line can hit the user's open LibreOffice.** Without a separate `-env:UserInstallation` profile, `--convert-to` runs inside the user's running instance silently. With a separate profile it took 0.68 s and left the GUI alone.
- **Electron apps need a launch flag and focus.** Typora showed a full tree only when launched with `--force-renderer-accessibility`, and its menu actions only work while its window has focus. Its item names include shortcut text ("Save Ctrl+S"), which matching must strip.
- **First launch shows blocking dialogs.** Calc shows "Tip of the Day", Impress shows "Select a Template", and Typora shows a license window.
- **Privacy, and a side effect.** "Recent Documents" lists real file names, and the same menu offers "Clear List". LibreOffice's file chooser also added 6 temp export paths to your real `~/.local/share/recently-used.xbel`. Surgeon should launch test apps with a temp `XDG_DATA_HOME`.

### Media and graphics

All five apps were visible and controllable. Pinta and VLC are the strongest demo targets, because each has a native API that the test agent drove and verified.

| App | Toolkit | Controls with actions | Native route | Test result | Verdict |
| --- | --- | --- | --- | --- | --- |
| VLC 3.0.20 | Qt 5.15 | 136 of 245 nodes | MPRIS (`org.mpris.MediaPlayer2.vlc`) | Menu item "Play" changed MPRIS status from Paused to Playing. Seek moved playback from 2 s to 5 s | Good |
| Pinta 3.1.2 (flatpak) | GTK 4 / .NET | 72 of 197 | About 130 GTK actions over D-Bus, including `rotatecw`, `resize`, `undo` | `rotatecw` turned a 200x100 image into 100x200, and `undo` reverted it. The Resize dialog, filled through AT-SPI, gave 100x50 | Good |
| XDot 1.3 | GTK 3 | 13 of 37 | Redraws when the .dot file changes | "Zoom In" changed the render, and "Best Fit" restored it pixel for pixel | Good |
| GTKWave 3.3 | GTK 3 | 32 of 108 | Tcl scripts passed at launch (`-S`) | "Zoom In" was verified only by a screenshot diff, because the tree shows no zoom state | Partial |
| PulseAudio Volume Control 5.0 | GTK 3 | 119 of 329 | `-t N` opens a tab | Switching tabs needed the Selection interface, because tabs have no action. Inspect only | Partial |

- **Unnamed icon buttons are common.** VLC, Pinta and GTKWave toolbar buttons have empty names, and their meaning sits in the description ("Pause the playback", "Zoom In\\nShortcut key: Ctrl++"). Surgeon has to match on the first line of the description too.
- **Hidden duplicates exist.** Every VLC toolbar button appears twice, because the hidden fullscreen controller has its own copy. Match only controls that are showing.
- **AT-SPI identity is unreliable here.** Pinta shows up as `dotnet`, with the PID of the flatpak D-Bus proxy rather than the app. VLC registers two app entries with the same PID. The reliable keys are the `_GTK_APPLICATION_ID` window property, then WM\_CLASS.
- **Some menus can't be opened.** Pinta's and GTKWave's menu buttons don't open their popovers through the AT-SPI click action, so their menu items are unreachable that way. Pinta's GTK actions cover the same commands.
- **Dialogs can appear late.** XDot's "Save As" returned from the action before its modal dialog existed. Surgeon should poll for new windows for at least 3 seconds.
- **Privacy.** VLC's recent media shows full file paths. PulseAudio Volume Control lists hardware device names and other apps' audio streams. File chooser dialogs list bookmarks and folder contents.

### Electron editors and browsers

All four Chromium-based apps work well, but only when launched with `--force-renderer-accessibility`. Without the flag they show just the app and an empty window. Firefox needs `GNOME_ACCESSIBILITY=1` at launch, plus a caller outside T3 Code's AppArmor label.

| App | Default visibility | With the enabler | Native route | Test result | Verdict |
| --- | --- | --- | --- | --- | --- |
| VS Code 1.13 | Window only | 413 to 592 nodes, walk under 0.06 s | CLI `-r -g file:line`, `vscode://`, command IDs in keybindings.json | "Toggle Primary Side Bar (Ctrl+B)" hid and restored the Explorer | Good with the flag |
| Google Chrome | Window only | 228 nodes, 311 with a page open | CLI hands URLs to the running profile | "New Tab" took tabs from 1 to 2, and its "Close" button reverted it. A button on a local web page ran its click handler | Good with the flag |
| Obsidian 1.14.5 | Window only | 105 to 460 nodes | `obsidian://` URIs, a CLI socket | Command palette row "Open graph view" opened the graph. `obsidian://search` filled the search box | Good with the flag |
| Cursor | Window only | 273 nodes | Same CLI as VS Code, `cursor://` | "Toggle Agents (Ctrl+Alt+J)" toggled the panel | Good with the flag |
| Firefox (snap) | Not registered | 612 nodes | `firefox --new-tab URL` | "Open a new tab (Ctrl+T)" took tabs from 1 to 2 | Partial |

- **The flag means a relaunch.** Surgeon can't enable accessibility on an Electron app the user already has open. It would have to restart the app with the flag, or install a wrapper .desktop entry that always adds it. A global screen-reader setting might avoid this, but nobody tested it.
- **The flag has side effects.** VS Code switches into "Screen Reader Optimized" mode when it sees the flag.
- **AppArmor blocks snap apps from Surgeon's process.** Calls from a shell labelled `t3code` to snap Firefox were all denied. A probe started through `systemd-run --user` worked. Surgeon must run from GNOME or its own systemd unit, never inside T3 Code.
- **Inherited environment breaks launches.** VS Code fails with "bad option" when `ELECTRON_RUN_AS_NODE` is set, and T3 Code sets it. Surgeon has to unset it and `CHROME_DESKTOP` before launching apps.
- **Command palettes beat menus, but need typing.** VS Code's palette lists 772 commands, but only about 17 rows exist in the tree, and its entry has no editable-text interface. Command IDs through the CLI or keybindings.json are the better route.
- **Identity.** All four apps report toolkit `Chromium`. Use `/proc/<pid>/exe`, then WM\_CLASS. VS Code's .desktop file says `StartupWMClass=Code`, but the window says `code`.
- **Native message boxes are invisible.** Obsidian's "Vault not found" error dialog never appeared in the tree.
- **Shutting down needs care.** SIGTERM to the whole process group hung the Electron apps. SIGTERM to the main PID alone exited cleanly.
- **Privacy, and profile leaks.** Every app exposes document or page text, and password fields stay hidden. VS Code's Welcome page listed 5 of your real recent folders even with a temp `--user-data-dir`. VS Code and Cursor also wrote to `~/.vscode`, `~/.vscode-shared`, `~/.cursor` and `~/.config/Cursor` despite the temp profile.

### Terminals and other toolkits

Six of seven apps were visible on the accessibility bus. Alacritty has no accessibility support at all, but it has a working IPC socket. STM32CubeIDE crashed during a tree walk.

| App | Toolkit | Controls with actions | Native route | Test result | Verdict |
| --- | --- | --- | --- | --- | --- |
| GNOME Terminal 3.52 | GTK 3 | 45 of 90 | GTK actions over D-Bus (`new-terminal`, `zoom-in`, `find`), `gnome-terminal --tab -- cmd` | Menu item "New Tab" opened a second tab. The D-Bus action `zoom-in` worked, and `zoom-normal` restored the screenshot exactly | Good |
| Ghostty 1.3.1 | GTK 4 | 13 of 59, plus 22 window actions | Window actions such as `win.new-tab` and `win.toggle-command-palette`, keybind config | Window action `win.new-tab` opened a second tab | Good |
| KiCad 9.0.9 | wxWidgets / GTK 3 | 83 of 149 | `kicad-cli` exports schematics and boards. The IPC API is off by default | "About KiCad" opened its dialog. The editors were not tested | Good (launcher only) |
| System Monitor | GTK 4 | 35 of 130 | GTK actions | Tab "Resources" became selected and was reverted | Good, with a denylist |
| Sublime Text 4200 | Custom, GTK 3 menubar | 579 of 871 | `sublime_text --command <cmd>`, `.sublime-keymap` | Menu item "Hide Status Bar" worked, but the label never updated | Partial |
| STM32CubeIDE 2.1.0 | Eclipse SWT / GTK 3 | 228 of 493 | `org.eclipse.swt` D-Bus `FileOpen`, headless build script | "About" opened. A later tree walk crashed the Java process | Partial, crash risk |
| Alacritty 0.13.2 | winit, no toolkit | Not visible | `alacritty msg config` over its IPC socket | `msg config font.size=22` changed the font, and `--reset` restored the screenshot exactly | Poor on accessibility, good native |

- **GTK 4 apps put named actions on the window.** Ghostty's window exposes `win.new-tab`, `win.split-right` and `win.about` as accessibility action names. These are steadier than button labels.
- **Menu labels go stale.** Sublime Text's "Hide Status Bar" never changed to "Show". GNOME Terminal's "100%" zoom label stayed the same after zooming. Surgeon must read checked or selected states, never labels.
- **The process that launches is not always the window's process.** The GNOME Terminal wrapper, the Eclipse launcher and Sublime's `--detached` mode all hand the window to another process. Resolve the real PID from the window.
- **Accessibility walks can crash an app.** STM32CubeIDE segfaulted in GTK's accessibility bridge on a walk right after a dialog closed. Surgeon has to re-fetch from the app root after any window closes, and cap walks by node count.
- **First launch shows blocking windows.** KiCad shows a settings-path prompt and an update check. Sublime shows a safe-mode notice and an update window. KiCad and Eclipse dialogs show up with role `frame` rather than `dialog`.
- **Dangerous controls are reachable.** System Monitor exposes `win.send-signal-kill` and an "End Process" button. A denylist by action id and label is required.
- **Privacy.** GNOME Terminal's tree exposes the full screen text. Ghostty exposes none. KiCad, Sublime and STM32CubeIDE expose recent-file paths.

## Integration strategies ranked

Named actions beat clicking labels. When an app publishes a command by id, that id survives language changes, stale labels and closed menus. Surgeon should try the routes in this order and stop at the first one that covers the request.

| Rank | Route | Worked on | Fails when |
| --- | --- | --- | --- |
| 1 | GTK actions over D-Bus (`org.gtk.Actions.Activate`) | Files, Image Viewer, Document Viewer, Pinta, GNOME Terminal, Disk Usage Analyzer | The action is disabled (it does nothing, silently) or only exists inside a window with no D-Bus path |
| 2 | GTK 4 window actions through accessibility (`win.*`, `page.*` on the frame) | Text Editor, Ghostty, Files | The app uses GTK 3 or another toolkit |
| 3 | Other D-Bus APIs (MPRIS, `FileManager1`, search providers, SWT `FileOpen`) | VLC, Files, Characters, STM32CubeIDE | The app has none. Each API is specific to its kind of app |
| 4 | App command line or URI scheme | LibreOffice, Xournal++, Calculator, KiCad, Sublime Text, VS Code, Cursor, Chrome, Firefox, Obsidian, Alacritty | The command needs a saved file rather than the open document, or reaches into the user's running instance unexpectedly |
| 5 | Accessibility controls by role and name | LibreOffice (including full export flows), Xournal++, Calculator, Clocks, XDot, Chrome tabs, VS Code layout toggles | Labels go stale or carry shortcut text, buttons are unnamed, GTK 4 popovers won't open, or the app needs a launch flag |
| 6 | Screenshot diff as verification only | GTKWave, Sublime Text, Alacritty | It proves something changed, not that the right thing changed |

Config-file edits (keybindings.json, `.sublime-keymap`, Ghostty config, `vlcrc`) were found in every editor and terminal but never tested, because the agents were told not to modify user config. They would be a seventh route, with backup and restore.

## Implications for Surgeon's design

The original plan had one action type (activate a control by role and name). Testing shows the manifest needs about ten step types, a stricter control matcher, and a new app-identity rule.

**Manifest step types.** Every one of these was needed by at least one tested app.

| Step | Why | Example |
| --- | --- | --- |
| `gtk_action {bus, path, name, param}` | Rank 1 route. Call `Describe` first, because disabled actions do nothing | Pinta `rotatecw`, Files `new-tab` |
| `frame_action {name}` | GTK 4 window actions by name, no menu needed | Text Editor `settings.wrap-text` |
| `dbus_call {bus, path, interface, method, args}` from an allowlist | MPRIS and similar APIs | VLC `PlayPause` |
| `cli {argv}` from an allowlist of the app's own binary | Native commands with no shell | `kicad-cli sch export pdf` |
| `open_uri {uri}` | Apps with URI schemes | `obsidian://search` |
| `activate {role, name or description, within}` | Accessibility fallback | Writer "Export Directly as PDF" |
| `select {list, item}` | Tabs and rows with no action, through the Selection interface | Characters categories, PulseAudio Volume Control tabs |
| `set_text`, `set_value` | Filling dialogs | Export filename, Pinta resize width |
| `confirm_if_present {window, button}` | Optional follow-up dialogs | Calc "PNG Options" then OK |
| `wait_for {window or node or state, timeout}` | Modal dialogs appear late | XDot "Save As" |

**Control matching.**

- Match on the name, then the `labelled-by` target's text, then the first line of the description.
- Strip mnemonic underscores and shortcut text ("Save Ctrl+S", "(Ctrl+B)").
- Keep only controls that are showing. VLC and Chrome have hidden duplicates.
- Read checked and selected states, never labels, to know whether a toggle is on.
- Resolve action names on every run, because action indexes shift.

**App identity.** Surgeon can't rely on the accessible app name, the PID it reports, or the .desktop `StartupWMClass`. Pinta reports as `dotnet` with a proxy PID, VLC registers twice, and VS Code's .desktop file has the wrong class. Use this order:

1. The `_GTK_APPLICATION_ID` window property (always equal to the desktop id in testing).
2. The window's PID, then `/proc/<pid>/exe`.
3. WM\_CLASS, plus the title suffix for LibreOffice modules.
4. The flatpak id from `/proc/<pid>/root/.flatpak-info`.

**Walker safety.**

- Cap children per node at about 500 and total nodes at about 20,000. Calc's sheet reports 2,147,483,647 cells.
- Walk only the selected window, not the whole app.
- Re-fetch from the app root after any window closes. Stale references crashed STM32CubeIDE.
- Retry once on a D-Bus timeout. Xournal++ timed out once.

**Safety rules.**

- Deny actions by id and label: `delete`, `move-trash`, `row.format`, `row.empty-trash`, `send-signal-*`, "End Process", "Clear List", `clear-recent`, `clear-history`, `set-wallpaper`, Quit, Exit.
- Drop the subtrees of "Recent Documents", "Open Recent" and file choosers before sending context to the model.
- Never send document text, terminal text or page text by default.

**Process environment.** Surgeon's helper must run from GNOME or its own `systemd-run --user` unit, never inside T3 Code. T3 Code's AppArmor label blocks snap apps. It also leaks `NO_AT_BRIDGE`, `GTK_MODULES` and `ELECTRON_RUN_AS_NODE`.

**Apps Surgeon can't see.** For Electron apps already open without the flag, Surgeon should say "Surgeon needs to restart this app to see inside it" and offer to relaunch it. For Alacritty, it should offer only command-line extensions. For STM32CubeIDE and other Eclipse IDEs, it should warn before inspecting, because a walk crashed one.

## Open issues and untested areas

- [ ] Does turning on the GNOME screen-reader setting make Electron apps expose their trees without a relaunch?
- [ ] Wayland. Every test ran on X11, and the `_GTK_*` window properties and `import -window` are X11 only.
- [ ] Config-file edits as an extension route (keybindings.json, `.sublime-keymap`, Ghostty config), with backup and restore.
- [ ] Whether GTK 4 popovers open when the window has focus. One attempt with focus worked, and five without focus failed.
- [ ] Why Qt apps register on the accessibility bus while `org.a11y.Status IsEnabled` is false.
- [ ] Untested surfaces: KiCad's schematic and board editors, Typora's HTML export, UNO dispatch to a running LibreOffice, Clocks `add-location`, and page text in a text-based PDF.
- [ ] Side effects to clean up on this machine. 6 temp export paths were added to `~/.local/share/recently-used.xbel`. VS Code and Cursor wrote to `~/.vscode`, `~/.vscode-shared`, `~/.cursor` and `~/.config/Cursor`. `~/.local/share/keyrings/login.keyring` was rewritten when Cursor started.
