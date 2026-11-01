---
name: Application Surgeon
description: A small cursor-side companion that grows into one solid HUD panel when summoned.
colors:
  suture-teal: "light-dark(oklch(0.52 0.105 185), oklch(0.66 0.13 183))"
  suture-teal-ink: "light-dark(oklch(0.47 0.095 186), oklch(0.82 0.11 182))"
  suture-teal-wash: "light-dark(oklch(0.55 0.11 185 / 0.12), oklch(0.66 0.13 183 / 0.18))"
  on-teal: "light-dark(oklch(1 0 0), oklch(0.16 0.02 190))"
  command-violet: "light-dark(oklch(0.52 0.15 295), oklch(0.72 0.13 295))"
  command-violet-wash: "light-dark(oklch(0.52 0.15 295 / 0.1), oklch(0.72 0.13 295 / 0.16))"
  control-wash: "light-dark(oklch(0.2 0.01 250 / 0.06), oklch(1 0 0 / 0.07))"
  caution-amber: "light-dark(oklch(0.6 0.13 65), oklch(0.8 0.14 75))"
  caution-amber-wash: "light-dark(oklch(0.8 0.14 75 / 0.2), oklch(0.8 0.14 75 / 0.14))"
  stop-red: "light-dark(oklch(0.55 0.19 27), oklch(0.7 0.17 25))"
  stop-red-wash: "light-dark(oklch(0.7 0.17 25 / 0.12), oklch(0.7 0.17 25 / 0.16))"
  hud: "light-dark(oklch(0.985 0.002 250 / 0.97), oklch(0.245 0.004 250 / 0.96))"
  hud-raised: "light-dark(oklch(1 0 0), oklch(0.29 0.005 250))"
  hud-sunken: "light-dark(oklch(0.955 0.003 250), oklch(0.21 0.004 250))"
  hud-hover: "light-dark(oklch(0.93 0.004 250), oklch(0.32 0.006 250))"
  hud-line: "light-dark(oklch(0.2 0.01 250 / 0.1), oklch(1 0 0 / 0.08))"
  hud-edge: "light-dark(oklch(0.2 0.01 250 / 0.16), oklch(0 0 0 / 0.6))"
  ink: "light-dark(oklch(0.22 0.008 250), oklch(0.95 0.003 250))"
  ink-2: "light-dark(oklch(0.45 0.01 250), oklch(0.77 0.006 250))"
  ink-3: "light-dark(oklch(0.5 0.01 250), oklch(0.66 0.006 250))"
  key-fill: "light-dark(oklch(1 0 0), oklch(0.34 0.005 250))"
  mark-keyline: "light-dark(oklch(1 0 0 / 0.85), oklch(0.15 0 0 / 0.7))"
typography:
  title:
    fontFamily: "Inter, Ubuntu Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.38
    letterSpacing: "-0.011em"
  input:
    fontFamily: "Inter, Ubuntu Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 450
    lineHeight: 1.2
    letterSpacing: "-0.011em"
  body:
    fontFamily: "Inter, Ubuntu Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.38
    letterSpacing: "-0.006em"
    fontFeature: "\"cv05\", \"cv08\", \"tnum\""
  small:
    fontFamily: "Inter, Ubuntu Sans, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.38
  label:
    fontFamily: "Inter, Ubuntu Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 550
    lineHeight: 1
    letterSpacing: "0"
  route:
    fontFamily: "Ubuntu Sans Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0"
rounded:
  panel: "14px"
  row: "8px"
  chip: "6px"
  key: "5px"
spacing:
  s-1: "2px"
  s-2: "4px"
  s-3: "6px"
  s-4: "8px"
  s-5: "10px"
  s-6: "12px"
  s-7: "16px"
  s-8: "20px"
  s-9: "24px"
