"""Manifest schema check, denylist, executor and verification checks.

The same executor backs test_manifest (Codex), the panel's Run button and surgeon-run.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import jsonschema
from gi.repository import GLib

from . import desktop as d
from .desktop import SurgeonError

DATA = Path(GLib.get_user_data_dir()) / "app-surgeon"
SCHEMA = json.loads((Path(__file__).parent.parent / "contracts" / "manifest.schema.json").read_text())

DENY_ACTIONS = re.compile(
    r"^(delete.*|move-trash|trash|empty-trash|format|send-signal-.*|kill.*|end-process|"
    r"clear-recent|clear-history|clear-list|set-wallpaper|quit|exit|logout|shutdown)$")
DENY_LABELS = re.compile(
    r"^(end process|kill( process)?|clear list|clear (recent|history).*|quit|exit|delete.*|"
    r"move to (the )?trash|empty trash|format.*|send signal.*|set as (wallpaper|background))$")
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "env", "python", "python3", "perl", "node", "sudo", "pkexec"}
CLEAN_ENV = ("ELECTRON_RUN_AS_NODE", "NO_AT_BRIDGE", "GTK_MODULES", "CHROME_DESKTOP")


def manifest_hash(m):
    """Hash of what actually runs. routes_tried and verified don't change behaviour."""
    core = {k: m.get(k) for k in ("steps", "verification", "undo")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def allowed_binaries(ident):
    exe = os.path.basename(ident.get("exe") or "")
    names = {exe, exe.removesuffix(".bin"), (ident.get("wm_class") or "").lower()}
    return {n for n in names if n}


def cli_allowed(argv0, ident):
    base = os.path.basename(argv0)
    if "/" in argv0 or base in SHELLS:  # bare names only, resolved on PATH, so /tmp/eog can't pass as eog
        return False
    allowed = allowed_binaries(ident)
    return base in allowed or any(a.startswith(base + "-") for a in allowed)


def check(manifest, ident):
    """Schema, denylist and cli rules. Raises SurgeonError naming the problem."""
    try:
        jsonschema.validate(manifest, SCHEMA)
    except jsonschema.ValidationError as e:
        raise SurgeonError(f"Manifest does not match the schema at {list(e.absolute_path)}: {e.message}")
    for step in manifest["steps"] + manifest["undo"]:
        kind = step["type"]
        if kind in ("gtk_action", "frame_action"):
            bare = step["name"].split(".", 1)[-1]
            if DENY_ACTIONS.match(bare):
                raise SurgeonError(f"Action {step['name']!r} is on Surgeon's blocked list.")
        if kind in ("activate", "confirm_if_present"):
            label = d.norm(step.get("name") or step.get("button"))
            if DENY_LABELS.match(label):
                raise SurgeonError(f"Pressing {label!r} is on Surgeon's blocked list.")
        if kind == "cli" and not cli_allowed(step["argv"][0], ident):
            raise SurgeonError(f"cli argv[0] must be the app's own binary ({', '.join(sorted(allowed_binaries(ident)))}),"
                               f" not {step['argv'][0]!r}.")


def placeholders(ident):
    title = ident.get("title") or ""
    stem = os.path.splitext(re.split(r" [-—] ", title)[0].strip())[0] or "untitled"
    docs = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or os.path.expanduser("~/Documents")
    xid = int(ident["xid"], 16)
    now = time.localtime(ident.get("run_started") or time.time())  # one timestamp per run
    return {"{date}": time.strftime("%Y-%m-%d", now), "{time}": time.strftime("%H%M%S", now), "{documents}": docs, "{stem}": stem,
            "{xid}": hex(xid), "{window_id}": str(xid), "{pid}": str(ident.get("pid") or "")}


def fill(text, ident):
    for key, value in placeholders(ident).items():
        text = text.replace(key, value)
    return os.path.expanduser(text)


# ---------- steps ----------

def _refresh(ident):
    title = d.xprop(ident["xid"], "_NET_WM_NAME").get("_NET_WM_NAME")
    if title is None:
        raise SurgeonError("The target window closed.")
    return {**ident, "title": title}


def _search_roots(ident, within):
    """Where to look for a control: a top-level window named `within`, else the target window, then all."""
    wins = d.windows(ident)
    if within:
        named = [w for _, n, w in wins if d.norm(within) in d.norm(n)]
        if named:
            return named, None
        return [w for *_, w in wins], within  # `within` names a menu or panel inside a window
    frame = d.frame_for(ident)
    return ([frame] if frame else []) + [w for *_, w in wins if w != frame], None


def _find_one(ident, role, name, within):
    # Retry without `within`: Codex sometimes scopes to a window title that names the document.
    for scope in ([within, None] if within else [None]):
        roots, inner = _search_roots(ident, scope)
        for root in roots:
            hits = d.find_controls(root, role, name, inner)
            if hits:
                return hits[0]
    where = f" in {within!r}" if within else ""
    raise SurgeonError(f"No showing {role or 'control'} named {name!r}{where}. Use find_elements to get exact names.")


def _press(node):
    names = d.action_names(node)
    if not names:
        raise SurgeonError(f"{node.get_role_name()} {node.get_name()!r} has no actions to press.")
    preferred = next((i for i, n in enumerate(names) if n in ("click", "press", "activate", "toggle")), 0)
    node.get_action_iface().do_action(preferred)


def _window_named(ident, name):
    """The newest top-level window whose name contains `name`. AT-SPI appends new windows last."""
    want = d.norm(name)
    return next((w for _, n, w in reversed(d.windows(ident)) if want and want in d.norm(n)), None)


def _close_new_windows(ident, before):
    """After a test, cancel dialogs the test left open so the next test starts clean."""
    for role, name, win in reversed(d.windows(ident)):
        if (role, name) in before or role not in ("dialog", "file chooser", "alert", "frame"):
            continue
        for label in ("Cancel", "Close"):  # never OK: it could confirm something
            hits = d.find_controls(win, "push button", label)
            if hits:
                _press(hits[0])
                time.sleep(0.3)
                break


def do_step(step, ident):
    """Run one step. Returns screen extents of what it acted on, or None."""
    kind = step["type"]
    if kind == "gtk_action":
        d.gtk_activate(ident, step["name"], step["param"])
        frame = d.frame_for(ident)
        return d.extents(frame) if frame else None
    if kind == "frame_action":
        frame = d.frame_for(ident)
        if frame is None:
            raise SurgeonError("Can't find the target window in the accessibility tree.")
        d.frame_action(frame, step["name"])
        return d.extents(frame)
    if kind == "cli":
        argv = [fill(a, ident) for a in step["argv"]]
        exe = shutil.which(argv[0]) or (ident["exe"] if os.path.basename(ident["exe"] or "") == argv[0] else None)
        if not exe:
            raise SurgeonError(f"{argv[0]!r} is not on PATH.")
        env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV}
        proc = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=30, env=env)
        if proc.returncode != 0:
            raise SurgeonError(f"{argv[0]} exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-300:]}")
        return None
    if kind == "activate":
        node = _find_one(ident, step["role"], step["name"], step["within"])
        ext = d.extents(node)
        _press(node)
        return ext
    if kind == "set_text":
        node = _set_text_target(ident, step)
        text = fill(step["text"], ident)
        et, t = node.get_editable_text_iface(), node.get_text_iface()
        et.delete_text(0, t.get_character_count())
        et.insert_text(0, text, len(text.encode()))
        return d.extents(node)
    if kind == "wait_for":
        win = d.wait(lambda: _window_named(ident, step["window"]), step["timeout"] or 5)
        if not win:
            raise SurgeonError(f"No window named {step['window']!r} appeared within {step['timeout']} s.")
        return d.extents(win)
    if kind == "confirm_if_present":
        win = d.wait(lambda: _window_named(ident, step["window"]), step["timeout"] or 3)
        if not win:
            return None  # optional dialog didn't show up
        hits = d.find_controls(win, "push button", step["button"])
        if not hits:
            raise SurgeonError(f"{step['window']!r} has no button {step['button']!r}.")
        ext = d.extents(hits[0])
        _press(hits[0])
        return ext
    raise SurgeonError(f"Unknown step type {kind!r}.")


