// Electron main: global shortcuts, the panel window, the helper process and Codex jobs.
import { app, BrowserWindow, globalShortcut, ipcMain, screen } from "electron";
import { execFile } from "node:child_process";
import path from "node:path";
import { Helper, REPO } from "./helper.js";
import { runJob } from "./job.js";

const PANEL_W = 480;
let panel: BrowserWindow;
let toolbar: BrowserWindow;
let toolbarAt: { x: number; y: number; width: number; height: number } | null = null;
const triggers = new Map<string, string>(); // armed sub-app id -> trigger type
let helper: Helper;
let target: any = null; // last `target` reply from the helper
let job: AbortController | null = null;
let lastRun: { xid: string; manifest: any } | null = null;

function send(channel: string, payload?: unknown) {
  if (!panel.isDestroyed()) panel.webContents.send(channel, payload);
}

function placeNear(x: number, y: number, w: number, h: number) {
  const { workArea } = screen.getDisplayNearestPoint({ x, y });
  let left = x + 14, top = y + 18;
  if (left + w > workArea.x + workArea.width) left = x - w - 14; // flip left at the screen edge
  if (top + h > workArea.y + workArea.height) top = y - h - 18;   // flip up
  return { x: Math.max(workArea.x, left), y: Math.max(workArea.y, top) };
}

async function summon() {
  if (panel.isVisible()) return hide();
  try {
    target = await helper.call("target"); // reads _NET_ACTIVE_WINDOW before the panel takes focus
  } catch (e: any) {
    target = null;
    send("notice", { tone: "info", title: "Surgeon can't see a window", text: e.message });
  }
  const cursor = screen.getCursorScreenPoint();
  const [w, h] = panel.getSize();
  const pos = placeNear(cursor.x, cursor.y, w, h);
  panel.setPosition(pos.x, pos.y);
  if (target) send("target", target);
  if (target) loadTools(target.ident.xid);
  panel.show();
  panel.focus();
}

// Walking the app's controls can take a moment, so the panel shows first and the list fills in after.
function loadTools(xid: string) {
  helper.call("tools", { xid }).then((tools) => send("tools", { xid, tools }), () => {});
}

// Sub-app hotkeys are global shortcuts, so they're registered only while their app's window is active.
let subappKeys: string[] = [];

function registerKey(accelerator: string, fn: () => void) {
  if (globalShortcut.register(accelerator, fn)) subappKeys.push(accelerator);
  else console.error(`${accelerator} is taken`);
}

function placeToolbar() {
  if (!toolbarAt) return;
  const [w, h] = toolbar.getSize();
  // Inside the app window's top-right corner, under a typical GNOME header bar.
  toolbar.setBounds({ x: Math.max(0, toolbarAt.x + toolbarAt.width - w - 8), y: toolbarAt.y + 52, width: w, height: h });
}

function onPush(ev: any) {
  if (ev.type === "subapp.armed") triggers.set(ev.id, ev.trigger);
  if (ev.type === "subapp.focus") {
    for (const key of subappKeys) globalShortcut.unregister(key);
    subappKeys = [];
    for (const { id, accelerator } of ev.active) {
      registerKey(accelerator, () => { helper.call("subapp_trigger", { sub_id: id, xid: ev.xid }).catch(() => {}); });
    }
    toolbarAt = ev.toolbars.length ? ev.at : null;
    if (!toolbarAt) return toolbar.hide();
    toolbar.webContents.send("toolbars", { xid: ev.xid, toolbars: ev.toolbars });
    for (const tb of ev.toolbars) {
      if (tb.accelerator) registerKey(tb.accelerator, () => { toolbar.focus(); toolbar.webContents.send("toolbar_focus"); });
    }
    placeToolbar();
    toolbar.showInactive();
  } else if (ev.type === "subapp.done" && triggers.get(ev.id) === "file_saved") {
    const cursor = screen.getCursorScreenPoint();
    const [w, h] = panel.getSize();
    const pos = placeNear(cursor.x, cursor.y, w, h);
    panel.setPosition(pos.x, pos.y);
    send("subtoast", ev);
    panel.showInactive();
  } else if (ev.type === "subapp.panel") {
    // Top-right corner of the app window, inside it, so the panel reads as belonging to that app.
    const at = ev.at ?? { ...screen.getCursorScreenPoint(), width: 0, height: 0 };
    panel.setPosition(Math.max(0, at.x + at.width - PANEL_W - 8), at.y + 48);
    send("subpanel", ev);
    panel.show();
    panel.focus();
  } else if (ev.type === "subapp.failed" || ev.type === "subapp.disabled") {
    const cursor = screen.getCursorScreenPoint();
    const [w, h] = panel.getSize();
    const pos = placeNear(cursor.x, cursor.y, w, h);
    panel.setPosition(pos.x, pos.y);
    send("subnotice", ev);
    panel.showInactive();
  }
}