components:
  panel:
    backgroundColor: "{colors.hud}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  command-bar:
    backgroundColor: "{colors.hud}"
    textColor: "{colors.ink}"
    typography: "{typography.input}"
    rounded: "{rounded.panel}"
    width: "440px"
    height: "46px"
    padding: "0 10px 0 6px"
  plan:
    backgroundColor: "{colors.hud}"
    rounded: "{rounded.panel}"
    width: "440px"
  tray:
    backgroundColor: "{colors.hud}"
    rounded: "{rounded.panel}"
    width: "320px"
  button:
    backgroundColor: "{colors.hud-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.row}"
    height: "28px"
    padding: "0 8px 0 10px"
  button-hover:
    backgroundColor: "{colors.hud-hover}"
  button-primary:
    backgroundColor: "{colors.suture-teal}"
    textColor: "{colors.on-teal}"
    rounded: "{rounded.row}"
    height: "28px"
    padding: "0 8px 0 10px"
  button-plain:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.row}"
    height: "28px"
    padding: "0 8px 0 10px"
  target-chip:
    backgroundColor: "{colors.hud-sunken}"
    textColor: "{colors.ink}"
    rounded: "{rounded.row}"
    height: "28px"
    padding: "0 8px 0 6px"
  route-action:
    backgroundColor: "{colors.suture-teal-wash}"
    textColor: "{colors.suture-teal-ink}"
    typography: "{typography.route}"
    rounded: "{rounded.chip}"
    height: "20px"
    padding: "0 7px 0 6px"
  route-command:
    backgroundColor: "{colors.command-violet-wash}"
    textColor: "{colors.command-violet}"
    typography: "{typography.route}"
    rounded: "{rounded.chip}"
    height: "20px"
    padding: "0 7px 0 6px"
  route-control:
    backgroundColor: "{colors.control-wash}"
    textColor: "{colors.ink-2}"
    typography: "{typography.route}"
    rounded: "{rounded.chip}"
    height: "20px"
    padding: "0 7px 0 6px"
  list-row:
    rounded: "{rounded.row}"
    height: "32px"
    padding: "0 8px"
  list-row-hover:
    backgroundColor: "{colors.hud-hover}"
  list-row-selected:
    backgroundColor: "{colors.suture-teal-wash}"
  keycap:
    backgroundColor: "{colors.key-fill}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.key}"
    height: "18px"
    padding: "0 5px"
  tag-warn:
    backgroundColor: "{colors.caution-amber-wash}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    height: "18px"
    padding: "0 6px"
  toast:
    backgroundColor: "{colors.hud}"
    textColor: "{colors.ink}"
    rounded: "18px"
    height: "36px"
    padding: "0 8px 0 10px"
---

# Design System: Application Surgeon

## Overview

**Creative North Star: "The suture beside the cursor"**

Surgeon is an 18px companion that sits next to the pointer and grows into one small panel only when the user summons it. Every surface is a macOS-style HUD drawn honestly for GNOME on X11. Linux gives an Electron overlay no window blur, so panels are solid and near-opaque (97% light, 96% dark) instead of fake glass. They have a 0.5px hairline edge, a two-layer soft shadow and 14px corners. The system refuses the chat sidebar and the centered Spotlight bar. Panels open below and to the right of the cursor and grow from the corner nearest it.

