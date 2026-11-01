"""Restart an app so Surgeon can see inside it, or say exactly how to.

Electron apps expose an accessibility tree only with --force-renderer-accessibility. Firefox-family
browsers (Firefox, Zen) register only when started with GNOME_ACCESSIBILITY=1. Surgeon closes the
app's windows politely (the app can still ask about unsaved work), waits for it to exit, and starts
it again as it was: the same command line, environment and folder, plus the fix.
"""
import os
import shlex
import subprocess
import time

from . import desktop as d
from .desktop import SurgeonError
from .manifest import CLEAN_ENV  # T3 Code's variables, which also hide apps from AT-SPI


FIXES = {
    "electron": {"kind": "electron", "args": ["--force-renderer-accessibility"], "env": {}},
    "gecko": {"kind": "gecko", "args": [], "env": {"GNOME_ACCESSIBILITY": "1"}},
}


def plan(ident, toolkit, nodes, has_frame):
    """What the app needs to become visible, or None."""
    if toolkit == "Chromium" and nodes < 10:
        return FIXES["electron"]
    if not has_frame and ident.get("instance") == "Navigator":  # Firefox's WM_CLASS instance, kept by forks
        return FIXES["gecko"]
    return None


def _process(pid):
    """argv, environment and cwd of a running process, or None."""
    try:
        argv = [os.fsdecode(a) for a in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if a]
        if len(argv) == 1 and " " in argv[0] and not os.path.exists(argv[0]):
            # Chromium rewrites its process title into one space-joined string.
            # shortcut: an argument that itself contains spaces comes back split; rare for app launches.
            argv = argv[0].split(" ")
        env = dict(line.split("=", 1) for line in open(f"/proc/{pid}/environ", "rb").read().decode(errors="replace").split("\0")
                   if "=" in line)
        return argv, env, os.readlink(f"/proc/{pid}/cwd")
    except (OSError, TypeError):
        return None


def command(ident, fix):
    """How to start the app again with the fix: (argv, env, cwd)."""
    proc = _process(ident.get("pid")) if ident.get("pid") else None
    if proc:
        argv, env, cwd = proc
        if not {"DISPLAY", "PATH", "HOME"} <= env.keys():
            env = dict(os.environ)  # Chromium's process-title rewrite overwrites environ too; use the session's
        env = {k: v for k, v in env.items() if k not in CLEAN_ENV}
        return argv + [a for a in fix["args"] if a not in argv], {**env, **fix["env"]}, cwd
    info = d.desktop_entry(ident)
    if info is None:
        raise SurgeonError(f"Surgeon can't find how {ident['wm_class']} was started.")
    argv = d.launch_argv(info, fix["args"])
    if os.path.basename(argv[0]) == "flatpak" and "run" in argv:  # flatpak run doesn't pass the environment on
        i = argv.index("run") + 1
        argv[i:i] = [f"--env={k}={v}" for k, v in fix["env"].items()]
        extra = {}
    else:
        extra = fix["env"]
    env = {k: v for k, v in os.environ.items() if k not in CLEAN_ENV}
    return argv, {**env, **extra}, os.path.expanduser("~")


def shell_command(ident, fix):
    """A command to paste into a terminal, after quitting the app."""
    proc = bool(ident.get("pid") and _process(ident["pid"]))
    argv, _, _ = command(ident, fix)
    if not proc and os.path.basename(argv[0]) == "flatpak":
        return shlex.join(["setsid", "-f", *argv])
    prefix = ["env", "-u", "ELECTRON_RUN_AS_NODE", "-u", "CHROME_DESKTOP", "-u", "NO_AT_BRIDGE"]
    return shlex.join(["setsid", "-f", *prefix, *[f"{k}={v}" for k, v in fix["env"].items()], *argv])


def _windows(target):
    out = []
    for xid in d.client_xids():
        try:
            if d.same_app(d.identity(xid), target):
                out.append(xid)
        except SurgeonError:
            continue
    return out


def _running(ident, info):
    if ident.get("pid"):
        return os.path.exists(f"/proc/{ident['pid']}")
    app_id = (info.get_id() or "").removesuffix(".desktop") if info else ""
    if not app_id:
        return False
    out = subprocess.run(["flatpak", "ps", "--columns=application"], capture_output=True, text=True, timeout=5).stdout
    return app_id in out.split()


def relaunch(ident, fix, close_timeout=15, open_timeout=25):
    """Close the app, start it again with the fix, and check Surgeon can see it.
    Returns {ok, message, xid}. On failure the caller shows shell_command()."""
    target = {k: ident.get(k) for k in ("app_id", "wm_class", "exe")}
    argv, env, cwd = command(ident, fix)  # read before the process exits
    info = d.desktop_entry(ident)
    for xid in _windows(target):
        subprocess.run(["wmctrl", "-i", "-c", xid], timeout=5)
    if d.wait(lambda: not _windows(target), close_timeout) is False:
        return {"ok": False, "message": f"{ident['wm_class']} is still open. It may be asking you something, such as "
                                        "whether to save or close several tabs. Answer it, then try again."}
    if not d.wait(lambda: not _running(ident, info), 10):
        return {"ok": False, "message": "Its windows closed, but the app is still running in the background."}
    subprocess.Popen(argv, env=env, cwd=cwd, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    xid = d.wait(lambda: next(iter(w for w in _windows(target) if not d.identity(w).get("transient")), None), open_timeout)
    if not xid:
        return {"ok": False, "message": "It didn't open a window again."}

    def visible():
        frame = d.frame_for(d.identity(xid))
        return frame is not None and sum(1 for _ in zip(range(20), d.walk(frame))) >= 10
    if not d.wait(visible, 10, step=0.5):
        return {"ok": False, "message": "It restarted, but Surgeon still can't see inside it.", "xid": xid}
    return {"ok": True, "message": "Restarted. Surgeon can see inside it now.", "xid": hex(int(xid, 16))}