function hide() {
  panel.hide();
  // GNOME would focus the topmost window, which can be Surgeon's toolbar. Hand focus to the app.
  if (target?.ident?.xid) execFile("wmctrl", ["-i", "-a", target.ident.xid], () => {});
}

app.whenReady().then(() => {
  helper = new Helper();
  helper.onPush = onPush;
  panel = new BrowserWindow({
    width: PANEL_W, height: 120, show: false, frame: false, transparent: true, resizable: false,
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false, backgroundColor: "#00000000",
    webPreferences: { nodeIntegration: true, contextIsolation: false }, // local file only, no remote content
  });
  panel.setAlwaysOnTop(true, "pop-up-menu");
  panel.loadFile(path.join(REPO, "app/panel.html"));
  toolbar = new BrowserWindow({
    width: 320, height: 60, show: false, frame: false, transparent: true, resizable: false,
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false, backgroundColor: "#00000000",
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  toolbar.setAlwaysOnTop(true, "pop-up-menu");
  toolbar.loadFile(path.join(REPO, "app/toolbar.html"));
  ipcMain.on("toolbar_size", (_e, { w, h }: { w: number; h: number }) => {
    toolbar.setSize(Math.ceil(w), Math.ceil(h));
    placeToolbar();
  });
  ipcMain.on("toolbar_click", (_e, args: { sub_id: string; xid: string; button: number }) => {
    execFile("wmctrl", ["-i", "-a", args.xid], () => {}); // the click focused the toolbar; give focus back
    helper.call("subapp_trigger", args).catch(() => {});
  });
  ipcMain.on("toolbar_blur", () => {
    toolbar.hide(); // GNOME returns focus to the app underneath
    toolbar.showInactive();
  });

  if (!globalShortcut.register("Control+Alt+Space", summon)) console.error("Ctrl+Alt+Space is taken by another app");
  globalShortcut.register("Control+Alt+Z", async () => {
    if (!lastRun?.manifest.undo?.length) return;
    try { await helper.call("undo", lastRun); } catch { /* window may be gone */ }
  });

  ipcMain.on("size", (_e, h: number) => {
    const [x, y] = panel.getPosition();
    const { workArea } = screen.getDisplayNearestPoint({ x, y });
    const height = Math.min(Math.ceil(h), workArea.height - 40);
    panel.setBounds({ x, y: Math.min(y, workArea.y + workArea.height - height), width: PANEL_W, height });
  });
  ipcMain.on("hide", hide);

  ipcMain.handle("ask", async (_e, request: string) => {
    job?.abort();
    job = new AbortController();
    const result = await runJob({
      xid: target.ident.xid, app: target.app, title: target.ident.title, request, helper,
      onStatus: (s) => send("status", s), signal: job.signal,
    });
    job = null;
    return result;
  });

  ipcMain.on("stop", () => {
    job?.abort();
    helper.call("stop").catch(() => {});
  });

  ipcMain.handle("run", async (_e, manifest: any) => {
    lastRun = { xid: target.ident.xid, manifest };
    return helper.call("run", lastRun, (ev) => send("step", ev));
  });

  ipcMain.handle("relaunch", async () => {
    const r = await helper.call("relaunch", { xid: target.ident.xid });
    if (r.ok && r.xid) {
      target = await helper.call("target", { xid: r.xid });
      send("target", target);
      loadTools(r.xid);
      panel.show();
      panel.focus(); // the restarted app took focus when its window opened
    }
    return r;
  });

  ipcMain.handle("install", (_e, args: { manifest: any; name: string; request: string }) =>
    helper.call("install", { xid: target.ident.xid, ...args }));

  ipcMain.handle("subapp_install", (_e, args: { job: string; manifest: any; request: string }) =>
    helper.call("subapp_install", { xid: target.ident.xid, ...args }));
  ipcMain.handle("subapp_enable", (_e, args: { sub_id: string; enabled: boolean }) => helper.call("subapp_enable", args));
  ipcMain.handle("subapp_remove", (_e, sub_id: string) => helper.call("subapp_remove", { sub_id }));
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  helper?.close();
});
app.on("window-all-closed", () => { /* keep running in the background */ });
