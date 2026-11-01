// Electron main: global shortcuts, the panel window, the helper process and Codex jobs.
import { app, BrowserWindow, globalShortcut, ipcMain, screen } from "electron";
import path from "node:path";
import { Helper, REPO } from "./helper.js";
import { runJob } from "./job.js";

const PANEL_W = 480;
let panel: BrowserWindow;
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
  panel.show();
  panel.focus();
}

function hide() {
  panel.hide(); // GNOME hands focus back to the window underneath
}

app.whenReady().then(() => {
  helper = new Helper();
  panel = new BrowserWindow({
    width: PANEL_W, height: 120, show: false, frame: false, transparent: true, resizable: false,
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false, backgroundColor: "#00000000",
    webPreferences: { nodeIntegration: true, contextIsolation: false }, // local file only, no remote content
  });
  panel.setAlwaysOnTop(true, "pop-up-menu");
  panel.loadFile(path.join(REPO, "app/panel.html"));

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

  ipcMain.handle("install", (_e, args: { manifest: any; name: string; request: string }) =>
    helper.call("install", { xid: target.ident.xid, ...args }));
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  helper?.close();
});
app.on("window-all-closed", () => { /* keep running in the background */ });
