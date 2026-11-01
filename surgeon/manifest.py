"""Manifest schema check, denylist, executor and verification checks.

The same executor backs test_manifest (Codex), the panel's Run button and surgeon-run.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
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
    # reads and exhausted describe; the gate checks exhausted against the log and the user reads both.
    core["subapp"] = m.get("subapp") and {k: v for k, v in m["subapp"].items() if k not in ("reads", "exhausted")}
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
    sub = manifest["subapp"] or {}
    scripts = {sc["file"] for sc in sub.get("scripts", [])}
    _check_steps(manifest["steps"], manifest["undo"], ident, scripts, bool(sub))
    for button in sub.get("buttons", []):
        _check_steps(button["steps"], button["undo"], ident, scripts, True)


SUBAPP_ONLY = ("script", "panel", "capture", "notify", "agent")


def _check_steps(steps, undo_steps, ident, scripts, in_subapp):
    for step in steps + undo_steps:
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
    if any(step["type"] in SUBAPP_ONLY for step in undo_steps):
        raise SurgeonError("Undo can't contain script, panel, capture, notify or agent steps.")
    seen = set()
    for step in steps:
        if step["type"] in SUBAPP_ONLY and not in_subapp:
            raise SurgeonError(f"{step['type']} steps are only allowed in a sub-app.")
        if step["type"] == "script":
            if step["file"] not in scripts:
                raise SurgeonError(f"Script step names {step['file']!r}, which is not in subapp.scripts.")
            seen.add(step["file"])
        if step["type"] == "agent":
            if step["reversible"]:
                raise SurgeonError("An agent step can't be reversible: nobody knows in advance what it will do.")
            if not 1 <= step["max_actions"] <= MAX_AGENT_ACTIONS:
                raise SurgeonError(f"An agent step's max_actions must be 1 to {MAX_AGENT_ACTIONS}.")
            seen.add(step["file"])
        if step["type"] in ("panel", "notify") and step["source"] is not None and step["source"] not in seen:
            raise SurgeonError(f"{step['type']} source {step['source']!r} must be the file of an earlier script or agent step.")
        if step["type"] == "capture" and (not re.fullmatch(r"[\w.-]+", step["file"]) or step["file"] in (".", "..")):
            raise SurgeonError(f"Capture file {step['file']!r} must be a plain file name.")


def button_manifest(manifest, index):
    """One toolbar button as a runnable plan: its steps and undo, the sub-app's scripts."""
    button = manifest["subapp"]["buttons"][index]
    return {**manifest, "steps": button["steps"], "undo": button["undo"], "verification": []}


def placeholders(ident):
    title = ident.get("title") or ""
    stem = os.path.splitext(re.split(r" [-—] ", title)[0].strip())[0] or "untitled"
    docs = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or os.path.expanduser("~/Documents")
    xid = int(ident["xid"], 16)
    doc = d.document_path(ident) or ""
    now = time.localtime(ident.get("run_started") or time.time())  # one timestamp per run
    return {"{date}": time.strftime("%Y-%m-%d", now), "{time}": time.strftime("%H%M%S", now), "{documents}": docs, "{stem}": stem,
            "{xid}": hex(xid), "{window_id}": str(xid), "{pid}": str(ident.get("pid") or ""),
            "{window.title}": title, "{app.id}": ident.get("app_id") or ident.get("wm_class") or "",
            "{document.path}": doc, "{document.dir}": os.path.dirname(doc), "{created}": ident.get("_created", "")}


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
        # Never frames: a main window's title changes when its document changes ("photo.png*"),
        # so it looks new, and its "Close" button would close the app.
        if (role, name) in before or role not in ("dialog", "file chooser", "alert"):
            continue
        for label in ("Cancel", "Close"):  # never OK: it could confirm something
            hits = d.find_controls(win, "push button", label)
            if hits:
                _press(hits[0])
                time.sleep(0.3)
                break


