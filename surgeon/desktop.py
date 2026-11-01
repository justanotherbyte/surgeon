"""Window identity, the bounded AT-SPI walker, the control matcher, and GTK/frame actions."""
import os
import re
import subprocess
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

MAX_CHILDREN = 500  # LibreOffice Calc's sheet reports 2,147,483,647 children
MAX_NODES = 20000
MAX_DEPTH = 40

# Subtrees that hold recent files or folder contents. Never walked for the model.
PRIVATE_NAMES = {"recent documents", "open recent", "recent files", "recent"}
PRIVATE_ROLES = {"file chooser"}
# Roles whose text is document, terminal or page content.
CONTENT_ROLES = {"paragraph", "terminal", "document text", "document web", "document frame",
                 "table cell", "list item", "tree item"}
INTERACTIVE = {"push button", "toggle button", "menu item", "check menu item", "radio menu item",
               "menu", "check box", "radio button", "combo box", "text", "entry", "spin button",
               "page tab", "slider", "button", "link", "toggle"}


class SurgeonError(Exception):
    """An error whose message tells Codex or the user what to do next."""


# ---------- identity ----------

def xprop(xid, *props):
    """Read X window properties. Returns {name: str | int | list[str]}."""
    out = subprocess.run(["xprop", "-id", str(xid), "-notype", *props],
                         capture_output=True, text=True, timeout=5).stdout
    result = {}
    for line in out.splitlines():
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        strings = re.findall(r'"((?:[^"\\]|\\.)*)"', value)
        if len(strings) > 1:
            result[key] = strings
        elif strings:
            result[key] = strings[0]
        elif value.strip().isdigit():
            result[key] = int(value.strip())
        else:
            result[key] = value.strip()
    return result


def active_xid():
    out = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                         capture_output=True, text=True, timeout=5).stdout
    match = re.search(r"window id # (0x[0-9a-f]+)", out)
    if not match or int(match.group(1), 16) == 0:
        raise SurgeonError("No active window. Click the app you want first.")
    return match.group(1)


def client_xids():
    out = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"],
                         capture_output=True, text=True, timeout=5).stdout
    return re.findall(r"0x[0-9a-f]+", out)


def identity(xid):
    """Who owns this window. Window properties first, because AT-SPI names and PIDs lie."""
    p = xprop(xid, "_GTK_APPLICATION_ID", "_GTK_UNIQUE_BUS_NAME", "_GTK_APPLICATION_OBJECT_PATH",
              "_GTK_WINDOW_OBJECT_PATH", "_NET_WM_PID", "WM_CLASS", "_NET_WM_NAME")
    if not p:
        raise SurgeonError(f"Window {xid} is gone.")
    pid = p.get("_NET_WM_PID") if isinstance(p.get("_NET_WM_PID"), int) else None
    exe = flatpak = None
    if pid:
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            pass
        try:
            info = open(f"/proc/{pid}/root/.flatpak-info").read()
            flatpak = re.search(r"^name=(.+)$", info, re.M).group(1)
        except (OSError, AttributeError):
            pass
    wm_class = p.get("WM_CLASS")
    return {
        "xid": hex(int(str(xid), 16)) if str(xid).startswith("0x") else hex(int(xid)),
        "app_id": p.get("_GTK_APPLICATION_ID") or flatpak,
        "bus_name": p.get("_GTK_UNIQUE_BUS_NAME"),
        "app_path": p.get("_GTK_APPLICATION_OBJECT_PATH"),
        "window_path": p.get("_GTK_WINDOW_OBJECT_PATH"),
        "pid": pid,
        "exe": exe,
        "wm_class": wm_class[-1] if isinstance(wm_class, list) else wm_class,  # class half: libreoffice-writer
        "title": p.get("_NET_WM_NAME") or "",
    }


def same_app(ident, target):
    """True if a live window identity matches a stored extension target."""
    for key in ("wm_class", "app_id"):  # LibreOffice modules share one app_id
        if target.get(key):
            return ident.get(key) == target[key]
    return bool(target.get("exe")) and ident.get("exe") == target["exe"]


# ---------- AT-SPI ----------

