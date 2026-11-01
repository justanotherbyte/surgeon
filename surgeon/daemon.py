"""JSON-lines loop for Electron. Request {id, cmd, ...}, reply {id, ok, result | error}.
A running manifest also sends {id, event: {type: "step", ...}} lines."""
import json
import os
import re
import sys
import threading

from gi.repository import Gio, GLib

from . import desktop as d
from . import install
from . import manifest as m
from . import relaunch
from . import subapps

_out = threading.Lock()
_stop = threading.Event()
_watcher = None


def send(msg):
    with _out:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()


def _icon_path(info):
    icon = info.get_icon() if info else None
    if isinstance(icon, Gio.FileIcon):
        return icon.get_file().get_path()
    if isinstance(icon, Gio.ThemedIcon):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        found = Gtk.IconTheme.get_default().lookup_by_gicon(icon, 64, 0)
        return found.get_filename() if found else None
    return None


def target(xid=None):
    ident = d.identity(xid or d.active_xid())
    info = d.desktop_entry(ident)
    app = info.get_name() if info else (ident["wm_class"] or "App").capitalize()
    doc = re.split(r" [—-] ", ident["title"])[0].strip()
    frame = d.frame_for(ident)
    atspi_app = d.app_for(ident)
    toolkit = atspi_app.get_toolkit_name() if atspi_app else None
    nodes = sum(1 for _ in zip(range(20), d.walk(frame))) if frame else 0
    fix = relaunch.plan(ident, toolkit, nodes, frame is not None)
    return {
        "ident": ident, "app": app, "doc": doc if doc and doc != app else "",
        "icon": _icon_path(info),
        "accessible": frame is not None,
        "needs_relaunch": fix is not None,
        "relaunch": fix and {"kind": fix["kind"], "command": _shell(ident, fix)},
        "extensions": [{"id": e["id"], "name": e["name"], "accelerator": e["accelerator"], "manifest": e["manifest"]}
                       for e in install.extensions() if d.same_app(ident, e["target"])],
        "subapps": [s for s in subapps.load_all() if d.same_app(ident, s["target"])],
    }


def tools(xid):
    """What Surgeon can drive in this app, shown in the command bar so people see what's possible."""
    ident = d.identity(xid)
    allowed = lambda name: not m.DENY_ACTIONS.match(name)
    actions = sorted({k.split(".", 1)[1] for k, v in d.gtk_actions(ident).items()
                      if v["enabled"] and allowed(k.split(".", 1)[1]) and not re.search(r"-\d+-\d+$", k)})
    frame = d.frame_for(ident)
    actions += [a for a in (d.action_names(frame) if frame else []) if allowed(a.split(".", 1)[-1])]
    controls, seen = [], set()
    for _, (node, _ancestors) in zip(range(3000), d.walk(frame) if frame else ()):  # a capped walk keeps summon fast in huge apps
        try:
            if node.get_role_name() not in d.INTERACTIVE:
                continue
            name = node.get_name() or ""
        except GLib.Error:
            continue
        key = d.norm(name)
        if key and key not in seen and not m.DENY_LABELS.match(key):
            seen.add(key)
            controls.append(name.split("\n")[0].replace("_", "").strip())
    return {"actions": actions, "controls": controls, "commands": sorted(m.allowed_binaries(ident)),
            "dbus": d.dbus_names(ident)}


def _shell(ident, fix):
    try:
        return relaunch.shell_command(ident, fix)
    except d.SurgeonError:
        return None


def _relaunch(xid):
    t = target(xid)
    if not t["relaunch"]:
        return {"ok": True, "message": "Surgeon can already see inside it.", "xid": t["ident"]["xid"]}
    try:
        result = relaunch.relaunch(t["ident"], relaunch.FIXES[t["relaunch"]["kind"]])
    except d.SurgeonError as e:
        result = {"ok": False, "message": str(e)}
    result["command"] = t["relaunch"]["command"]
    return result


def verified(job, manifest):
    """Trust only a passing test_manifest logged by our MCP server for exactly this manifest."""
    log = m.DATA / "jobs" / os.path.basename(job) / "inspection.jsonl"
    if not log.exists():
        return False
    want = m.manifest_hash(manifest)
    for line in log.read_text().splitlines():
        entry = json.loads(line)
        if entry.get("tool") == "test_manifest" and entry.get("passed") and entry.get("hash") == want:
            return True
    return False


def _run(rid, xid, manifest):
    try:
        _stop.clear()
        result = m.run(manifest, d.identity(xid), emit=lambda e: send({"id": rid, "event": e}), stop=_stop.is_set)
        send({"id": rid, "ok": True, "result": result})
    except (d.SurgeonError, GLib.Error) as e:
        send({"id": rid, "ok": False, "error": getattr(e, "message", None) or str(e)})


def handle(req):
    cmd = req["cmd"]
    if cmd == "target":
        return target(req.get("xid"))
    if cmd == "tools":
        return tools(req["xid"])
    if cmd == "check":
        return {"verified": verified(req["job"], req["manifest"])}
    if cmd == "capture":
        return {"path": d.screenshot(req["xid"], req["path"])}
    if cmd == "undo":
        return m.undo(req["manifest"], d.identity(req["xid"]))
    if cmd == "relaunch":
        return _relaunch(req["xid"])
    if cmd == "stop":
        _stop.set()
        return {}
    if cmd == "install":
        return install.install(req["manifest"], d.identity(req["xid"]), req["name"], req.get("request", ""))
    if cmd == "uninstall":
        return install.uninstall(req["ext_id"])
    if cmd == "list":
        return {"extensions": install.extensions()}
    if cmd == "subapp_check":
        return {"reasons": subapps.gate(req["manifest"], req["job"], d.identity(req["xid"]))}
    if cmd == "subapp_install":
        return subapps.install(req["manifest"], req["job"], d.identity(req["xid"]), req.get("request", ""))
    if cmd == "subapp_enable":
        return subapps.set_enabled(req["sub_id"], req["enabled"])
    if cmd == "subapp_remove":
        return subapps.remove(req["sub_id"])
    if cmd == "subapp_trigger":
        _watcher.fire(req["sub_id"], req["xid"], req.get("button"))
        return {}
    raise d.SurgeonError(f"Unknown command {cmd!r}.")


def main():
    global _watcher
    _watcher = subapps.Watcher(lambda event: send({"push": event}))
    _watcher.start()
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        if req.get("cmd") == "run":
            threading.Thread(target=_run, args=(rid, req["xid"], req["manifest"]), daemon=True).start()
            continue
        try:
            send({"id": rid, "ok": True, "result": handle(req)})
        except Exception as e:  # report every failure to Electron instead of dying
            send({"id": rid, "ok": False, "error": getattr(e, "message", None) or str(e)})


if __name__ == "__main__":
    main()
