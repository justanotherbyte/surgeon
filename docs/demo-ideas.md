# Application Surgeon: demo ideas

Nov 1, 2026

## Summary

These are nine demos, each built only on apps and routes that passed in [app-compatibility.md](app-compatibility.md). Each one solves a task people already do by hand. Three cover accessibility, three cover workflow speed and three cover teaching.

For a five-minute demo, run these three in order:

1. **"Make it bigger" in any app** (accessibility). One sentence works in four apps through three different kinds of route, including Alacritty, which has no accessibility tree.
2. **Calc report in three formats** (workflow). A dialog chain of about ten clicks becomes one command, and Files then reveals the output.
3. **Calculator tutor** (education). Surgeon presses the real buttons slowly while the student watches, so the audience sees it act on the real app UI.

## How to read each idea

Each idea lists who it helps, what the user asks for, the manifest steps Surgeon would generate, and how much testing has already proved. The step names come from the step types in the compatibility doc.

| Status | Meaning |
| --- | --- |
| Verified | The exact action ran in testing and the test agent checked its result |
| Route verified | The route works on that app, but this exact sequence has not run |
| Untested | Nobody has tried it |

## Accessibility

### 1. "Make it bigger" in any app

**Who it helps.** Low-vision users, and anyone presenting on a projector.

**The ask.** "Make this bigger", said while any supported app is in front.

| App | Step | Status |
| --- | --- | --- |
| Image Viewer | `gtk_action zoom-set 2.0` | Verified, 100% to 200% |
| GNOME Terminal | `gtk_action zoom-in`, undone by `zoom-normal` | Verified, the screenshot restored exactly |
| Alacritty | `cli alacritty msg config font.size=22`, undone by `--reset` | Verified, the screenshot restored exactly |
| Text Editor | `frame_action page.zoom-in` | Route verified, the action is listed but was not run |

The request stays the same while the route changes per app, which shows the route ranking working. Alacritty is the strongest moment, because no accessibility tool can see it at all.

### 2. Hands-free VLC

**Who it helps.** People with limited hand movement, and students taking notes during a recorded lecture.

**The ask.** "Pause", "play", "go back 10 seconds".

**Steps.** `dbus_call` to MPRIS on `org.mpris.MediaPlayer2.vlc`: `PlayPause`, and `Seek` with an offset of -10,000,000 microseconds.

**Status.** Verified. Play changed MPRIS status from Paused to Playing, and a seek moved playback from 2 s to 5 s.

**Blocker.** The machine has no `OPENAI_API_KEY`, and Codex uses a ChatGPT login, so voice input needs its own key or a local speech model. Without one, run this demo with typed commands or a global shortcut.

### 3. Make Electron apps readable by a screen reader

**Who it helps.** Orca users. VS Code, Obsidian, Chrome and Cursor show an empty window to accessibility tools unless they start with `--force-renderer-accessibility`.

**The ask.** "Make Obsidian work with my screen reader."

**Steps.** Surgeon installs a wrapper .desktop entry that always adds the flag, then relaunches the app. The relaunch sends SIGTERM to the main PID only, because signalling the whole process group hung Electron apps in testing.

**Status.** Route verified. With the flag, Obsidian exposed 105 to 460 nodes and VS Code switched into its "Screen Reader Optimized" mode. Nobody tested Orca reading the result.

The same relaunch is what Surgeon needs to extend these apps at all, so this demo also explains a required step instead of hiding it.

## Speeding up workflows

### 4. Calc report in three formats

**Who it helps.** Anyone who sends the same spreadsheet out every week.

**The ask.** "Export this sheet as PDF, PNG and CSV, then show me the files."

**Steps.**

1. `activate` "Export Directly as PDF".
2. `activate` Export, `select` PNG in the unnamed format combo box, `activate` Export, then `confirm_if_present` the "PNG Options" dialog.
3. `activate` "Save a Copy", `select` CSV, then `confirm_if_present` the "Export Text File" dialog.
4. `dbus_call org.freedesktop.FileManager1.ShowItems` on the output files.

**Status.** Verified. All three exports produced correct files, and `ShowItems` selected a file in Files.

**Watch for.** The format combo box has no name, so the matcher has to find it by role and position. For a saved file, `soffice --convert-to` with its own `-env:UserInstallation` profile does the same in 0.68 s. Without that separate profile, the command runs inside the user's open LibreOffice.

### 5. Photo thumbnail in Pinta

**Who it helps.** Anyone preparing images for a form, a slide or a listing.

**The ask.** "Rotate this photo and shrink it to 100 pixels wide."

**Steps.** `gtk_action rotatecw`, then `gtk_action resize` to open the dialog, `set_value` on the width field, and `confirm_if_present` OK. `gtk_action undo` reverts each step.

