import copy
import json
import os
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from surgeon import manifest as m
from surgeon import subapps
from tests.test_manifest import EOG

SCRIPT = "import json, sys\nprint(json.dumps(sys.argv[1:]))\n"
SUB = {
    "feasible": True, "summary": "List the largest files", "verification": [], "undo": [], "routes_tried": [],
    "verified": True,
    "steps": [{"type": "script", "label": "Find them", "reversible": True, "file": "big.py", "args": ["{window.title}"], "outputs_to": None},
              {"type": "panel", "label": "Show them", "reversible": True, "title": "Largest", "source": "big.py"}],
    "subapp": {"trigger": {"type": "hotkey", "accelerator": "Ctrl+Alt+L", "path": None, "watch": None, "title": None}, "reads": ["file sizes"], "buttons": [],
               "exhausted": [{"rank": r, "outcome": "unsuitable", "reason": "no"} for r in range(1, 6)],
               "scripts": [{"file": "big.py", "content": SCRIPT}]},
}


TOOLBAR = {
    "feasible": True, "summary": "Image toolbar", "verification": [], "undo": [], "routes_tried": [], "verified": True,
    "steps": [],
    "subapp": {"trigger": {"type": "toolbar", "accelerator": None, "path": None, "watch": None, "title": None}, "reads": [], "exhausted": [],
               "scripts": [], "buttons": [{"label": "Rotate", "steps": [
                   {"type": "gtk_action", "label": "Rotate", "reversible": True, "name": "win.rotate-90", "param": None}],
                   "undo": [{"type": "gtk_action", "label": "Back", "reversible": True, "name": "win.rotate-270", "param": None}]}]},
}


def log_for(manifest, describe=None, finds=(("size", 3),), tested=True):
    entries = [{"tool": "describe_app", "ok": True, "summary": describe or
                {"gtk_actions": 5, "frame_actions": 0, "dbus_names": 0, "needs_relaunch": False}}]
    entries += [{"tool": "find_elements", "ok": True, "summary": {"query": q, "matches": n}} for q, n in finds]
    if tested:
        entries.append({"tool": "test_manifest", "hash": m.manifest_hash(manifest), "passed": True})
    return entries