def _children(node):
    try:
        count = min(node.get_child_count(), MAX_CHILDREN)
    except GLib.Error:
        return
    for i in range(count):
        try:
            child = node.get_child_at_index(i)
        except GLib.Error:
            continue
        if child is not None:
            yield child


def app_for(ident):
    """The AT-SPI application for a window, re-fetched from the desktop every call."""
    desktop = Atspi.get_desktop(0)
    by_title = None
    for app in _children(desktop):
        try:
            pid = app.get_process_id()
        except GLib.Error:
            continue
        if ident["pid"] and pid == ident["pid"]:
            return app
        if by_title is None and ident["title"]:
            for win in _children(app):
                if (win.get_name() or "") == ident["title"]:
                    by_title = app  # flatpak apps report the D-Bus proxy's PID
                    break
    return by_title


def frame_for(ident):
    """The AT-SPI top-level window that matches the X window title."""
    app = app_for(ident)
    if app is None:
        return None
    wins = list(_children(app))
    for win in wins:
        if (win.get_name() or "") == ident["title"]:
            return win
    for win in wins:  # LibreOffice titles differ slightly between X and AT-SPI
        name = win.get_name() or ""
        if name and (name in ident["title"] or ident["title"] in name):
            return win
    return wins[0] if len(wins) == 1 else None


def windows(ident):
    """Top-level AT-SPI windows of the app as [(role, name, node)]."""
    app = app_for(ident)
    return [(w.get_role_name(), w.get_name() or "", w) for w in _children(app)] if app else []


def states(node):
    try:
        ss = node.get_state_set()
    except GLib.Error:
        return set()
    return {Atspi.StateType(s).value_nick for s in ss.get_states()}


def showing(node):
    return {"showing", "visible"} <= states(node)


def action_names(node):
    try:
        ai = node.get_action_iface()
        return [ai.get_action_name(i) for i in range(ai.get_n_actions())] if ai else []
    except GLib.Error:
        return []


def extents(node):
    try:
        r = node.get_extents(Atspi.CoordType.SCREEN)
        return {"x": r.x, "y": r.y, "width": r.width, "height": r.height}
    except (GLib.Error, AttributeError):
        return None


def walk(root, private=False):
    """Bounded depth-first walk yielding (node, ancestor_names), unnamed ancestors as "". private=False prunes recent files,
    file chooser listings and document content, for anything sent to the model."""
    budget = [MAX_NODES]

    def go(node, ancestors, depth, in_chooser):
        if budget[0] <= 0 or depth > MAX_DEPTH:
            return
        budget[0] -= 1
        try:
            role, name = node.get_role_name(), node.get_name() or ""
        except GLib.Error:
            return
        if not private:
            if norm(name) in PRIVATE_NAMES:
                return
            if role in CONTENT_ROLES or (in_chooser and role in {"table", "tree table", "list", "table cell"}):
                return
        yield node, ancestors
        chooser = in_chooser or role in PRIVATE_ROLES
        for child in _children(node):
            yield from go(child, ancestors + (name,), depth + 1, chooser)

    yield from go(root, (), 0, False)


# ---------- matching ----------

_SHORTCUT = re.compile(r"\s*\(?\b(?:ctrl|shift|alt|super|meta)\+\S+\)?\s*$", re.I)


def norm(label):
    """Normalize a control label: drop mnemonics, shortcut text, ellipses, trailing colons."""
    label = (label or "").split("\n")[0].replace("_", "").replace("~", "")
    label = _SHORTCUT.sub("", label)
    label = re.sub(r"(\.\.\.|…|:)$", "", label.strip())
    return " ".join(label.split()).lower()


def labels(node):
    """Every name a control goes by: its name, its labelled-by targets, its description's first line."""
    out = []
    try:
        out.append(node.get_name() or "")
        for rel in node.get_relation_set() or []:
            if rel.get_relation_type() == Atspi.RelationType.LABELLED_BY:
                out += [rel.get_target(i).get_name() or "" for i in range(rel.get_n_targets())]
        out.append((node.get_description() or "").split("\n")[0])
    except GLib.Error:
        pass
    return [norm(x) for x in out if x and norm(x)]


