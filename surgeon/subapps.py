"""Sub-apps: helpers that run beside one app when no route can do the request.

The install gate checks Codex's claim that ranks 1 to 5 failed against the job's inspection log,
which Codex can't write. The watcher arms sub-apps while their app has a window and fires triggers.
"""
import json
import os
import re
import shutil
import sys
import threading
import time

from gi.repository import GLib

from . import desktop as d
from . import manifest as m

SUBAPP_DIR = m.DATA / "subapps"
RANK_TOOL = {1: "describe_app", 2: "describe_app", 3: "describe_app", 4: "describe_app", 5: "find_elements"}
RANK_NAME = {1: "GTK actions", 2: "window actions", 3: "other D-Bus APIs", 4: "the app's command line",
             5: "controls by name"}
UNAVAILABLE = {1: "gtk_actions", 2: "frame_actions", 3: "dbus_names"}  # summary count that must be 0
MAX_FAILURES = 3
# A change is at least CHANGED_PIXELS of the 32x32 gray samples moving by more than PIXEL_DELTA.
# Measured on GNOME Terminal: a printed line moved 4 to 17 pixels, a cursor blink 2, idle 0.
# The mean barely moves (0.2 to 0.4 of 255) for a line of text, so it can't be the test.
PIXEL_DELTA, CHANGED_PIXELS = 24, 3
SETTLED_SAMPLES = 2  # unchanged samples in a row after a change that count as finished


def title_decide(st, matches, now, seconds):
    """Feed whether the active window's title matches. Returns True once per visit, after the title
    has matched continuously for `seconds`."""
    if not matches:
        st["since"], st["fired"] = None, False
        return False
    if st["since"] is None:
        st["since"] = now
    if not st["fired"] and now - st["since"] >= seconds:
        st["fired"] = True
        return True
    return False


def watch_decide(st, sample, mode):
    """Feed one window sample to a watch's state. Returns True when the trigger should fire.
    changed: fire on each change. settled: fire once the window stops changing after a change."""
    last, st["last"] = st["last"], sample
    if last is None or sample is None:
        return False
    changed = sum(abs(a - b) > PIXEL_DELTA for a, b in zip(last, sample)) >= CHANGED_PIXELS
    if mode == "changed":
        return changed
    if changed:
        st["changing"], st["stable"] = True, 0
        return False
    if st["changing"]:
        st["stable"] += 1
        if st["stable"] >= SETTLED_SAMPLES:
            st["changing"] = False
            return True
    return False