def _set_text_target(ident, step):
    if step["name"]:
        return _find_one(ident, step["role"] or "text", step["name"], step["within"])
    roots, _ = _search_roots(ident, step["within"])
    for root in roots:
        for node, _ in d.walk(root, private=True):
            if node.get_role_name() in ("text", "entry") and {"editable", "showing"} <= d.states(node):
                return node
    raise SurgeonError(f"No editable text field in {step['within']!r}.")


# ---------- checks ----------

def baseline(manifest, ident):
    """State the checks compare against, read before any step runs."""
    base = {"started": time.time()}
    for c in manifest["verification"]:
        if c["type"] == "action_state":
            base[c["name"]] = d.gtk_state(ident, c["name"])[2]
        if c["type"] == "file_created":
            path = fill(c["path"], ident)
            base[path] = os.path.getmtime(path) if os.path.exists(path) else None
    return base


def verify(c, ident, base):
    kind = c["type"]
    if kind == "window_appears":
        ok = bool(d.wait(lambda: _window_named(ident, c["window"]), 4))
        return {"check": c, "passed": ok, "detail": "" if ok else f"no window named {c['window']!r}"}
    if kind == "file_created":
        path = fill(c["path"], ident)

        def fresh():
            return os.path.exists(path) and os.path.getsize(path) > 0 and os.path.getmtime(path) != base.get(path)
        ok = d.wait(fresh, 8)
        return {"check": c, "passed": bool(ok), "path": path, "detail": "" if ok else f"{path} was not written"}
    if kind == "action_state":
        now = d.gtk_state(ident, c["name"])[2]
        ok = now != base.get(c["name"])
        return {"check": c, "passed": ok, "detail": f"{c['name']} state {base.get(c['name'])} -> {now}"}
    return {"check": c, "passed": False, "detail": f"unknown check {kind!r}"}


