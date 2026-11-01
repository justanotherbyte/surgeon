// Panel renderer: command bar, plan, notice, toast. Model text only ever goes through textContent.
const { ipcRenderer } = (window as any).require("electron") as typeof import("electron");

type View = "bar" | "planning" | "plan" | "running" | "ran" | "notice" | "toast" | "consent" | "manage" | "subpanel";
let view: View = "bar";
let target: any = null;
let request = "";
let result: any = null; // JobResult from main
let savedIdx = -1;
let toastTimer = 0;

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const input = $<HTMLInputElement>("input");
const SVG = "http://www.w3.org/2000/svg";

function el(tag: string, cls = "", text = ""): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

function icon(id: string): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "icon");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `#${id}`);
  svg.append(use);
  return svg;
}

function keys(...names: string[]) {
  const span = el("span", "kbd");
  for (const n of names) span.append(el("kbd", "", n));
  return span;
}

function show(...ids: string[]) {
  for (const id of ["bar", "plan", "notice", "toast", "consent", "subpanel"]) $(id).hidden = !ids.includes(id);
}

function setIcon(img: HTMLImageElement, path: string | null) {
  img.hidden = !path;
  if (path) img.src = `file://${path}`;
}

// ---------- routes ----------

function routeOf(step: any) {
  if (["gtk_action", "frame_action", "dbus_call"].includes(step.type)) return "action";
  if (["cli", "open_uri", "launch"].includes(step.type)) return "command";
  if (["script", "panel", "capture", "notify"].includes(step.type)) return "helper";
  return "control";
}

function routeText(step: any) {
  switch (step.type) {
    case "gtk_action":
    case "frame_action": return `${step.type} ${step.name.replace(/^(win|app)\./, "")}`;
    case "cli": return `cli ${step.argv.slice(0, 2).join(" ")}`;
    case "activate": return `activate ${step.name}`;
    case "confirm_if_present": return `confirm_if_present ${step.button}`;
    case "capture": return `capture ${step.source}`;
    case "launch": return `launch ${step.app ?? "app"}`;
    default: return step.type;
  }
}

// ---------- views ----------

function reset() {
  view = "bar";
  result = null;
  savedIdx = -1;
  clearTimeout(toastTimer);
  setIcon($("target-icon") as HTMLImageElement, target?.icon ?? null);
  $("target-app").textContent = target?.app ?? "No window";
  $("target-doc").textContent = target?.doc ?? "";
  input.value = "";
  input.disabled = !target;
  input.placeholder = !target ? "Click an app window, then press Ctrl+Alt+Space"
    : target.accessible ? `Ask Surgeon to do something in ${target.app}`
    : `${target.app} only takes commands, such as a font size change`;
  $("status").hidden = true;
  $("enter-hint").hidden = false;
  renderSaved();
  show("bar");
  if (target?.needs_relaunch && !relaunchDismissed.has(target.ident.wm_class)) return relaunchNotice();
  input.focus();
}

function renderSaved() {
  const list = $("saved-list");
  list.replaceChildren();
  const exts = target?.extensions ?? [];
  const subs = target?.subapps ?? [];
  $("saved").hidden = exts.length + subs.length === 0;
  $("saved-head").textContent = `Saved for ${target?.app ?? ""}`;
  exts.forEach((ext: any, i: number) => {
    const row = el("li", "row");
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", String(i === savedIdx));
    row.append(icon("i-saved"), el("span", "label", ext.name), keys(...ext.accelerator.split("+")));
    row.addEventListener("click", () => { savedIdx = i; openSaved(); });
    list.append(row);
  });
  subs.forEach((sub: any, j: number) => {
    const i = exts.length + j;
    const row = el("li", "row");
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", String(i === savedIdx));
    const chip = el("span", "route", sub.enabled ? "helper" : "helper, off");
    chip.dataset.route = "helper";
    row.append(icon("i-saved"), el("span", "label", sub.name), chip);
    row.addEventListener("click", () => { savedIdx = i; openSaved(); });
    list.append(row);
  });
}

// ---------- sub-apps ----------

const RANK_NAME: Record<number, string> = {
  1: "GTK actions", 2: "Window actions", 3: "Other D-Bus APIs", 4: "The app's command line", 5: "Controls by name",
};
let managing: any = null; // installed sub-app record shown in the manage view