def role_matches(actual, wanted):
    if not wanted:
        return True
    aliases = {"button": {"push button", "button", "toggle button"}, "entry": {"text", "entry"}}
    return actual == wanted or actual in aliases.get(wanted, ())


def find_controls(root, role=None, name=None, within=None, need_showing=True):
    """Controls under root matching role and normalized name, inside an ancestor named `within`."""
    want, want_within = norm(name), norm(within)
    hits = []
    for node, ancestors in walk(root, private=True):
        if not role_matches(node.get_role_name(), role):
            continue
        if want and want not in labels(node):
            continue
        if want_within and not any(want_within == norm(a) for a in ancestors):
            continue
        if need_showing and not showing(node) and node.get_role_name() not in (
                "menu item", "check menu item", "radio menu item", "menu"):
            continue  # closed LibreOffice menus still activate, VLC's hidden duplicates must not
        hits.append(node)
    return hits


def describe_node(node, ancestors=()):
    return {
        "role": node.get_role_name(),
        "name": node.get_name() or "",
        "labels": labels(node),
        "actions": action_names(node),
        "states": sorted(states(node) & {"checked", "selected", "enabled", "sensitive", "showing",
                                         "focused", "editable", "pressed", "expanded"}),
        "within": [a for a in ancestors if a][-3:],
    }


# ---------- named actions ----------

_bus = None


def bus():
    global _bus
    if _bus is None:
        _bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    return _bus


def _action_path(ident, name):
    prefix, _, bare = name.partition(".")
    if not bare:
        prefix, bare = "win", name
    path = ident["app_path"] if prefix == "app" else ident["window_path"]
    if not (ident["bus_name"] and path):
        raise SurgeonError(f"{ident['wm_class']} exports no GTK actions on D-Bus. Use frame_action or activate.")
    return path, bare


def gtk_actions(ident):
    """{'app.x' | 'win.x': {'enabled', 'param', 'state'}} from org.gtk.Actions.DescribeAll."""
    out = {}
    for prefix, path in (("app", ident["app_path"]), ("win", ident["window_path"])):
        if not (ident["bus_name"] and path):
            continue
        try:
            res = bus().call_sync(ident["bus_name"], path, "org.gtk.Actions", "DescribeAll",
                                  None, None, 0, 3000, None).unpack()[0]
        except GLib.Error:
            continue
        for name, (enabled, param, state) in res.items():
            out[f"{prefix}.{name}"] = {"enabled": enabled, "param": param, "state": state[0] if state else None}
    return out


def gtk_state(ident, name):
    path, bare = _action_path(ident, name)
    enabled, param, state = bus().call_sync(ident["bus_name"], path, "org.gtk.Actions", "Describe",
                                            GLib.Variant("(s)", (bare,)), None, 0, 3000, None).unpack()[0]
    return enabled, param, state[0] if state else None


def gtk_activate(ident, name, param=None):
    path, bare = _action_path(ident, name)
    try:
        enabled, sig, _ = gtk_state(ident, name)
    except GLib.Error:
        raise SurgeonError(f"GTK action {name!r} does not exist. Call describe_app for the real list.")
    if not enabled:
        raise SurgeonError(f"GTK action {name!r} is disabled right now, so it would do nothing.")
    if sig and param is None:
        raise SurgeonError(f"GTK action {name!r} needs a parameter of type {sig!r}.")
    if sig == "d" and isinstance(param, int):
        param = float(param)
    params = [GLib.Variant(sig, param)] if sig else []
    bus().call_sync(ident["bus_name"], path, "org.gtk.Actions", "Activate",
                    GLib.Variant("(sava{sv})", (bare, params, {})), None, 0, 3000, None)


def frame_action(frame, name):
    names = action_names(frame)
    if name not in names:
        raise SurgeonError(f"The window has no action {name!r}. It has: {', '.join(names[:40])}")
    frame.get_action_iface().do_action(names.index(name))


def screenshot(xid, path):
    subprocess.run(["import", "-window", str(xid), str(path)], check=True, timeout=10,
                   capture_output=True)
    return path


def wait(predicate, timeout, step=0.2):
    end = time.monotonic() + timeout
    while True:
        result = predicate()
        if result or time.monotonic() >= end:
            return result
        time.sleep(step)
