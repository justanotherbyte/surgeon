// Panel renderer: command bar, plan, notice, toast. Model text only ever goes through textContent.
const { ipcRenderer } = (window as any).require("electron") as typeof import("electron");

type View = "bar" | "planning" | "plan" | "running" | "ran" | "notice" | "toast";
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
  for (const id of ["bar", "plan", "notice", "toast"]) $(id).hidden = !ids.includes(id);
}

function setIcon(img: HTMLImageElement, path: string | null) {
  img.hidden = !path;
  if (path) img.src = `file://${path}`;
}

// ---------- routes ----------

function routeOf(step: any) {
  if (["gtk_action", "frame_action", "dbus_call"].includes(step.type)) return "action";
  if (["cli", "open_uri"].includes(step.type)) return "command";
  return "control";
}

function routeText(step: any) {
  switch (step.type) {
    case "gtk_action":
    case "frame_action": return `${step.type} ${step.name.replace(/^(win|app)\./, "")}`;
    case "cli": return `cli ${step.argv.slice(0, 2).join(" ")}`;
    case "activate": return `activate ${step.name}`;
    case "confirm_if_present": return `confirm_if_present ${step.button}`;
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
  if (target?.needs_relaunch) {
    notice("warn", `Restart ${target.app} so Surgeon can see inside it`,
      `${target.app} started without accessibility turned on. Quit it and start it again with --force-renderer-accessibility.`, "i-restart");
  }
  input.focus();
}

function renderSaved() {
  const list = $("saved-list");
  list.replaceChildren();
  const exts = target?.extensions ?? [];
  $("saved").hidden = exts.length === 0;
  $("saved-head").textContent = `Saved for ${target?.app ?? ""}`;
  exts.forEach((ext: any, i: number) => {
    const row = el("li", "row");
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", String(i === savedIdx));
    row.append(icon("i-saved"), el("span", "label", ext.name), keys(...ext.accelerator.split("+")));
    row.addEventListener("click", () => { savedIdx = i; openSaved(); });
    list.append(row);
  });
}

function notice(tone: "info" | "warn" | "danger", title: string, text: string, iconId = "i-alert") {
  view = "notice";
  $("notice").dataset.tone = tone;
  $("notice-icon").setAttribute("href", `#${iconId}`);
  $("notice-title").textContent = title;
  $("notice-text").textContent = text;
  show("notice");
  $("notice-ok").focus();
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
  if (!r.manifest.feasible) {
    const tried = r.manifest.routes_tried.map((t: any) => t.route).join(", ");
    return notice("info", `Surgeon can't do this in ${target.app}`, r.manifest.summary + (tried ? ` Tried: ${tried}.` : ""));
  }
  renderPlan();
}

function openSaved() {
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
$("notice-ok").addEventListener("click", () => (target ? reset() : ipcRenderer.send("hide")));

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    e.preventDefault();
    if (view === "planning") { ipcRenderer.send("stop"); reset(); }
    else if (view === "running") ipcRenderer.send("stop");
    else if (view === "notice" && target && !target.needs_relaunch) reset();
    else ipcRenderer.send("hide");
  } else if (e.key === "Enter" && !e.repeat) {
    if (view === "bar" && document.activeElement === input) { e.preventDefault(); ask(); }
    else if (view === "plan" && document.activeElement?.id !== "save") {
      e.preventDefault();
      if (irreversible() < 0 || e.ctrlKey) run();
    } else if (view === "ran" && document.activeElement?.id !== "save") ipcRenderer.send("hide");
  } else if (view === "bar" && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
    const n = target?.extensions?.length ?? 0;
    if (!n) return;
    e.preventDefault();
    savedIdx = e.key === "ArrowDown" ? Math.min(n - 1, savedIdx + 1) : Math.max(-1, savedIdx - 1);
    renderSaved();
  }
});

new ResizeObserver(() => ipcRenderer.send("size", $("root").getBoundingClientRect().height)).observe($("root"));