class GateTest(unittest.TestCase):
    def reasons(self, manifest, log):
        with mock.patch.object(subapps, "_log", return_value=log):
            return subapps.gate(manifest, "job", EOG)

    def test_good_subapp_passes(self):
        self.assertEqual(self.reasons(SUB, log_for(SUB)), [])

    def test_missing_rank(self):
        man = copy.deepcopy(SUB)
        man["subapp"]["exhausted"].pop()
        self.assertTrue(any("rank 5" in r for r in self.reasons(man, log_for(man))))

    def test_route_never_inspected(self):
        log = [e for e in log_for(SUB) if e["tool"] != "find_elements"]
        self.assertTrue(any("find_elements" in r for r in self.reasons(SUB, log)))

    def test_unavailable_must_match_the_log(self):
        man = copy.deepcopy(SUB)
        man["subapp"]["exhausted"][0]["outcome"] = "unavailable"  # but describe_app found 5 GTK actions
        self.assertTrue(any("unavailable" in r for r in self.reasons(man, log_for(man))))
        man["subapp"]["exhausted"][0]["rank"], man["subapp"]["exhausted"][1]["rank"] = 2, 1
        self.assertEqual(self.reasons(man, log_for(man)), [])  # rank 2 really had 0 frame actions

    def test_no_match_needs_an_empty_search(self):
        man = copy.deepcopy(SUB)
        man["subapp"]["exhausted"][4]["outcome"] = "no_match"
        self.assertTrue(any("no_match" in r for r in self.reasons(man, log_for(man))))
        self.assertEqual(self.reasons(man, log_for(man, finds=(("size", 3), ("largest", 0)))), [])

    def test_rewording_descriptions_after_the_test_is_fine(self):
        reworded = copy.deepcopy(SUB)
        reworded["subapp"]["reads"] = ["file names and sizes"]
        reworded["subapp"]["exhausted"][0]["reason"] = "None of the 46 actions lists files."
        self.assertEqual(self.reasons(reworded, log_for(SUB)), [])

    def test_untested_or_changed_subapp_refused(self):
        self.assertTrue(any("test" in r for r in self.reasons(SUB, log_for(SUB, tested=False))))
        changed = copy.deepcopy(SUB)
        changed["subapp"]["scripts"][0]["content"] += "import os\n"
        self.assertTrue(any("test" in r for r in self.reasons(changed, log_for(SUB))))

    def test_electron_without_flag_refused(self):
        log = log_for(SUB, describe={"gtk_actions": 0, "frame_actions": 0, "dbus_names": 0, "needs_relaunch": True})
        self.assertTrue(any("restart" in r for r in self.reasons(SUB, log)))

    def test_irreversible_step_refused_only_when_nobody_acts(self):
        man = copy.deepcopy(SUB)
        man["steps"][0]["reversible"] = False
        self.assertEqual(self.reasons(man, log_for(man)), [])  # a hotkey press is the user's own action
        man["subapp"]["trigger"] = {"type": "app_opened", "accelerator": None, "path": None, "watch": None, "title": None}
        self.assertTrue(any("reversible" in r for r in self.reasons(man, log_for(man))))

    def test_toolbar_without_script_needs_no_route_proof(self):
        man = copy.deepcopy(TOOLBAR)
        self.assertEqual(self.reasons(man, log_for(man, finds=())), [])
        man["steps"] = copy.deepcopy(TOOLBAR["subapp"]["buttons"][0]["steps"])
        self.assertTrue(any("top-level steps" in r for r in self.reasons(man, log_for(man))))
        man = copy.deepcopy(TOOLBAR)
        man["subapp"]["buttons"] *= 7
        self.assertTrue(any("1 to 6" in r for r in self.reasons(man, log_for(man))))

    def test_button_steps_hit_the_denylist(self):
        man = copy.deepcopy(TOOLBAR)
        man["subapp"]["buttons"][0]["steps"][0]["name"] = "win.move-trash"
        self.assertTrue(any("blocked" in r for r in self.reasons(man, log_for(man))))

    def test_file_saved_needs_a_path(self):
        man = copy.deepcopy(SUB)
        man["subapp"]["trigger"] = {"type": "file_saved", "accelerator": None, "path": None, "watch": None, "title": None}
        self.assertTrue(any("path" in r for r in self.reasons(man, log_for(man))))

    def test_script_steps_only_in_subapps(self):
        man = copy.deepcopy(SUB)
        man["subapp"] = None
        with self.assertRaisesRegex(m.SurgeonError, "only allowed in a sub-app"):
            m.check(man, EOG)


class SaveTriggerTest(unittest.TestCase):
    def test_debounce_and_self_trigger_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.xopp"
            path.write_text("v1")
            w = subapps.Watcher(lambda e: None)
            key = ("sub", "0x1")
            rec = {"id": "sub", "manifest": {"subapp": {"trigger": {"type": "file_saved", "path": str(path)}}}}
            w.armed[key], w.idents["0x1"] = rec, {**EOG, "xid": "0x1"}
            w.saves[key] = {"path": None, "mtime": None, "pending": None, "quiet_until": 0}
            fired = []
            w.fire = lambda *k: fired.append(k)
            w.check_saves()  # resolves the path and its current mtime
            os.utime(path, (1, 1000))
            w.check_saves()  # changed once: may still be mid-save
            self.assertEqual(fired, [])
            w.check_saves()  # unchanged for a tick: the save is done
            self.assertEqual(fired, [key])
            w.saves[key]["quiet_until"] = time.time() + 5  # our own run just ended
            os.utime(path, (1, 2000))
            w.check_saves()
            w.check_saves()
            self.assertEqual(fired, [key])


