---
version: 1
slug: "ui-specimen-html"
primary_target: "ui/specimen.html"
related_targets: ["ui/tokens.css","ui/surgeon.css"]
---

# Surgeon overlay UI

Scope: every overlay surface Surgeon draws over the desktop (companion, command bar, plan, mark, toast, notices, tray popover). Mode: Operate. Specimen: ui/specimen.html. Direction is brief-pinned (small cursor-side companion like HeyClicky, clean macOS feel), so no concept roll ran.

Audience and job: one person at their GNOME desktop all day, asking Surgeon to do something in the app under the cursor. Constraints: X11, no window blur on Linux, overlays sit over arbitrary app content in light or dark themes, keyboard-only must work.

## Direction contract

THESIS: Surgeon is an 18px companion beside the cursor that grows into one small panel only when summoned, and shrinks back when done. It refuses the chat sidebar and the centered Spotlight bar.

OWN-WORLD: macOS HUD material rendered honestly: solid near-opaque panels (no fake glass), 0.5px hairline, soft two-layer shadow, 14px panel radius, Inter at 13px. Neutral graphite and paper follow the system theme. One accent, suture teal, chosen because GNOME's own focus and selection colour is blue and Surgeon's marks must never read as the app's. Route chips colour-code how Surgeon acts: teal named action, violet command, graphite control press.

STORY: The user taps Ctrl+Alt+Space, sees which app Surgeon is aimed at, types, reads a plan with routes, presses Enter, watches the companion move to the real control, and gets one line with an undo.

FIRST VIEWPORT: The specimen opens on a mock Pinta window mid-run: the plan panel below-right of the cursor with step 2 running, a mark bracketing the Resize button with its route label, and the companion parked at the mark's corner. The replay shows the command bar step before it. Surface states follow below in light and dark.

FORM: Pinned brief (macOS HUD companion), position 1 of 1, seed key: none (brief-pinned, no roll). Signature move: the mark, a teal corner-bracket outline drawn at the control's real accessibility extents, with a route chip, which the companion glides to before acting.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
