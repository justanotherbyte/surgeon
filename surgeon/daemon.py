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

_out = threading.Lock()
_stop = threading.Event()


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


def _app_info(ident):
    for name in (ident["app_id"], ident["wm_class"], (ident["wm_class"] or "").lower()):
        if name:
            try:
                info = Gio.DesktopAppInfo.new(f"{name}.desktop")
            except TypeError:
                info = None
            if info:
                return info
    return None


def target(xid=None):
    ident = d.identity(xid or d.active_xid())
    info = _app_info(ident)
    app = info.get_name() if info else (ident["wm_class"] or "App").capitalize()
    doc = re.split(r" [—-] ", ident["title"])[0].strip()
    frame = d.frame_for(ident)
    atspi_app = d.app_for(ident)
    toolkit = atspi_app.get_toolkit_name() if atspi_app else None
    nodes = sum(1 for _ in zip(range(20), d.walk(frame))) if frame else 0
    return {
        "ident": ident, "app": app, "doc": doc if doc and doc != app else "",
        "icon": _icon_path(info),
        "accessible": frame is not None,
        "needs_relaunch": toolkit == "Chromium" and nodes < 10,
        "extensions": [{"id": e["id"], "name": e["name"], "accelerator": e["accelerator"], "manifest": e["manifest"]}
                       for e in install.extensions() if d.same_app(ident, e["target"])],
    }


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
    if cmd == "check":
        return {"verified": verified(req["job"], req["manifest"])}
    if cmd == "capture":
        return {"path": d.screenshot(req["xid"], req["path"])}
    if cmd == "undo":
        return m.undo(req["manifest"], d.identity(req["xid"]))
    if cmd == "stop":
        _stop.set()
        return {}
    if cmd == "install":
        return install.install(req["manifest"], d.identity(req["xid"]), req["name"], req.get("request", ""))
    if cmd == "uninstall":
        return install.uninstall(req["ext_id"])
    if cmd == "list":
        return {"extensions": install.extensions()}
    raise d.SurgeonError(f"Unknown command {cmd!r}.")


def main():
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