function renderConsent(manifest: any, record: any = null) {
  view = record ? "manage" : "consent";
  managing = record;
  const sub = manifest.subapp;
  setIcon($("consent-icon") as HTMLImageElement, target?.icon ?? null);
  $("consent-title").textContent = record ? record.name : request;
  $("consent-sub").textContent = record ? (record.enabled ? "Installed helper" : "Installed helper, turned off") : manifest.summary;
  const proof = sub.exhausted.length > 0;
  $("consent-gap").hidden = $("consent-routes").hidden = !proof;
  $("consent-gap").textContent = `${target.app} can't do this through its own actions, commands or controls. Surgeon checked:`;
  const routes = $("consent-routes");
  routes.replaceChildren();
  for (const e of [...sub.exhausted].sort((a: any, b: any) => a.rank - b.rank)) {
    const li = el("li");
    if (e.outcome === "unsuitable") {
      const tag = el("span", "tag", "Codex judged");
      tag.dataset.tone = "warn";
      li.append(tag);
    }
    li.append(el("span", "", `${RANK_NAME[e.rank] ?? `Rank ${e.rank}`}: ${e.reason}`));
    routes.append(li);
  }
  const trig = sub.trigger;
  const file = !trig.path ? "" : trig.path.includes("{document.path}") ? "the open file" : trig.path.split("/").pop();
  $("consent-trigger").textContent = {
    hotkey: `When you press ${trig.accelerator} in ${target.app}`,
    app_opened: `When ${target.app} opens`,
    file_saved: `Each time you save ${file} in ${target.app}`,
    toolbar: `As buttons beside ${target.app}` + (trig.accelerator ? `. ${trig.accelerator} moves to them` : ""),
    title: trig.title && `When ${target.app}'s title matches "${trig.title.pattern}" for ${trig.title.seconds} s while it's in front`,
    watch: trig.watch && (trig.watch.mode === "settled"
      ? `When ${target.app}'s window stops changing, checked every ${trig.watch.interval} s`
      : `Each time ${target.app}'s window changes, checked every ${trig.watch.interval} s`),
  }[trig.type as string] ?? trig.type;
  const steps = $("consent-steps");
  steps.replaceChildren();
  const addSteps = (list: any[]) => {
    for (const step of list) {
      const li = el("li");
      const meta = el("span", "step-meta");
      if (!step.reversible) {
        const tag = el("span", "tag", "Can't undo");
        tag.dataset.tone = "warn";
        meta.append(tag);
      }
      if (step.type === "script" && step.outputs_to) {
        const tag = el("span", "tag", `Creates files in ${step.outputs_to.replace("{document.dir}", "the file's folder").replace("{documents}", "Documents")}`);
        tag.dataset.tone = "warn";
        meta.append(tag);
      }
      if (step.type === "capture" && step.source === "screen") {
        const tag = el("span", "tag", "Sees your whole screen");
        tag.dataset.tone = "danger";
        meta.append(tag);
      }
      const chip = el("span", "route", routeText(step));
      chip.dataset.route = routeOf(step);
      meta.append(chip);
      li.append(el("span", "", step.label), meta);
      steps.append(li);
    }
  };
  if (trig.type === "toolbar") {
    for (const b of sub.buttons) {
      steps.append(el("li", "button-name", `Button: ${b.label}`));
      addSteps(b.steps);
    }
  } else addSteps(manifest.steps);
  const allSteps = [...manifest.steps, ...sub.buttons.flatMap((b: any) => b.steps)];
  $("consent-hint").textContent = allSteps.some((st: any) => st.type === "capture" && st.source === "screen")
    ? "Its script sees everything on your screen, including other apps. Nothing goes to Codex"
    : sub.scripts.length
    ? "Scripts run sandboxed: no network, no sockets, no writes, no signals"
    : `Uses only ${target.app}'s own actions, controls and command line`;
  $("consent-reads").textContent = sub.reads.join("; ");
  const scripts = $("consent-scripts");
  scripts.replaceChildren();
  for (const sc of sub.scripts) scripts.append(el("div", "script-name", sc.file), el("pre", "script", sc.content));
  $("consent-install").hidden = !!record;
  $("consent-remove").hidden = !record;
  $("consent-toggle").hidden = !record;
  $("consent-toggle").textContent = record?.enabled ? "Turn off" : "Turn on";
  show("consent");
}

