# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

The UI is HTML and CSS rendered in Electron overlay windows on a Linux desktop (Ubuntu 24.04, GNOME 46, X11). There is no browser page. "web" here means the rendering technology, not the delivery.

## Stack

Electron with TypeScript and plain CSS, no UI framework. The user chose this from three offered options (Electron, Python GTK, Tauri).

- The Electron main process hosts the Codex TypeScript SDK, global shortcuts, cursor tracking and the overlay windows.
- The AT-SPI and D-Bus helper stays a Python process (`/usr/bin/python3` with `gi`) and talks to Codex as an MCP server.
- The helper must run from GNOME or `systemd-run --user`, never inside T3 Code (see docs/app-compatibility.md).

## Users

One person at their own GNOME desktop, using Surgeon all day across many apps. The hackathon demo uses the same UI, with no separate stage mode.

## Product Purpose

Application Surgeon lets a user extend or drive any desktop app by asking in words. Surgeon reads the app through accessibility and D-Bus, Codex writes a short manifest of steps, and Surgeon runs it on the real app. Success is a task done in the app the user is already looking at, without hunting through its menus.

## Positioning

Surgeon acts through each app's own named actions first (GTK actions, D-Bus APIs, the app's CLI) and falls back to pressing controls by name. It does not drive the app with screenshots and synthetic mouse clicks. Every step it runs names its route, and most steps can be undone.

## Operating Context

- Surgeon lives beside the cursor and over whatever app is in front. It never takes over the screen.
- The main controls are a global shortcut, the cursor (Surgeon targets the window and control under it) and typed commands. Voice input comes later: no OPENAI_API_KEY exists on the machine and Codex uses a ChatGPT login.
- Tested app coverage and routes are in docs/app-compatibility.md. Demo flows are in docs/demo-ideas.md.

## Capabilities and Constraints

- Ten manifest step types: `gtk_action`, `frame_action`, `dbus_call`, `cli`, `open_uri`, `activate`, `select`, `set_text`/`set_value`, `confirm_if_present`, `wait_for`.
- Electron apps (VS Code, Chrome, Obsidian, Cursor) are invisible until relaunched with `--force-renderer-accessibility`. Surgeon must say so and offer the relaunch.
- Alacritty has no accessibility tree; only its CLI route works.
- A denylist blocks destructive actions (`delete`, `move-trash`, `send-signal-*`, "End Process", "Clear List", Quit, and others).
- Trees expose document text, terminal text and recent files. Surgeon must not send them to the model by default.
- X11 only so far. Wayland is untested.
- Undecided: the exact default shortcut, voice engine, and whether saved commands sync anywhere.

## Brand Commitments

- Name: Application Surgeon, "Surgeon" in UI copy.
- The user asked for a small interface like HeyClicky (a cursor-side assistant on macOS) and a clean macOS feel. This is binding.

## Evidence on Hand

- docs/app-compatibility.md: 31 apps tested, 22 good targets, with verified routes.
- docs/demo-ideas.md: nine demo flows with verification status.
- No users, testimonials, benchmarks or pricing exist. Do not invent them.

## Product Principles

1. Stay beside the cursor. Surgeon is a small thing that comes and goes, not a window you manage.
2. Show the route. The user should always see whether Surgeon called a named action, ran a command or pressed a control.
3. Ask before anything that can't be undone. Reversible steps run on Enter; irreversible ones need an explicit confirm.
4. Say what Surgeon can't see, and the fix, in one line.
5. Keep private text private by default.

## Accessibility & Inclusion

Demo 1 and demo 2 target low-vision users and people with limited hand movement, so every action must work from the keyboard alone, text must meet WCAG AA contrast over any app, and motion must respect reduced-motion settings.