def _log(job):
    path = m.DATA / "jobs" / job.replace("/", "") / "inspection.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def gate(manifest, job, ident):
    """Reasons to refuse this sub-app. An empty list means Surgeon may offer it."""
    sub = manifest.get("subapp")
    if not sub:
        return ["This plan is not a sub-app."]
    reasons = []
    try:
        m.check(manifest, ident)
    except d.SurgeonError as e:
        reasons.append(str(e))
    log = _log(job)
    calls = {tool: [e for e in log if e.get("tool") == tool and e.get("ok")] for tool in set(RANK_TOOL.values())}
    claimed = {e["rank"]: e for e in sub["exhausted"]}
    trig = sub["trigger"]
    all_steps = manifest["steps"] + [s for b in sub["buttons"] for s in b["steps"]]
    # Only work done outside the app (a script) is the last resort. A trigger or toolbar in front of
    # the app's own routes needs no proof that those routes failed.
    needs_proof = any(s["type"] == "script" for s in all_steps)
    for rank, tool in (RANK_TOOL.items() if needs_proof else ()):
        entry = claimed.get(rank)
        if entry is None:
            reasons.append(f"No reason given for why {RANK_NAME[rank]} (rank {rank}) can't do this.")
            continue
        if not calls[tool]:
            reasons.append(f"Surgeon never ran {tool} for this request, so rank {rank} wasn't checked.")
            continue
        outcome, summaries = entry["outcome"], [c.get("summary") or {} for c in calls[tool]]
        if outcome == "unavailable" and not (rank in UNAVAILABLE and any(s.get(UNAVAILABLE[rank]) == 0 for s in summaries)):
            reasons.append(f"Rank {rank} is marked unavailable, but describe_app found {RANK_NAME[rank]}.")
        if outcome == "no_match" and not (rank == 5 and any(s.get("query") and s.get("matches") == 0 for s in summaries)):
            reasons.append(f"Rank {rank} is marked no_match, but no search for it came back empty.")
        if outcome == "failed" and not any(e.get("tool") == "test_manifest" and not e.get("passed") for e in log):
            reasons.append(f"Rank {rank} is marked failed, but no test failed for this request.")
    if needs_proof and any((s.get("summary") or {}).get("needs_relaunch") for s in calls["describe_app"]):
        reasons.append("The app needs a restart with accessibility on first. That opens ranks 2 to 5.")
    if trig["type"] == "app_opened" and any(not s["reversible"] for s in all_steps):
        reasons.append("It runs when the app opens, with nobody acting, so every step must be reversible.")
    if trig["type"] == "hotkey" and not trig["accelerator"]:
        reasons.append("A hotkey trigger needs an accelerator.")
    if trig["type"] == "file_saved" and not trig["path"]:
        reasons.append("A file_saved trigger needs the path to watch.")
    if trig["type"] == "toolbar":
        if not 1 <= len(sub["buttons"]) <= 6:
            reasons.append("A toolbar needs 1 to 6 buttons.")
        if manifest["steps"]:
            reasons.append("A toolbar keeps its steps in its buttons, so top-level steps must be empty.")
    elif sub["buttons"]:
        reasons.append("Only a toolbar has buttons.")
    if trig["type"] == "watch" and not (trig["watch"] and 2 <= trig["watch"]["interval"] <= 60):
        reasons.append("A watch trigger needs an interval of 2 to 60 seconds.")
    if trig["type"] == "title":
        spec = trig["title"]
        if not (spec and 1 <= spec["seconds"] <= 86400):
            reasons.append("A title trigger needs a pattern and 1 to 86400 seconds.")
        else:
            try:
                re.compile(spec["pattern"])
            except re.error as e:
                reasons.append(f"The title pattern is not a valid regular expression: {e}.")
    if not any(e.get("tool") == "test_manifest" and e.get("passed") and e.get("hash") == m.manifest_hash(manifest)
               for e in log):
        reasons.append("Surgeon's own test didn't pass for exactly this sub-app.")
    return reasons


# ---------- storage ----------

def install(manifest, job, ident, request):
    reasons = gate(manifest, job, ident)  # again: the log could have changed since the check
    if reasons:
        raise d.SurgeonError(" ".join(reasons))
    sub_id = (re.sub(r"[^a-z0-9]+", "-", manifest["summary"].lower()).strip("-")[:32] or "helper") \
        + "-" + m.manifest_hash(manifest)[:6]
    record = {"id": sub_id, "name": manifest["summary"], "request": request, "enabled": True,
              "target": {k: ident.get(k) for k in ("app_id", "wm_class", "exe")}, "manifest": manifest}
    (SUBAPP_DIR / sub_id).mkdir(parents=True, exist_ok=True)
    (SUBAPP_DIR / sub_id / "subapp.json").write_text(json.dumps(record, indent=2))
    return {"id": sub_id}


def load_all():
    return [json.loads(p.read_text()) for p in sorted(SUBAPP_DIR.glob("*/subapp.json"))] if SUBAPP_DIR.exists() else []


def set_enabled(sub_id, enabled):
    path = SUBAPP_DIR / sub_id.replace("/", "") / "subapp.json"
    record = json.loads(path.read_text())
    record["enabled"] = bool(enabled)
    path.write_text(json.dumps(record, indent=2))
    return {"id": sub_id, "enabled": record["enabled"]}


def remove(sub_id):
    shutil.rmtree(SUBAPP_DIR / sub_id.replace("/", ""), ignore_errors=True)
    return {"id": sub_id}


# ---------- runtime ----------