def do_step(step, ident, ctx=None):
    """Run one step. Returns screen extents of what it acted on, or None.
    ctx carries a run's sub-app scripts, their outputs, and the panels to show."""
    kind = step["type"]
    if kind == "script":
        ctx["outputs"][step["file"]] = run_script(ctx["scripts"][step["file"]], [fill(a, ident) for a in step["args"]],
                                                  _workdir(ctx))
        if step["outputs_to"]:
            ctx["created"] += deliver(_workdir(ctx), fill(step["outputs_to"], ident))
        return None
    if kind == "agent":
        ctx["outputs"][step["file"]] = run_agent(step, ident)
        return None
    if kind == "launch":
        info = d.app_by_id(step["app"]) if step["app"] else d.desktop_entry(ident)
        if info is None:
            raise SurgeonError(f"No installed app {step['app'] or ident['wm_class']!r}. Use list_apps for desktop ids.")
        if "TerminalEmulator" in (info.get_categories() or ""):
            raise SurgeonError(f"Surgeon won't launch terminal emulators ({info.get_name()}).")
        args = [fill(a, ident) for a in step["args"]]
        for arg in args:
            if not (arg in LAUNCH_FLAGS or re.match(r"https?://\S+$", arg) or (os.path.isabs(arg) and os.path.exists(arg))):
                raise SurgeonError(f"Launch argument {arg!r} must be an http(s) URL, an existing file path, or one of "
                                   f"{', '.join(sorted(LAUNCH_FLAGS))}.")
        env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV}
        subprocess.Popen(d.launch_argv(info, args), env=env, cwd=os.path.expanduser("~"), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx["launched"].append(info)
        return None
    if kind == "capture":
        # The script reads the pixels; nothing here goes to the model.
        d.screenshot("root" if step["source"] == "screen" else ident["xid"], Path(_workdir(ctx)) / step["file"])
        return None
    if kind == "notify":
        body = ctx["outputs"][step["source"]].strip()[:500] if step["source"] else ""
        subprocess.run(["notify-send", "-a", "Surgeon", step["title"], body], timeout=5)
        return None
    if kind == "panel":
        text = ctx["outputs"][step["source"]]
        try:
            rows = json.loads(text)
            rows = [str(r) for r in rows][:50] if isinstance(rows, list) else None
        except ValueError:
            rows = None
        ctx["panels"].append({"title": step["title"], "rows": rows, "text": None if rows is not None else text})
        frame = d.frame_for(ident)
        return d.extents(frame) if frame else None
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


SANDBOX = Path(__file__).with_name("sandbox.py")
AGENT_JS = Path(__file__).parent.parent / "app" / "dist" / "agent.js"
MAX_AGENT_ACTIONS, AGENT_TIMEOUT = 10, 240  # keep AGENT_TIMEOUT under test_manifest's tool timeout in app/job.ts


def run_agent(step, ident):
    """Run Codex toward the step's goal. It acts only through run_steps, which goes through check()
    and the denylist like any plan. Returns its final message."""
    # Electron passes its own binary; ELECTRON_RUN_AS_NODE makes it plain Node (harmless for real node).
    node = os.environ.get("SURGEON_NODE") or shutil.which("node")
    if not node:
        raise SurgeonError("Can't find Node to run the agent. Start Surgeon with npm run dev.")
    env = {**os.environ, "ELECTRON_RUN_AS_NODE": "1"}
    try:
        proc = subprocess.run([node, str(AGENT_JS), ident["xid"], str(step["max_actions"]), step["goal"]],
                              capture_output=True, text=True, timeout=AGENT_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        raise SurgeonError(f"The agent ran longer than {AGENT_TIMEOUT} s.")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SurgeonError(f"The agent returned no result: {proc.stderr.strip()[-300:]}")
    if not result.get("ok"):
        raise SurgeonError(f"The agent didn't reach its goal: {result.get('message') or result.get('error')}")
    return result["message"]


LAUNCH_FLAGS = {"--new-window", "--new-tab", "--new-instance", "--private-window"}
MAX_CREATED, MAX_CREATED_BYTES = 20, 500 * 1024 * 1024


def deliver(workdir, dest):
    """Copy files a script wrote to ./out/ into dest, never overwriting. dest must be inside the
    home folder and not hidden, so a script can't plant ~/.config/autostart entries."""
    home = Path.home().resolve()
    target = Path(dest).expanduser().resolve()
    if target != home and home not in target.parents or any(p.startswith(".") for p in target.relative_to(home).parts):
        raise SurgeonError(f"Files can only go to a visible folder inside {home}, not {target}.")
    out = Path(workdir) / "out"
    files = sorted(f for f in out.iterdir() if f.is_file() and not f.is_symlink()) if out.is_dir() else []
    if len(files) > MAX_CREATED or sum(f.stat().st_size for f in files) > MAX_CREATED_BYTES:
        raise SurgeonError(f"A script may create at most {MAX_CREATED} files and 500 MB per run.")
    target.mkdir(parents=True, exist_ok=True)
    created = []
    for f in files:
        dst, n = target / f.name, 1
        while dst.exists():
            dst, n = target / f"{f.stem}-{n}{f.suffix}", n + 1
        shutil.move(str(f), dst)
        created.append(str(dst))
    return created


def _close_launched(ctx, before):
    """After a test, close windows the test's launch steps opened."""
    names = {(i.get_startup_wm_class() or "").lower() for i in ctx["launched"]} | \
            {(i.get_id() or "").removesuffix(".desktop").lower() for i in ctx["launched"]}
    names.discard("")
    time.sleep(1.5)  # let the launched app map its window
    for xid in set(d.client_xids()) - before:
        try:
            ident = d.identity(xid)
        except SurgeonError:
            continue
        if {(ident["wm_class"] or "").lower(), (ident["app_id"] or "").lower()} & names:
            subprocess.run(["wmctrl", "-i", "-c", xid], timeout=5)


def _workdir(ctx):
    """One temp dir per run, shared by its capture and script steps. run() removes it."""
    if not ctx.get("workdir"):
        ctx["workdir"] = tempfile.mkdtemp(prefix="surgeon-run-")
    return ctx["workdir"]


def run_script(content, args, workdir):
    """Run a sub-app script in the Landlock and seccomp sandbox, writable only in workdir.
    Returns stdout, capped at 64 KB."""
    path = Path(workdir) / ".script.py"
    path.write_text(content)
    env = {"PATH": "/usr/bin:/bin", "HOME": os.path.expanduser("~"), "LANG": os.environ.get("LANG", "C.UTF-8")}
    try:
        proc = subprocess.run(["/usr/bin/python3", "-I", str(SANDBOX), workdir, str(path), *args], cwd=workdir, env=env,
                              capture_output=True, text=True, timeout=30, close_fds=True)
    except subprocess.TimeoutExpired:
        raise SurgeonError("The script ran longer than 30 s.")
    if proc.returncode != 0:
        raise SurgeonError(f"The script exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    return proc.stdout[:65536]


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
    out = {"ok": False, "steps": [], "checks": [], "undo": None, "error": None, "hash": manifest_hash(manifest), "panels": []}
    ctx = {"scripts": {sc["file"]: sc["content"] for sc in (manifest["subapp"] or {}).get("scripts", [])},
           "outputs": {}, "panels": [], "created": [], "launched": []}
    clients_before = set(d.client_xids()) if test else set()
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
            ext = do_step(step, ident, ctx)
            if ctx["created"]:
                ident = {**ident, "_created": ctx["created"][0]}
            for panel in ctx["panels"][len(out["panels"]):]:
                out["panels"].append(panel)
                emit({"type": "panel", "xid": ident["xid"], "at": ext, **panel})
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
        if ctx["launched"]:
            _close_launched(ctx, clients_before)
        for path in ctx["created"]:  # a test leaves no files behind
            Path(path).unlink(missing_ok=True)
    out["created"] = [] if test else ctx["created"]
    if ctx.get("workdir"):
        shutil.rmtree(ctx["workdir"], ignore_errors=True)
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
