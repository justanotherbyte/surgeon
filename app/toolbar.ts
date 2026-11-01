// Sub-app toolbars beside the active app window. Labels come from Codex, so only textContent.
const { ipcRenderer } = (window as any).require("electron") as typeof import("electron");
const root = document.getElementById("root")!;

ipcRenderer.on("toolbars", (_e, { xid, toolbars }: { xid: string; toolbars: any[] }) => {
  root.replaceChildren(...toolbars.map((tb) => {
    const bar = document.createElement("div");
    bar.className = "hud toolbar";
    bar.setAttribute("aria-label", tb.name);
    const chip = document.createElement("span");
    chip.className = "route";
    chip.dataset.route = "helper";
    chip.textContent = "helper";
    chip.title = tb.name;
    bar.append(chip);
    tb.buttons.forEach((label: string, i: number) => {
      const btn = document.createElement("button");
      btn.className = "btn";
      btn.type = "button";
      btn.textContent = label;
      btn.addEventListener("click", () => {
        btn.setAttribute("aria-busy", "true");
        setTimeout(() => btn.removeAttribute("aria-busy"), 800);
        ipcRenderer.send("toolbar_click", { sub_id: tb.id, xid, button: i });
      });
      bar.append(btn);
    });
    return bar;
  }));
});

// Reached by the toolbar's key: arrows move between buttons, Esc hands focus back to the app.
document.addEventListener("keydown", (e) => {
  const buttons = [...root.querySelectorAll<HTMLButtonElement>("button")];
  const i = buttons.indexOf(document.activeElement as HTMLButtonElement);
  if (e.key === "Escape") ipcRenderer.send("toolbar_blur");
  else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    buttons[(i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
  }
});
ipcRenderer.on("toolbar_focus", () => root.querySelector<HTMLButtonElement>("button")?.focus());

new ResizeObserver(() => {
  const r = root.getBoundingClientRect();
  ipcRenderer.send("toolbar_size", { w: r.width, h: r.height });
}).observe(root);