class DocumentPathTest(unittest.TestCase):
    def test_resolves_relative_argument_named_in_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "notes.xopp").write_text("x")
            ident = {**EOG, "pid": os.getpid(), "title": "notes.xopp - Xournal++"}
            with mock.patch("builtins.open", mock.mock_open(read_data=b"xournalpp\0--flag\0notes.xopp\0")), \
                    mock.patch("os.readlink", return_value=tmp):
                self.assertEqual(m.d.document_path(ident), os.path.join(tmp, "notes.xopp"))
            with mock.patch("builtins.open", mock.mock_open(read_data=b"xournalpp\0other.xopp\0")), \
                    mock.patch("os.readlink", return_value=tmp):
                self.assertIsNone(m.d.document_path(ident))


class ScriptTest(unittest.TestCase):
    def test_title_with_spaces_and_semicolon_stays_one_arg(self):
        ident = {**EOG, "title": "my photos; rm -rf ~", "run_started": 0}
        ctx = {"scripts": {"big.py": SCRIPT}, "outputs": {}, "panels": [], "workdir": tempfile.mkdtemp()}
        with mock.patch.object(m.d, "frame_for", return_value=None):
            m.do_step(SUB["steps"][0], ident, ctx)
            m.do_step(SUB["steps"][1], ident, ctx)
        self.assertEqual(ctx["panels"][0]["rows"], ["my photos; rm -rf ~"])

    def test_sandbox_blocks_escapes_and_allows_reads(self):
        bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus").split("path=")[-1].split(",")[0]
        probe = f"""
import json, os, socket
def t(f):
    try:
        f(); return "allowed"
    except Exception as e:
        return type(e).__name__
print(json.dumps({{
    "bus": t(lambda: socket.socket(socket.AF_UNIX).connect({bus!r})),
    "tcp": t(lambda: socket.create_connection(("127.0.0.1", 9), timeout=1)),
    "write_home": t(lambda: open(os.path.expanduser("~/.surgeon-sandbox-test"), "w")),
    "kill": t(lambda: os.kill(os.getppid(), 0)),
    "read_home": t(lambda: os.listdir(os.path.expanduser("~"))),
}}))
"""
        with tempfile.TemporaryDirectory() as tmp:
            out = json.loads(m.run_script(probe, [], tmp))
        self.assertEqual(out, {"bus": "PermissionError", "tcp": "PermissionError", "write_home": "PermissionError",
                               "kill": "PermissionError", "read_home": "allowed"})
        self.assertFalse(Path("~/.surgeon-sandbox-test").expanduser().exists())

    def test_failing_script_raises(self):
        with self.assertRaisesRegex(m.SurgeonError, "exited 1"):
            m.run_script("raise SystemExit(1)", [], tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()


class WatchTest(unittest.TestCase):
    def feed(self, mode, frames):
        st = {"last": None, "changing": False, "stable": 0}
        return [subapps.watch_decide(st, bytes([v]) * 1024, mode) for v in frames]

    def test_changed_fires_on_each_change(self):
        self.assertEqual(self.feed("changed", [10, 10, 80, 80, 81, 20]), [False, False, True, False, False, True])

    def test_settled_fires_once_after_changes_stop(self):
        self.assertEqual(self.feed("settled", [10, 10, 50, 90, 90, 90, 90]),
                         [False, False, False, False, False, True, False])

    def test_a_line_of_text_counts_but_a_cursor_blink_does_not(self):
        st = {"last": None, "changing": False, "stable": 0}
        idle = bytes(1024)
        line = bytes([200] * 4) + bytes(1020)  # 4 thumbnail pixels changed sharply
        blink = bytes([200] * 2) + bytes(1020)
        subapps.watch_decide(st, idle, "changed")
        self.assertTrue(subapps.watch_decide(st, line, "changed"))
        subapps.watch_decide(st, idle, "changed")
        self.assertFalse(subapps.watch_decide(st, blink, "changed"))

    def test_missing_sample_never_fires(self):
        st = {"last": bytes(1024), "changing": True, "stable": 1}
        self.assertFalse(subapps.watch_decide(st, None, "settled"))


class TestManifestPrivacyTest(unittest.TestCase):
    def test_codex_never_sees_script_output(self):
        from surgeon import mcp
        panel = {"title": "Screen text", "rows": ["my bank balance", "a private message"], "text": None}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(m, "DATA", Path(tmp)), \
                mock.patch.object(mcp.d, "identity", return_value=EOG), \
                mock.patch.object(mcp.m, "_refresh", side_effect=lambda i: i), \
                mock.patch.object(mcp.m, "run", return_value={"ok": True, "steps": [], "checks": [], "undo": None,
                                                              "error": None, "hash": "h", "panels": [panel]}):
            out = mcp.Tools("0x1", "job").test_manifest(SUB)
        self.assertEqual(out["panels"], [{"title": "Screen text", "rows": 2, "text_chars": 0}])
        self.assertNotIn("bank", json.dumps(out))


class TitleTriggerTest(unittest.TestCase):
    def test_fires_once_per_visit_after_the_dwell(self):
        st = {"since": None, "fired": False}
        seen = [subapps.title_decide(st, match, t, 10) for t, match in
                [(0, True), (5, True), (10, True), (15, True), (16, False), (20, True), (31, True)]]
        self.assertEqual(seen, [False, False, True, False, False, False, True])

    def test_gate_checks_the_pattern(self):
        man = copy.deepcopy(TOOLBAR)
        man["subapp"]["buttons"] = []
        man["steps"] = TOOLBAR["subapp"]["buttons"][0]["steps"]
        man["subapp"]["trigger"] = {"type": "title", "accelerator": None, "path": None, "watch": None,
                                    "title": {"pattern": "/ X(", "seconds": 10}}
        with mock.patch.object(subapps, "_log", return_value=log_for(man)):
            self.assertTrue(any("regular expression" in r for r in subapps.gate(man, "job", EOG)))


class LaunchAndFilesTest(unittest.TestCase):
    def test_deliver_never_overwrites_and_stays_out_of_hidden_folders(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as dest, tempfile.TemporaryDirectory() as work:
            if Path(dest).name.startswith("."):
                self.skipTest("temp dir is hidden")
            (Path(work) / "out").mkdir()
            (Path(work) / "out" / "photo-inverted.png").write_text("new")
            (Path(dest) / "photo-inverted.png").write_text("keep me")
            created = m.deliver(work, dest)
            self.assertEqual(created, [str(Path(dest) / "photo-inverted-1.png")])
            self.assertEqual((Path(dest) / "photo-inverted.png").read_text(), "keep me")
            for bad in ("~/.config/autostart", "/tmp", "~/../"):
                with self.assertRaisesRegex(m.SurgeonError, "visible folder"):
                    m.deliver(work, os.path.expanduser(bad))

    def test_launch_refuses_unsafe_arguments_and_terminals(self):
        ctx = {"launched": [], "created": []}
        info = mock.Mock(get_categories=lambda: "Graphics;", get_name=lambda: "Image Viewer")
        step = {"type": "launch", "label": "Open", "reversible": True, "app": "org.gnome.eog", "args": ["-e", "sh"]}
        with mock.patch.object(m.d, "app_by_id", return_value=info), mock.patch.object(m.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(m.SurgeonError, "Launch argument"):
                m.do_step(step, {**EOG, "run_started": 0}, ctx)
            info.get_categories = lambda: "System;TerminalEmulator;"
            with self.assertRaisesRegex(m.SurgeonError, "terminal"):
                m.do_step({**step, "args": []}, {**EOG, "run_started": 0}, ctx)
            popen.assert_not_called()

    def test_launch_argv_drops_field_codes(self):
        info = mock.Mock(get_commandline=lambda: "/usr/bin/flatpak run --file-forwarding app.zen_browser.zen @@u %u @@")
        self.assertEqual(m.d.launch_argv(info, ["--new-window"]),
                         ["/usr/bin/flatpak", "run", "app.zen_browser.zen", "--new-window"])


class RelaunchTest(unittest.TestCase):
    def test_electron_process_title_and_environ_rewrites(self):
        from surgeon import relaunch
        files = {"/proc/7/cmdline": b"/usr/share/typora/Typora /tmp/notes.md", "/proc/7/environ": b"p/notes.md\0"}
        with mock.patch("builtins.open", lambda path, mode="r": __import__("io").BytesIO(files[path])), \
                mock.patch("os.readlink", return_value="/home/u"), \
                mock.patch.dict(os.environ, {"DISPLAY": ":1", "PATH": "/usr/bin", "HOME": "/home/u", "NO_AT_BRIDGE": "1"}, clear=True):
            argv, env, cwd = relaunch.command({"pid": 7}, relaunch.FIXES["electron"])
        self.assertEqual(argv, ["/usr/share/typora/Typora", "/tmp/notes.md", "--force-renderer-accessibility"])
        self.assertEqual(env, {"DISPLAY": ":1", "PATH": "/usr/bin", "HOME": "/home/u"})  # session env, T3's vars dropped

    def test_flatpak_gets_env_through_flatpak_run(self):
        from surgeon import relaunch
        info = mock.Mock(get_commandline=lambda: "/usr/bin/flatpak run --file-forwarding app.zen_browser.zen @@u %u @@")
        with mock.patch.object(relaunch.d, "desktop_entry", return_value=info):
            argv, _, _ = relaunch.command({"pid": None, "wm_class": "zen"}, relaunch.FIXES["gecko"])
        self.assertEqual(argv, ["/usr/bin/flatpak", "run", "--env=GNOME_ACCESSIBILITY=1", "app.zen_browser.zen"])


AGENT_STEP = {"type": "agent", "label": "Fix it", "reversible": False, "goal": "Open the file the error names",
              "max_actions": 3, "file": "agent.txt"}
AGENT = {**copy.deepcopy(SUB), "steps": [AGENT_STEP, {"type": "notify", "label": "Say what happened",
                                                       "reversible": True, "title": "Done", "source": "agent.txt"}]}
AGENT["subapp"].update(scripts=[], exhausted=[])


class AgentStepTest(unittest.TestCase):
    def test_check_rules(self):
        m.check(AGENT, EOG)  # notify may show the agent's message
        for bad in ({"reversible": True}, {"max_actions": 11}):
            man = copy.deepcopy(AGENT)
            man["steps"][0].update(bad)
            self.assertRaises(m.SurgeonError, m.check, man, EOG)
        plain = {**copy.deepcopy(AGENT), "subapp": None, "steps": [AGENT_STEP]}
        self.assertRaises(m.SurgeonError, m.check, plain, EOG)
        undo = {**copy.deepcopy(AGENT), "undo": [AGENT_STEP]}
        self.assertRaises(m.SurgeonError, m.check, undo, EOG)

    def test_agent_needs_no_route_proof(self):
        with mock.patch.object(subapps, "_log", return_value=log_for(AGENT)):
            self.assertEqual(subapps.gate(AGENT, "job", EOG), [])

    def test_run_agent_reads_the_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "node"
            for ok, want in (("true", "m"), ("false", None)):
                fake.write_text(f'#!/bin/sh\necho noise\necho \'{{"ok": {ok}, "message": "m"}}\'\n')
                fake.chmod(0o755)
                with mock.patch.dict(os.environ, {"SURGEON_NODE": str(fake)}):
                    if want:
                        self.assertEqual(m.run_agent(AGENT_STEP, {"xid": "0x1"}), want)
                    else:
                        self.assertRaises(m.SurgeonError, m.run_agent, AGENT_STEP, {"xid": "0x1"})