**Status.** Verified. `rotatecw` turned a 200x100 image into 100x200, `undo` reverted it, and the Resize dialog filled through AT-SPI gave 100x50.

**Watch for.** Pinta is a flatpak and reports itself as `dotnet` with a proxy PID. Identify it by `_GTK_APPLICATION_ID`.

### 6. Coding workspace in one command

**Who it helps.** Developers who rebuild the same window layout every morning.

**The ask.** "Open the failing test at line 42, hide the sidebar, and give me a terminal running the test watcher."

**Steps.**

1. `cli code -r -g tests/test_export.py:42`.
2. `activate` "Toggle Primary Side Bar (Ctrl+B)", which needs VS Code launched with the accessibility flag.
3. `cli gnome-terminal --tab -- <watch command>`, or `frame_action win.split-right` in Ghostty.

**Status.** Route verified. The sidebar toggle and terminal tabs passed on their own, but the combined sequence has not run.

**Watch for.** Surgeon must unset `ELECTRON_RUN_AS_NODE` and `CHROME_DESKTOP` before launching VS Code, or it fails with "bad option".

## Education

### 7. Calculator tutor

**Who it helps.** Children learning arithmetic, and adults learning a new app.

**The ask.** "Show me how to work out 7 × 6 on the calculator."

**Steps.** `activate` the buttons 7, ×, 6 and = with a pause between each, then read the display. `gnome-calculator --solve '7*6'` checks the answer.

**Status.** Verified. Pressing 7, ×, 6, = displayed 42, and `--solve '7*6+sqrt(16)'` printed 46.

The same pattern teaches any app by doing the steps slowly on the real UI, for example "show me how to export a PDF in Writer". The student sees where each control is, which a written answer can't show.

### 8. Graph algorithm lessons in XDot

**Who it helps.** Computer science teachers explaining searches and shortest paths.

**The ask.** "Step through breadth-first search on this graph, one node per click."

**Steps.** Codex writes a small script that rewrites the .dot file at each step and colors the visited nodes. XDot redraws when the file changes. Surgeon then runs `activate` "Best Fit" to frame the graph.

**Status.** Route verified. XDot redraws on file change, and "Zoom In" and "Best Fit" passed. The stepping script is new code.

### 9. Lecture handout pipeline

**Who it helps.** Teachers who annotate slides and notes, then share them as PDFs.

**The ask.** "Turn today's slides and my handwritten notes into PDFs in one folder."

**Steps.** `activate` "Export Directly as PDF" in Impress, `cli xournalpp --create-pdf` for the notes, then `dbus_call FileManager1.ShowItems` on the folder.

**Status.** Verified for each step. Impress produced a 1-page PDF, and Xournal++'s CLI and its "Export as PDF" menu produced the same 6030-byte file.

**Watch for.** Impress shows a "Select a Template" dialog on first launch. Close it before the demo starts.

## Ideas to avoid on stage

| Idea | Why it fails |
| --- | --- |
| Typora export | Export > PDF opened no dialog in testing |
| Anything in snap Firefox | AppArmor denies Surgeon's calls unless it runs outside T3 Code, and Firefox needs `GNOME_ACCESSIBILITY=1` at launch |
| STM32CubeIDE | A tree walk crashed the Java process |
| Anything that opens a GTK 4 menu | Popovers opened once with focus and failed five times without it. Call the action by name instead |
| Character picking from Characters' grid | The grid is not in the tree. The search provider works |
| Disk Usage Analyzer results | The results list is not in the tree |
| System Monitor process actions | `send-signal-kill` and "End Process" are on the denylist |
| An Electron app the audience saw open without the flag | Surgeon can't see inside it until it relaunches |

## Demo prep checklist

- [ ] Run Surgeon's helper from GNOME or `systemd-run --user`, never from inside T3 Code.
- [ ] Launch VS Code, Obsidian and Chrome with `--force-renderer-accessibility`, with `ELECTRON_RUN_AS_NODE` and `CHROME_DESKTOP` unset.
- [ ] Dismiss first-launch dialogs ahead of time: Calc's "Tip of the Day", Impress's "Select a Template", KiCad's settings prompt.
- [ ] Launch demo apps with a temp `XDG_DATA_HOME` and LibreOffice with its own `-env:UserInstallation`, so exports stay out of the real recent-files list.
- [ ] Use demo files only. Recent-file menus, terminal text and document text all show up in trees and on the projector.
- [ ] Focus Electron windows before menu actions. Typora and other Electron menus only fire with window focus.
- [ ] Get an API key or a local speech model if demo 2 uses voice.

## Open questions

- [ ] Does demo 2 get real voice input, or typed commands?
- [ ] Is the XDot stepping script in demo 8 worth building, or does a pre-made series of .dot files do the job?
- [ ] Does Orca read Obsidian well with the flag on? Demo 3 depends on it.