async function installSubapp() {
  const m = result.manifest;
  const btn = $("consent-install");
  btn.setAttribute("aria-busy", "true");
  try {
    await ipcRenderer.invoke("subapp_install", { job: result.jobId, manifest: m, request });
    const trig = m.subapp.trigger;
    if (trig.type === "hotkey") toast("Helper installed", ["Hotkey", ...trig.accelerator.split("+")]);
    else toast(`Helper installed. It runs when ${target.app} opens`);
  } catch (e: any) {
    notice("danger", "Surgeon won't install this helper", String(e.message).replace(/^Error invoking remote method '\w+': (Error: )?/, ""), "i-ban");
  } finally {
    btn.removeAttribute("aria-busy");
  }
}

async function toggleSubapp() {
  const r = await ipcRenderer.invoke("subapp_enable", { sub_id: managing.id, enabled: !managing.enabled });
  managing.enabled = r.enabled;
  renderConsent(managing.manifest, managing);
}

async function removeSubapp() {
  await ipcRenderer.invoke("subapp_remove", managing.id);
  target.subapps = target.subapps.filter((s: any) => s.id !== managing.id);
  toast(`Removed ${managing.name}`);
}

function renderSubpanel(ev: any) {
  view = "subpanel";
  $("sub-title").textContent = ev.title;
  $("sub-name").textContent = ev.name;
  const rows = $("sub-rows");
  rows.replaceChildren(...(ev.rows ?? []).map((r: string) => {
    const li = el("li", "row");
    li.append(el("span", "label", r));
    li.title = r;
    return li;
  }));
  rows.hidden = !ev.rows;
  $("sub-text").hidden = !!ev.rows;
  $("sub-text").textContent = ev.text ?? "";
  show("subpanel");
  $("sub-close").focus();
}

type NoticeOpts = { action?: { label: string; run: () => void }; dismiss?: () => void; okLabel?: string; command?: string | null };
let noticeOpts: NoticeOpts = {};

function notice(tone: "info" | "warn" | "danger", title: string, text: string, iconId = "i-alert", opts: NoticeOpts = {}) {
  view = "notice";
  noticeOpts = opts;
  $("notice").dataset.tone = tone;
  $("notice-icon").setAttribute("href", `#${iconId}`);
  $("notice-title").textContent = title;
  $("notice-text").textContent = text;
  $("notice-cmd").hidden = $("notice-copy").hidden = !opts.command;
  $("notice-command").textContent = opts.command ?? "";
  $("notice-copy").textContent = "Copy command";
  $("notice-action").hidden = !opts.action;
  $("notice-action").removeAttribute("aria-busy");
  $("notice-action-label").textContent = opts.action?.label ?? "";
  $("notice-ok-label").textContent = opts.okLabel ?? "OK";
  show("notice");
  (opts.action ? $("notice-action") : $("notice-ok")).focus();
}

function dismissNotice() {
  if (noticeOpts.dismiss) noticeOpts.dismiss();
  else if (target) reset();
  else ipcRenderer.send("hide");
}

// Apps the user said "Not now" to, this session. Watch and title helpers work without accessibility.
const relaunchDismissed = new Set<string>();

function relaunchNotice() {
  const app = target.app;
  const how = target.relaunch.kind === "electron"
    ? "the accessibility flag" : "accessibility turned on (GNOME_ACCESSIBILITY=1)";
  notice("warn", `Restart ${app} so Surgeon can see inside it`,
    `${app} started without accessibility, so Surgeon can't see its controls. Surgeon can close it and start it again with ${how}. ${app} may ask about unsaved work first.`,
    "i-restart", {
      action: { label: `Restart ${app}`, run: doRelaunch },
      okLabel: "Not now",
      dismiss: () => { relaunchDismissed.add(target.ident.wm_class); reset(); },
    });
}

async function doRelaunch() {
  const app = target.app;
  $("notice-action").setAttribute("aria-busy", "true");
  $("notice-text").textContent = `Closing ${app} and starting it again…`;
  const r = await ipcRenderer.invoke("relaunch");
  if (r.ok) return; // main sends the new target, which resets the panel
  notice("warn", `Surgeon couldn't restart ${app}`,
    r.command ? `${r.message} Quit ${app}, then paste this into a terminal:` : r.message, "i-restart",
    { command: r.command, dismiss: () => { relaunchDismissed.add(target.ident.wm_class); reset(); } });
}