# ---------- run ----------

def run(manifest, ident, emit=lambda event: None, test=False, stop=lambda: False):
    """Run a manifest against a live window. test=True also runs the undo steps afterwards.
    Returns {ok, steps, checks, undo, error, hash}."""
    check(manifest, ident)
    ident = {**_refresh(ident), "run_started": time.time()}
    out = {"ok": False, "steps": [], "checks": [], "undo": None, "error": None, "hash": manifest_hash(manifest)}
    before = {(r, n) for r, n, _ in d.windows(ident)}
    try:
        base = baseline(manifest, ident)
    except GLib.Error as e:
        out["error"] = f"Can't read the state a check needs: {e.message}"
        return out
    for i, step in enumerate(manifest["steps"]):
        if stop():
            out["error"] = f"Stopped before step {i + 1}."
            break
        emit({"type": "step", "index": i, "state": "running", "message": step["label"]})
        try:
            ident = _refresh(ident)
            ext = do_step(step, ident)
            out["steps"].append({"index": i, "ok": True})
            emit({"type": "step", "index": i, "state": "done", "extents": ext, "message": step["label"]})
            time.sleep(0.3)  # let the app react before the next step reads the tree
        except (SurgeonError, GLib.Error, subprocess.TimeoutExpired) as e:
            msg = getattr(e, "message", None) or str(e)
            out["steps"].append({"index": i, "ok": False, "error": msg})
            out["error"] = f"Step {i + 1} ({step['label']}) failed: {msg}"
            emit({"type": "step", "index": i, "state": "failed", "message": msg})
            break
    if out["error"] is None:
        ident = _refresh(ident)
        out["checks"] = [verify(c, ident, base) for c in manifest["verification"]]
        out["ok"] = all(c["passed"] for c in out["checks"])
        if not out["ok"]:
            out["error"] = "; ".join(c["detail"] for c in out["checks"] if not c["passed"])
    if test and manifest["undo"] and any(s["ok"] for s in out["steps"]):
        out["undo"] = undo(manifest, ident)
    if test:
        _close_new_windows(ident, before)
    return out


def undo(manifest, ident):
    try:
        ident = _refresh(ident)
        for step in manifest["undo"]:
            do_step(step, ident)
            time.sleep(0.3)
        return {"ok": True}
    except (SurgeonError, GLib.Error, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": getattr(e, "message", None) or str(e)}