The palette is neutral graphite and paper that follows the GNOME colour scheme through CSS `light-dark()`. A `data-theme` attribute pins one scheme. There is one accent, suture teal. GNOME draws focus and selection in blue (#3584e4), so teal keeps Surgeon's marks from ever reading as the app's own. Two more hues carry meaning and nothing else. Violet marks a step that runs the app's command line or a URI. Amber and red mark caution and failure.

Density is desktop-native. Body text is 13px Inter, rows are 32 to 36px tall, and spacing steps by 2px and 4px. The interaction model, keys and stack are in [docs/interface.md](docs/interface.md). This file covers only the visual system.

**Key Characteristics:**
- Solid near-opaque HUD panels with a 0.5px edge, an inset sheen and a two-layer shadow.
- One accent (suture teal) for focus, selection, primary action, progress and the mark.
- Route chips in a monospace face, coloured by how Surgeon acts.
- The mark, a set of teal corner brackets at a control's real accessibility extents.
- Every colour token is a light and dark pair that follows the system scheme.

## Colors

The neutrals are cool graphite at hue 250 with almost no chroma, and the hues each carry one meaning.

### Primary
- **Suture teal** is the only accent. It fills the primary button, the checked switch, completed step dots, the running step's arc, the focus ring, the text caret and the status dot. The mark and the companion use the same pair through `--mark`.
- **Suture teal ink** is the darker (light theme) or lighter (dark theme) teal for text and icons on a teal wash. It colours action route chips and the icon of a selected row.
- **Suture teal wash** is the 12 to 18% teal fill behind a selected row, an action route chip and selected text.
- **On teal** is the ink on a solid teal fill: white in light theme, near-black teal in dark theme.

### Secondary
- **Command violet** and its wash colour the route chip for steps that run the app's CLI or open a URI. Violet appears nowhere else.

### Tertiary
- **Caution amber** and its wash mark steps that can't be undone, warning notices, the companion's error state and a degraded tray status.
- **Stop red** and its wash mark failed steps and blocking notices.

### Neutral
- **HUD** is the panel ground. **HUD raised** is the face of a default button. **HUD sunken** is the ground for the target chip, the running step and the plan footer. **HUD hover** is the hover fill for rows and buttons.
- **HUD line** divides sections inside a panel. **HUD edge** is the panel's outer hairline and the outline of buttons, step dots and the switch track.
- **Ink** is primary text, **ink 2** is secondary text and done steps, and **ink 3** is placeholders, hints, notes and list headings.
- **Control wash** is the graphite fill behind a control route chip, the info notice icon and the unchecked switch track.
- **Key fill** is the keycap face. **Mark keyline** is the opposite-tone halo around anything drawn over app pixels.

### Named Rules

**The Never Blue Rule.** Surgeon's own marks, selection and focus never use blue. GNOME and its apps already draw focus in #3584e4, and Surgeon must stay distinguishable from the app it is operating.

**The Route Colour Rule.** Teal means a named action (`gtk_action`, `frame_action`, `dbus_call`), violet means the app's command line or URI, and graphite means pressing a control by name. Don't use these hues for anything else on a surface that shows routes.

**The Paired Token Rule.** Every theme colour is a `light-dark()` pair. Don't add a colour that has only one value.

## Typography

Inter (variable, bundled at weights 100 to 900) carries every piece of UI text, with Ubuntu Sans and system-ui as fallbacks. Ubuntu Sans Mono appears only inside route chips, where it sets the literal step type and target name. Body text turns on Inter's `cv05` and `cv08` alternates and tabular numerals.

### Hierarchy
- **Title** (600, 15px, -0.011em) is the request at the top of a plan. It wraps with `text-wrap: balance`.
- **Input** (450, 15px, line-height 1.2, -0.011em) is the command bar's text field. Long input ends in an ellipsis on one line.
- **Body** (400, 13px, line-height 1.38, -0.006em) is step text, row labels, notice text and toasts. Buttons use body size at 550. Chip and tray names use 550 and 650.
- **Small** (12px) is hints, step notes, setting descriptions, empty states and the bar's status text.
- **Label** (550, 11px, no tracking) is list headings in sentence case, tags and keycaps (keycaps at 500).
- **Route** (Ubuntu Sans Mono 500, 11px) is the route chip text only.

### Named Rules

**The One Family Rule.** Inter sets everything a person reads. Monospace is reserved for route chips, because a route is a literal identifier.

**The Weight Step Rule.** Hierarchy comes from Inter's variable weights (400, 450, 550, 600, 650) and two sizes (13px and 15px), not from large size jumps or uppercase.

## Layout

Surgeon has no page grid. Each surface is a fixed-width overlay placed relative to the cursor. The command bar, plan and notice are 440px wide. The tray popover is 320px wide. The bar row is 46px tall. List rows are at least 32px, plan steps 34px, settings 36px, and buttons and the target chip 28px.

Panels open below and to the right of the cursor and scale in from the corner nearest it. The companion sits at the cursor plus 14px across and 16px down.

Spacing uses a 2px and 4px ramp from 2px to 24px. Panel headers pad 12px, list containers pad 4px, rows pad 8px on the sides, and the plan footer pads 10px by 12px on a sunken ground. Plan steps sit on a three-column grid: a 20px state dot, the text, and the route chip right-aligned. The plan footer wraps when the hint and buttons don't fit, and the primary button stays right-aligned.

## Elevation & Depth

Panels are lifted, and the shadow is ambient. Every HUD carries the same four-layer shadow. A 0.5px inset sheen runs along the top edge, a 0.5px inset rim shows in dark theme only, a near shadow (0 2px 6px) sits under that, and a far shadow (0 14px 38px) spreads below. The shadow colours are paired tokens, so dark theme shadows are deeper. Inside a panel, depth is tonal. Sunken grounds mark the target chip, the running step and the footer. Raised grounds with a 0.5px drop mark default buttons.

### Shadow Vocabulary
- **HUD shadow** (`0 0.5px 0 0 var(--hud-sheen) inset, 0 0 0 0.5px var(--hud-rim) inset, 0 2px 6px -1px var(--shadow-near), 0 14px 38px -10px var(--shadow-far)`) goes on every panel and the toast.
- **Button lift** (`0 0.5px 1px var(--shadow-near)`) goes on default buttons only.
- **Mark label shadow** (`0 2px 8px -2px var(--shadow-far)`) goes on the small label above a mark.
- **Companion drop** (`drop-shadow(0 1px 1.5px oklch(0 0 0 / 0.35))`) goes on the companion's SVG.

### Named Rules

**The Honest Material Rule.** Panels are solid. Don't use `backdrop-filter`, translucent glass, or a background below 96% opacity. The 2px blur in the panel entry animation is motion, not material, and is allowed.

**The Keyline Rule.** Anything Surgeon draws over app pixels (the mark and the companion) carries a keyline in the opposite tone so it reads on light and dark apps alike.

## Shapes

Corners nest by size. Panels are 14px, rows, buttons, the target chip and the notice icon are 8px, chips, tags and mark labels are 6px, and keycaps are 5px. The toast and the switch are full pills, with the radius set to half their height (18px and 9px). Step dots and the status dot are circles. Edges are 0.5px hairlines everywhere. Keycaps thicken their bottom edge to 1.5px. Icons are 16px stroked SVG at 1.75 stroke width with round caps and joins.

The mark is the one bracket form. It draws four corner brackets with 8px arms and 2px strokes, 5px outside the control's accessibility box, around a 45% teal outline at 5px radius. When the mark brackets a whole window, the arms grow to 18px, the radius to 10px, and the outline goes away.

## Components

### Buttons
Buttons are quiet and compact, and each one shows its key. They are 28px tall with 8px corners, 550 weight body text and a keycap after the label. The default button is a raised face with a 0.5px edge and a hairline lift. It fills with HUD hover on hover and scales to 98% when pressed, over 120ms. The primary button is solid suture teal with on-teal text. Its hover mixes 12% ink into the teal, and its keycap inverts to an on-teal face with teal-ink text. The plain button has no fill, edge or shadow and uses ink 2. A busy button hides its label behind a 14px spinning ring. Disabled buttons drop to 45% opacity.

### Chips
Route chips are 20px tall with 6px corners and set their text in the route face. A 6px square dot leads each one. Action and command chips use a filled dot in their own colour. The control chip's dot is a 1.25px outline square, so the route still reads without colour. The target chip names the aimed app on a sunken 28px chip, with the document name in ink 3. Tags are 18px tall with 6px corners and 11px 550 text on a caution or stop wash.

### Cards / Containers
Every container is a HUD panel. It has the HUD ground, 14px corners, a 0.5px HUD edge, the HUD shadow and clipped overflow. Sections inside a panel are separated by a 0.5px HUD line. Panels enter over 180ms with ease-out-quint, from 96% scale, 2px up and a 2px blur, and grow from the corner nearest the cursor.

### Inputs / Fields
The command bar's field has no box. It sits inside the bar row after the target chip, in 15px 450 Inter, with a teal caret and an ink 3 placeholder. Focus shows the teal caret, not an outline. Other focusable elements get a 2px teal outline at 2px offset. The switch is a real checkbox with `role="switch"`. Its track is 30 by 18px on control wash and turns teal when checked, and the white 14px knob slides 12px over 180ms.

### Navigation
Lists are the navigation. Rows are 32px tall with 8px corners, a 16px icon in ink 3 and an ellipsised label. Hover fills them with HUD hover. The selected row (`aria-selected`) takes the teal wash, and its icon turns teal ink. List headings are 11px 550 sentence-case text in ink 3.

### The plan
The plan is the core panel. A 15px title states the request beside the app icon. Each step has an 18px state dot. Pending dots show the step number inside a hairline circle. A running step sits on a sunken row, and its dot becomes a 30% teal arc spinning every 900ms. Done dots are solid teal with a check, and the step text goes to ink 2. Failed dots are solid red with a mark, and the step note turns red. The footer carries a hint in small text and the buttons with their keycaps.

### The mark and the companion
The mark is Surgeon's signature. Teal corner brackets land at a control's real accessibility extents and scale in from 125% over 260ms. A small HUD label above shows the route chip for the step. The companion is an 18px teal pointer with an opposite-tone keyline. It glides to the mark over 460ms before Surgeon acts. When idle it rests at 55% opacity and 60% scale. While thinking it spins a dashed ring, when done it shows a check, and on error it turns amber with an exclamation mark.

### Toast and notices
The toast is a 36px pill HUD with a teal check, one line of result and an undo keycap set after a hairline divider. Notices are 440px panels that state what Surgeon can't do and the fix. Each one has a 28px icon tile on a caution, stop or control wash, a 600-weight title, ink 2 text and right-aligned buttons.

## Do's and Don'ts

### Do:
- **Do** put every new surface on the HUD panel material: HUD ground, 0.5px HUD edge, 14px corners and the HUD shadow.
- **Do** show the route chip on every step, coloured by its route family.
- **Do** give every button and toast action its keycap, so the whole flow works from the keyboard.
- **Do** keep hover, press, toggle and panel entry at 120ms or 180ms, and use ease-out-quint (`cubic-bezier(0.22, 1, 0.36, 1)`) for arrivals. Only the mark (260ms) and the companion glide (460ms) run longer.
- **Do** give anything drawn over app pixels the mark keyline.
- **Do** honour reduced motion. Animations collapse to 1ms and the companion stops gliding.

### Don't:
- **Don't** use blue for Surgeon's focus, selection or marks.
- **Don't** use `backdrop-filter` or translucent glass for panels.
- **Don't** use violet, amber or red outside their route and status meanings.
- **Don't** set UI text in the monospace face outside route chips.
- **Don't** add a colour token without both light and dark values.
- **Don't** centre a panel on screen or dock it as a sidebar. Panels open beside the cursor.