function toast(text: string, keyNames: string[] = []) {
  view = "toast";
  $("toast-text").textContent = text;
  $("toast-keys").replaceChildren(...(keyNames.length ? [document.createTextNode(keyNames[0] + " "), ...keyNames.slice(1).map((k) => el("kbd", "", k))] : []));
  $("toast-sep").hidden = keyNames.length === 0;
  show("toast");
  toastTimer = window.setTimeout(() => ipcRenderer.send("hide"), 4000);
}

const irreversible = () => result.manifest.steps.findIndex((s: any) => !s.reversible);

function renderPlan() {
  view = "plan";
  const m = result.manifest;
  setIcon($("plan-icon") as HTMLImageElement, target?.icon ?? null);
  $("plan-ask").textContent = request;
  $("plan-summary").textContent = m.summary;
  const steps = $("steps");
  steps.replaceChildren();
  for (const step of m.steps) {
    const li = el("li", "step");
    const state = el("span", "step-state");
    state.append(icon("i-check"));
    const meta = el("span", "step-meta");
    if (!step.reversible) {
      const tag = el("span", "tag", "Can't undo");
      tag.dataset.tone = "warn";
      meta.append(tag);
    }
    const chip = el("span", "route", routeText(step));
    chip.dataset.route = routeOf(step);
    chip.title = routeText(step);
    meta.append(chip);
    li.append(state, el("span", "step-text", step.label), meta);
    steps.append(li);
  }
  const bad = irreversible();
  const hint = result.verified
    ? (bad >= 0 ? `Tested. Step ${bad + 1} can't be undone` : `Tested on ${target.app}${result.seconds ? ` in ${result.seconds} s` : ""}`)
    : "Not verified. Surgeon's own test didn't pass for this plan";
  $("plan-hint").textContent = hint;
  $("save").hidden = !result.verified || !!result.saved;
  setRunButton("Run", bad >= 0 ? ["Ctrl", "Enter"] : ["Enter"]);
  show("plan");
}

function setRunButton(label: string, keyNames: string[]) {
  const btn = $("run");
  btn.replaceChildren(document.createTextNode(label + " "), keys(...keyNames));
  btn.removeAttribute("aria-busy");
}

// ---------- actions ----------

async function ask() {
  request = input.value.trim();
  if (!request) return openSaved();
  view = "planning";
  input.disabled = true;
  $("status").hidden = false;
  $("status-text").textContent = "Planning";
  $("enter-hint").hidden = true;
  const r = await ipcRenderer.invoke("ask", request);
  if (view !== "planning") return; // Esc while planning
  result = r;
  if (r.error) return r.error === "Stopped" ? reset() : notice("danger", "Codex couldn't finish", r.error);
  if (r.manifest.feasible && r.manifest.subapp) {
    return r.gate?.length ? notice("danger", "Surgeon won't offer this helper", r.gate.join(" "), "i-ban")
      : renderConsent(r.manifest);
  }
  if (!r.manifest.feasible) {
    const tried = r.manifest.routes_tried.map((t: any) => t.route).join(", ");
    return notice("info", `Surgeon can't do this in ${target.app}`, r.manifest.summary + (tried ? ` Tried: ${tried}.` : ""));
  }
  renderPlan();
}

function openSaved() {
  const nExt = target?.extensions?.length ?? 0;
  if (savedIdx >= nExt) {
    const sub = target?.subapps?.[savedIdx - nExt];
    return sub && renderConsent(sub.manifest, sub);
  }
  const ext = target?.extensions?.[savedIdx];
  if (!ext) return;
  request = ext.name;
  result = { manifest: ext.manifest, verified: true, saved: true };
  renderPlan();
  $("plan-hint").textContent = `Saved as ${ext.accelerator}`;
}

async function run() {
  view = "running";
  $("save").hidden = true;
  $("run").setAttribute("aria-busy", "true");
  for (const li of $("steps").children) delete (li as HTMLElement).dataset.state;
  let res: any;
  try {
    res = await ipcRenderer.invoke("run", result.manifest);
  } catch (e: any) {
    return notice("danger", "Surgeon won't run this", String(e.message).replace(/^Error invoking remote method 'run': (Error: )?/, ""), "i-ban");
  }
  view = "ran";
  const file = res.checks?.find((c: any) => c.path)?.path;
  $("plan-hint").textContent = res.ok ? (file ? `Done. Saved ${file.split("/").pop()}` : "Done") : (res.error ?? "Failed");
  $("save").hidden = !res.ok || !result.verified || !!result.saved;
  setRunButton("Close", ["Esc"]);
}

