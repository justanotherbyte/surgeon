"""Codex's only way into the desktop. Seven tools scoped to one window, over MCP stdio JSON-RPC.

python3 -m surgeon.mcp --xid 0x3a00007 --job <id>
Every call is appended to jobs/<id>/inspection.jsonl, which Codex's read-only sandbox can't write.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
import time

from gi.repository import GLib

from . import desktop as d
from . import manifest as m
from . import relaunch
from .desktop import SurgeonError

MAX_TESTS = 5  # keep in step with MAX_TESTS in app/job.ts


class Tools:
    def __init__(self, xid, job):
        self.ident = d.identity(xid)
        self.log_path = m.DATA / "jobs" / job / "inspection.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.tests = 0

    def log(self, entry):
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"ts": time.time(), **entry}) + "\n")

    def _ident(self):
        self.ident = m._refresh(self.ident)
        return self.ident

    def _roots(self):
        ident = self._ident()
        frame = d.frame_for(ident)
        others = [w for _, _, w in d.windows(ident) if w != frame]
        return ([frame] if frame else []) + others

    def describe_app(self):
        ident = self._ident()
        app, frame = d.app_for(ident), d.frame_for(ident)
        actions = {k: v for k, v in d.gtk_actions(ident).items()
                   if not m.DENY_ACTIONS.match(k.split(".", 1)[1]) and not re.search(r"-\d+-\d+$", k)}
        nodes = sum(1 for _ in d.walk(frame)) if frame else 0
        toolkit = app.get_toolkit_name() if app else None
        return {
            "app_id": ident["app_id"], "wm_class": ident["wm_class"], "title": ident["title"],
            "binary": ident["exe"], "cli_argv0_allowed": sorted(m.allowed_binaries(ident)),
            "toolkit": toolkit,
            "accessible": frame is not None,
            "tree_nodes": nodes,
            "needs_relaunch": relaunch.plan(ident, toolkit, nodes, frame is not None) is not None,
            "windows": [{"role": r, "name": n} for r, n, _ in d.windows(ident)],
            "gtk_actions": [{"name": k, **v} for k, v in sorted(actions.items())],
            "dbus_names": d.dbus_names(ident),
            "frame_actions": [a for a in (d.action_names(frame) if frame else [])
                              if not m.DENY_ACTIONS.match(a.split(".", 1)[-1])],
            "placeholders": sorted(m.placeholders(ident)),
            "document_path": d.document_path(ident),  # null when the app was not opened on a file
            "launcher": (lambda i: i and i.get_id())(d.desktop_entry(ident)),  # for launch steps with app null
        }

    def find_elements(self, query, roles=None):
        want, out, seen = d.norm(query), [], set()
        for root in self._roots():
            for node, ancestors in d.walk(root):
                role = node.get_role_name()
                if roles and role not in roles or not roles and role not in d.INTERACTIVE:
                    continue
                labels = d.labels(node)
                if want and not any(want in label for label in labels):
                    continue
                info = d.describe_node(node, ancestors)
                key = (info["role"], info["name"], tuple(info["within"]))
                if key in seen:
                    continue
                seen.add(key)
                out.append(info)
                if len(out) >= 40:
                    return out
        return out

    def get_tree(self, depth=6):
        lines = []
        for root in self._roots():
            for node, ancestors in d.walk(root):
                level = len(ancestors)
                if level > depth or len(lines) >= 400:
                    continue
                acts = d.action_names(node)
                name = node.get_name() or ""
                lines.append(f"{'  ' * level}{node.get_role_name()} {name!r}" + (f" {acts}" if acts else ""))
        return "\n".join(lines) + ("\n[truncated at 400 lines]" if len(lines) >= 400 else "")

    def inspect_element(self, role, name, within=None):
        node = m._find_one(self._ident(), role, name, within)
        return {**d.describe_node(node), "description": node.get_description() or "",
                "extents": d.extents(node)}

    def list_apps(self, query):
        return d.list_apps(query)

    def capture_window(self):
        """A fresh screenshot of the target window only. Never the whole screen."""
        png = subprocess.run(["import", "-window", self._ident()["xid"], "-resize", "1280x1280>", "png:-"],
                             capture_output=True, timeout=10).stdout
        if not png:
            raise SurgeonError("Couldn't capture the window. It may be minimized.")
        return {"__image__": base64.b64encode(png).decode()}

    def test_manifest(self, manifest):
        if self.tests >= MAX_TESTS:
            return {"passed": False, "error": f"Only {MAX_TESTS} tests per request. Return the closest version that passed a test, or feasible=false with what you learned."}
        self.tests += 1
        try:
            result = m.run(manifest, self._ident(), test=True)
            buttons = (manifest.get("subapp") or {}).get("buttons") or []
            if result["ok"] and buttons:  # a toolbar passes only if every button runs and undoes
                result["buttons"] = []
                for i, button in enumerate(buttons):
                    r = m.run(m.button_manifest(manifest, i), self._ident(), test=True)
                    result["buttons"].append({"label": button["label"], "ok": r["ok"], "error": r["error"], "undo": r["undo"]})
                    if not r["ok"]:
                        result.update(ok=False, error=f"Button {button['label']!r}: {r['error']}")
                        break
                    if r["undo"] and not r["undo"]["ok"]:
                        result.update(ok=False, error=f"Button {button['label']!r} undo failed: {r['undo']['error']}")
                        break
        except SurgeonError as e:
            result = {"ok": False, "error": str(e), "hash": m.manifest_hash(manifest)}
        self.log({"tool": "test_manifest", "hash": result["hash"], "passed": result["ok"], "error": result.get("error")})
        # A script's output goes to the user's panel, never to the model: Codex sees only its shape.
        result["panels"] = [{"title": p["title"], "rows": len(p["rows"]) if p["rows"] is not None else None,
                             "text_chars": len(p["text"] or "")} for p in result.get("panels", [])]
        return {"passed": result["ok"], "attempt": self.tests, **{k: v for k, v in result.items() if k != "ok"}}


SPECS = {
    "describe_app": ("Identity of the target app: GTK actions with enabled state and parameter type, GTK 4 frame "
                     "actions, other D-Bus names it owns (rank 3), the binary cli steps may use, open windows, "
                     "whether it needs a relaunch to be visible.",
                     {"type": "object", "properties": {}}),
    "find_elements": ("Search the target app's showing controls by label substring (name, labelled-by, description). "
                      "Returns role, name, actions, states and containing windows or menus.",
                      {"type": "object", "properties": {"query": {"type": "string"},
                                                        "roles": {"type": "array", "items": {"type": "string"}}},
                       "required": ["query"]}),
    "get_tree": ("Bounded, pruned accessibility tree of the target window and its dialogs. Document text is removed.",
                 {"type": "object", "properties": {"depth": {"type": "integer"}}}),
    "inspect_element": ("States, actions, description and screen extents of one control.",
                        {"type": "object", "properties": {"role": {"type": "string"}, "name": {"type": "string"},
                                                          "within": {"type": "string"}},
                         "required": ["role", "name"]}),
    "list_apps": ("Installed apps whose name, desktop id or keywords contain query, for launch steps. "
                  "Returns id, name and window class.",
                  {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    "capture_window": ("A fresh screenshot of the target window (only that window, never the whole screen). Use it "
                       "to see the app's state after a test, or to plan a watch trigger or a script that reads pixels.",
                       {"type": "object", "properties": {}}),
    "test_manifest": ("Run a manifest against the real app with Surgeon's executor, check its verification, then run "
                      "its undo steps. Pass the full manifest object. At most 5 calls per request.",
                      {"type": "object", "properties": {"manifest": {"type": "object"}}, "required": ["manifest"]}),
}


def summarize(name, args, res):
    """What the sub-app install gate needs to check a claimed route outcome."""
    if name == "describe_app":
        return {"gtk_actions": len(res["gtk_actions"]), "frame_actions": len(res["frame_actions"]),
                "dbus_names": len(res["dbus_names"]), "needs_relaunch": res["needs_relaunch"]}
    if name == "find_elements":
        return {"query": args.get("query", ""), "matches": len(res)}
    return None


def serve(tools):
    def reply(rid, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": rid, **({"error": error} if error else {"result": result})}
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        if rid is None:
            continue
        if method == "initialize":
            reply(rid, {"protocolVersion": req["params"].get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}}, "serverInfo": {"name": "surgeon", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(rid, {"tools": [{"name": k, "description": desc, "inputSchema": schema}
                                  for k, (desc, schema) in SPECS.items()]})
        elif method == "tools/call":
            name, args = req["params"]["name"], req["params"].get("arguments") or {}
            try:
                if name not in SPECS:
                    raise SurgeonError(f"Unknown tool {name!r}.")
                res = getattr(tools, name)(**args)
                if name != "test_manifest":
                    tools.log({"tool": name, "args": args, "ok": True, "summary": summarize(name, args, res)})
                if isinstance(res, dict) and "__image__" in res:
                    content = [{"type": "image", "data": res["__image__"], "mimeType": "image/png"}]
                else:
                    content = [{"type": "text", "text": res if isinstance(res, str) else json.dumps(res)}]
                reply(rid, {"content": content})
            except (SurgeonError, GLib.Error, TypeError) as e:
                tools.log({"tool": name, "args": args, "ok": False, "error": str(e)})
                reply(rid, {"content": [{"type": "text", "text": f"error: {getattr(e, 'message', None) or e}"}],
                            "isError": True})
        elif method == "ping":
            reply(rid, {})
        else:
            reply(rid, error={"code": -32601, "message": "method not found"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xid", required=True)
    ap.add_argument("--job", required=True)
    a = ap.parse_args()
    serve(Tools(a.xid, a.job))
