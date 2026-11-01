"""Save a manifest as an extension and bind it to a GNOME custom keybinding.

GNOME stores and fires the keybinding, so the shortcut keeps working with Surgeon and Codex closed.
"""
import ast
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from . import manifest as m

KEYS = "org.gnome.settings-daemon.plugins.media-keys"
ITEM = KEYS + ".custom-keybinding"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
REPO = Path(__file__).resolve().parent.parent
EXT_DIR = m.DATA / "extensions"


def gsettings(*args):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, check=True, timeout=5).stdout.strip()


def _paths():
    raw = gsettings("get", KEYS, "custom-keybindings").removeprefix("@as ")
    return list(ast.literal_eval(raw))


def _used_bindings():
    out = set()
    for path in _paths():
        out.add(ast.literal_eval(gsettings("get", f"{ITEM}:{path}", "binding") or "''"))
    return out


def command_for(ext_id):
    return f"env PYTHONPATH={shlex.quote(str(REPO))} /usr/bin/python3 -m surgeon.run {shlex.quote(ext_id)}"


def install(manifest, target, name, request):
    """Write the extension and bind the first free Ctrl+Alt+1..9. Returns {id, accelerator}."""
    used = _used_bindings()
    digit = next((n for n in range(1, 10) if f"<Control><Alt>{n}" not in used), None)
    if digit is None:
        raise m.SurgeonError("Ctrl+Alt+1 to 9 are all taken. Remove a saved shortcut first.")
    ext_id = (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "ext") + "-" + m.manifest_hash(manifest)[:6]
    binding = f"<Control><Alt>{digit}"
    ext = {"id": ext_id, "name": name, "request": request, "accelerator": f"Ctrl+Alt+{digit}",
           "binding": binding, "target": {k: target.get(k) for k in ("app_id", "wm_class", "exe")},
           "manifest": manifest}
    (EXT_DIR / ext_id).mkdir(parents=True, exist_ok=True)
    (EXT_DIR / ext_id / "manifest.json").write_text(json.dumps(ext, indent=2))
    path = f"{BASE}surgeon-{ext_id}/"
    schema = f"{ITEM}:{path}"
    gsettings("set", schema, "name", f"Surgeon: {name}")
    gsettings("set", schema, "command", command_for(ext_id))
    gsettings("set", schema, "binding", binding)
    paths = _paths()
    if path not in paths:
        gsettings("set", KEYS, "custom-keybindings", str(paths + [path]))
    return {"id": ext_id, "accelerator": ext["accelerator"]}


def uninstall(ext_id):
    path = f"{BASE}surgeon-{ext_id}/"
    gsettings("set", KEYS, "custom-keybindings", str([p for p in _paths() if p != path]))
    for key in ("name", "command", "binding"):
        gsettings("reset", f"{ITEM}:{path}", key)
    shutil.rmtree(EXT_DIR / ext_id, ignore_errors=True)
    return {"id": ext_id}


def load(ext_id):
    return json.loads((EXT_DIR / ext_id / "manifest.json").read_text())


def extensions():
    if not EXT_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(EXT_DIR.glob("*/manifest.json"))]