async function save() {
  const btn = $("save");
  btn.setAttribute("aria-busy", "true");
  try {
    const r = await ipcRenderer.invoke("install", { manifest: result.manifest, name: result.manifest.summary || request, request });
    toast(`Saved. Press it in ${target.app} any time, even with Surgeon closed`, ["Shortcut", ...r.accelerator.split("+")]);
  } catch (e: any) {
    notice("danger", "Couldn't save the shortcut", String(e.message));
  } finally {
    btn.removeAttribute("aria-busy");
  }
}

// ---------- wiring ----------

ipcRenderer.on("target", (_e, t) => { target = t; reset(); });
ipcRenderer.on("status", (_e, s) => { $("status-text").textContent = s.text; });
ipcRenderer.on("notice", (_e, n) => { target = null; reset(); notice(n.tone, n.title, n.text); });
ipcRenderer.on("subpanel", (_e, ev) => renderSubpanel(ev));
ipcRenderer.on("subtoast", (_e, ev) => {
  target = null;
  toast(ev.files?.length ? `${ev.name}: saved ${ev.files[0].split("/").pop()}` : `Ran ${ev.name}`);
});
ipcRenderer.on("subnotice", (_e, ev) => {
  target = null; // pushed while Surgeon may be closed; Esc or OK just hides
  notice("warn", ev.type === "subapp.disabled" ? `Turned off ${ev.name}` : `${ev.name} failed`, ev.reason ?? ev.error);
});
ipcRenderer.on("step", (_e, ev) => {
  const li = $("steps").children[ev.index] as HTMLElement | undefined;
  if (!li) return;
  li.dataset.state = ev.state;
  if (ev.state === "failed") {
    li.querySelector(".step-state")!.replaceChildren(icon("i-x"));
    const text = li.querySelector(".step-text")!;
    text.querySelector(".step-note")?.remove();
    text.append(el("span", "step-note", ev.message));
  }
});

$("run").addEventListener("click", () => (view === "plan" ? run() : view === "ran" && ipcRenderer.send("hide")));
$("save").addEventListener("click", save);
$("consent-install").addEventListener("click", installSubapp);
$("consent-toggle").addEventListener("click", toggleSubapp);
$("consent-remove").addEventListener("click", removeSubapp);
$("sub-close").addEventListener("click", () => ipcRenderer.send("hide"));
$("notice-ok").addEventListener("click", dismissNotice);
$("notice-action").addEventListener("click", () => noticeOpts.action?.run());
$("notice-copy").addEventListener("click", () => {
  (window as any).require("electron").clipboard.writeText($("notice-command").textContent ?? "");
  $("notice-copy").textContent = "Copied";
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    e.preventDefault();
    if (view === "planning") { ipcRenderer.send("stop"); reset(); }
    else if (view === "running") ipcRenderer.send("stop");
    else if (view === "notice") dismissNotice();
    else if ((view === "consent" || view === "manage") && target) reset();
    else ipcRenderer.send("hide");
  } else if (e.key === "Enter" && !e.repeat) {
    if (view === "consent") { if (e.ctrlKey) { e.preventDefault(); installSubapp(); } } // plain Enter never installs
    else if (view === "notice" && noticeOpts.action && document.activeElement?.id !== "notice-ok"
             && document.activeElement?.id !== "notice-copy") { e.preventDefault(); noticeOpts.action.run(); }
    else if (view === "bar" && document.activeElement === input) { e.preventDefault(); ask(); }
    else if (view === "plan" && document.activeElement?.id !== "save") {
      e.preventDefault();
      if (irreversible() < 0 || e.ctrlKey) run();
    } else if (view === "ran" && document.activeElement?.id !== "save") ipcRenderer.send("hide");
  } else if (view === "bar" && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
    const n = (target?.extensions?.length ?? 0) + (target?.subapps?.length ?? 0);
    if (!n) return;
    e.preventDefault();
    savedIdx = e.key === "ArrowDown" ? Math.min(n - 1, savedIdx + 1) : Math.max(-1, savedIdx - 1);
    renderSaved();
  }
});

new ResizeObserver(() => ipcRenderer.send("size", $("root").getBoundingClientRect().height)).observe($("root"));
