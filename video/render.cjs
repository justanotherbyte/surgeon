// Renders video/launch.html to video/out/launch.mp4, one exact frame at a time.
// Run: npm run video   (optional args: --from=<s> --to=<s> --fps=<n> --out=<path>)
const { app, BrowserWindow } = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const arg = (k, d) => (process.argv.find((a) => a.startsWith(`--${k}=`)) ?? `=${d}`).split("=")[1];
const FPS = Number(arg("fps", 30));
const OUT = path.resolve(arg("out", path.join(__dirname, "out", "launch.mp4")));
const FFMPEG = process.env.FFMPEG ?? "ffmpeg";

app.commandLine.appendSwitch("force-device-scale-factor", "1");
app.disableHardwareAcceleration();

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1920, height: 1080, show: false, useContentSize: true, webPreferences: { offscreen: true } });
  win.webContents.setUserAgent(win.webContents.getUserAgent() + " SurgeonRender");
  await win.loadFile(path.join(__dirname, "launch.html"));
  await win.webContents.executeJavaScript("document.fonts.ready.then(() => true)");
  const duration = await win.webContents.executeJavaScript("DURATION");
  const from = Number(arg("from", 0)), to = Number(arg("to", duration));

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const ff = spawn(FFMPEG, ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("exit", (c) => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));

  const frames = Math.round((to - from) * FPS);
  for (let i = 0; i < frames; i++) {
    const t = from + i / FPS;
    // Two animation frames so layout and paint reflect the new state before capture.
    await win.webContents.executeJavaScript(`seek(${t}); new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))`);
    const png = (await win.webContents.capturePage()).toPNG();
    if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once("drain", r));
    if (i % FPS === 0) process.stdout.write(`\r${t.toFixed(0)}s / ${to}s`);
  }
  ff.stdin.end();
  await done;
  console.log(`\nWrote ${OUT}`);
  app.quit();
}).catch((e) => { console.error(e); app.exit(1); });