SURGEON_CLASS = "app-surgeon"  # Surgeon's own windows: focusing a toolbar must not hide it


def _trig(rec):
    return rec["manifest"]["subapp"]["trigger"]


class Watcher(threading.Thread):
    """Arms each enabled sub-app on every window of its app, and fires its trigger.
    shortcut: polls _NET_CLIENT_LIST and watched files each second instead of systemd scope signals
    and inotify; X11 only, which Surgeon already is. Upgrade if polling shows up in profiles."""

    def __init__(self, send):
        super().__init__(daemon=True)
        self.send = send  # push a message to Electron
        self.idents = {}  # xid -> identity, read once per window
        self.armed = {}  # (sub_id, xid) -> record
        self.saves = {}  # (sub_id, xid) -> file_saved state
        self.watches = {}  # (sub_id, xid) -> watch state
        self.titles = {}  # (sub_id, xid) -> title dwell state
        self.active, self.geometry = None, None
        self.busy, self.failures = set(), {}
        self.lock = threading.Lock()

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:  # a bad window or sub-app must not stop the loop
                print(f"subapp watcher: {e}", file=sys.stderr)
            time.sleep(1)

    def tick(self):
        xids = [hex(int(x, 16)) for x in d.client_xids()]
        for xid in xids:
            if xid not in self.idents:
                try:
                    self.idents[xid] = d.identity(xid)
                except d.SurgeonError:
                    continue
        self.idents = {x: i for x, i in self.idents.items() if x in xids}
        subs = {s["id"]: s for s in load_all() if s["enabled"]}
        want = {(sid, x): s for sid, s in subs.items() for x, i in self.idents.items()
                if d.same_app(i, s["target"]) and not i.get("transient")}  # main windows only, not dialogs
        with self.lock:
            changed = want.keys() != self.armed.keys()
            for key in want.keys() - self.armed.keys():
                self.armed[key] = rec = want[key]
                self.failures[key[0]] = 0
                self.send({"type": "subapp.armed", "id": key[0], "xid": key[1], "name": rec["name"],
                           "trigger": _trig(rec)["type"]})
                if _trig(rec)["type"] == "file_saved":
                    self.saves[key] = {"path": None, "mtime": None, "pending": None, "quiet_until": 0}
                if _trig(rec)["type"] == "title":
                    self.titles[key] = {"since": None, "fired": False}
                if _trig(rec)["type"] == "watch":
                    self.watches[key] = {"last": None, "next": 0, "changing": False, "stable": 0}
                if _trig(rec)["type"] == "app_opened":
                    self.fire(*key)
            for key in self.armed.keys() - want.keys():
                del self.armed[key]
                self.saves.pop(key, None)
                self.watches.pop(key, None)
                self.titles.pop(key, None)
                self.send({"type": "subapp.disarmed", "id": key[0], "xid": key[1]})
        self.check_saves()
        self.check_watches()
        self.update_focus(changed)

    def update_focus(self, changed):
        """Hotkeys and toolbars exist only while their app's window is active."""
        try:
            active = hex(int(d.active_xid(), 16))
        except d.SurgeonError:
            active = None
        ident = self.idents.get(active) or {}
        if ident.get("wm_class") == SURGEON_CLASS:
            active = self.active  # the user is in Surgeon's panel or toolbar; keep the app's state
        mine = [(sid, r) for (sid, x), r in self.armed.items() if x == active]
        self.check_titles(active)
        toolbars = [{"id": sid, "name": r["name"], "accelerator": _trig(r)["accelerator"],
                     "buttons": [b["label"] for b in r["manifest"]["subapp"]["buttons"]]}
                    for sid, r in mine if _trig(r)["type"] == "toolbar"]
        geometry = d.window_geometry(active) if toolbars else None
        if active != self.active or changed or geometry != self.geometry:
            self.active, self.geometry = active, geometry
            self.send({"type": "subapp.focus", "xid": active, "at": geometry, "toolbars": toolbars,
                       "active": [{"id": sid, "accelerator": _trig(r)["accelerator"]}
                                  for sid, r in mine if _trig(r)["type"] == "hotkey"]})

    def check_saves(self):
        """Fire file_saved sub-apps once a watched file's mtime changes and then holds for a tick."""
        now = time.time()
        for key, st in list(self.saves.items()):
            rec, ident = self.armed.get(key), self.idents.get(key[1])
            if not rec or not ident:
                continue
            if st["path"] is None:
                path = m.fill(_trig(rec)["path"], ident)
                if os.path.isfile(path):
                    st["path"], st["mtime"] = path, os.path.getmtime(path)
                continue
            try:
                mtime = os.path.getmtime(st["path"])
            except OSError:
                continue  # mid-rename while the app saves
            if mtime == st["mtime"]:
                st["pending"] = None
            elif now < st["quiet_until"] or key[0] in self.busy:
                st["mtime"] = mtime  # our own run touched it: don't loop
            elif st["pending"] == mtime:
                st["mtime"], st["pending"] = mtime, None
                self.fire(*key)
            else:
                st["pending"] = mtime

    def check_titles(self, active):
        """Title triggers count time only while their window is the active one."""
        now = time.time()
        title = None
        for key, st in list(self.titles.items()):
            if key[1] != active:
                title_decide(st, False, now, 0)
                continue
            if title is None:
                title = d.xprop(active, "_NET_WM_NAME").get("_NET_WM_NAME") or ""
            spec = _trig(self.armed[key])["title"]
            if title_decide(st, bool(re.search(spec["pattern"], title, re.I)), now, spec["seconds"]):
                self.fire(*key)

    def check_watches(self):
        now = time.time()
        for key, st in list(self.watches.items()):
            rec = self.armed.get(key)
            if not rec or now < st["next"] or key[0] in self.busy:
                continue
            spec = _trig(rec)["watch"]
            st["next"] = now + spec["interval"]
            if watch_decide(st, d.sample(key[1]), spec["mode"]):
                self.fire(*key)

    def fire(self, sub_id, xid, button=None):
        """Run a sub-app, or one toolbar button, once. A trigger during a run is dropped, not queued."""
        xid = hex(int(xid, 16))
        with self.lock:
            rec = self.armed.get((sub_id, xid))
            if rec is None or sub_id in self.busy:
                return
            buttons = rec["manifest"]["subapp"]["buttons"]
            if button is not None and not 0 <= button < len(buttons):
                return
            self.busy.add(sub_id)
        manifest = m.button_manifest(rec["manifest"], button) if button is not None else rec["manifest"]
        threading.Thread(target=self._run, args=(rec, manifest, xid), daemon=True).start()

    def _run(self, rec, manifest, xid):
        sub_id = rec["id"]
        try:
            result = m.run(manifest, d.identity(xid),
                           emit=lambda e: e["type"] == "panel" and self.send({**e, "type": "subapp.panel", "id": sub_id, "name": rec["name"]}))
        except (d.SurgeonError, GLib.Error) as e:
            result = {"ok": False, "error": getattr(e, "message", None) or str(e)}
        finally:
            with self.lock:
                self.busy.discard(sub_id)
                for key, st in self.saves.items():
                    if key[0] == sub_id:
                        st["quiet_until"] = time.time() + 2
                for key, st in self.watches.items():
                    if key[0] == sub_id:  # our own steps may have changed the window: new baseline
                        st.update(last=None, changing=False, stable=0)
        if result["ok"]:
            self.failures[sub_id] = 0
            self.send({"type": "subapp.done", "id": sub_id, "name": rec["name"],
                       "files": [c["path"] for c in result.get("checks", []) if c.get("path")]})
            return
        self.failures[sub_id] = self.failures.get(sub_id, 0) + 1
        self.send({"type": "subapp.failed", "id": sub_id, "name": rec["name"], "error": result["error"]})
        if self.failures[sub_id] >= MAX_FAILURES:
            set_enabled(sub_id, False)
            self.send({"type": "subapp.disabled", "id": sub_id, "name": rec["name"],
                       "reason": f"It failed {MAX_FAILURES} times in a row."})
