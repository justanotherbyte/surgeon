"""surgeon-run <id>: what a saved keybinding executes. No Codex, no Electron."""
import subprocess
import sys

from gi.repository import GLib

from . import desktop as d
from . import install
from . import manifest as m


def notify(title, body=""):
    subprocess.run(["notify-send", "-a", "Surgeon", "-i", "system-run", title, body], timeout=5)


def find_target(target):
    """The active window if it belongs to the target app, else the first window that does."""
    try:
        active = d.active_xid()
        if d.same_app(d.identity(active), target):
            return d.identity(active)
    except d.SurgeonError:
        pass
    for xid in d.client_xids():
        try:
            ident = d.identity(xid)
        except d.SurgeonError:
            continue
        if d.same_app(ident, target):
            return ident
    return None


def main(ext_id):
    ext = install.load(ext_id)
    ident = find_target(ext["target"])
    if ident is None:
        notify(f"{ext['name']}: app not open", f"Open {ext['target'].get('wm_class') or ext['target'].get('app_id')} first.")
        return 1
    try:
        result = m.run(ext["manifest"], ident)
    except (d.SurgeonError, GLib.Error) as e:
        result = {"ok": False, "error": getattr(e, "message", None) or str(e), "checks": []}
    if result["ok"]:
        paths = [c["path"] for c in result["checks"] if c.get("path")]
        notify(ext["name"], f"Saved {paths[0]}" if paths else "Done")
        return 0
    notify(f"{ext['name']} failed", result["error"] or "")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
