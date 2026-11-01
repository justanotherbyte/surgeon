import copy
import json
import unittest
from pathlib import Path

from surgeon import desktop as d
from surgeon import manifest as m

EOG = {"xid": "0x3a00007", "app_id": "org.gnome.eog", "bus_name": ":1.1", "app_path": "/org/gnome/eog",
       "window_path": "/org/gnome/eog/window/1", "pid": 1, "exe": "/usr/bin/eog", "wm_class": "Eog",
       "title": "photo.jpg"}
ZOOM = json.loads((Path(__file__).parent / "manifests" / "eog-zoom.json").read_text())


def with_step(step):
    man = copy.deepcopy(ZOOM)
    man["steps"] = [step]
    return man


class CheckTest(unittest.TestCase):
    def test_valid_manifest_passes(self):
        m.check(ZOOM, EOG)

    def test_unknown_step_type_rejected(self):
        with self.assertRaisesRegex(d.SurgeonError, "schema"):
            m.check(with_step({"type": "shell", "label": "x", "reversible": True, "cmd": "rm -rf ~"}), EOG)

    def test_cli_must_be_the_apps_binary(self):
        step = {"type": "cli", "label": "x", "reversible": True, "argv": ["bash", "-c", "rm -rf ~"]}
        with self.assertRaisesRegex(d.SurgeonError, "own binary"):
            m.check(with_step(step), EOG)
        m.check(with_step({**step, "argv": ["eog", "--fullscreen"]}), EOG)
        with self.assertRaisesRegex(d.SurgeonError, "own binary"):
            m.check(with_step({**step, "argv": ["/tmp/eog"]}), EOG)

    def test_denylist_blocks_actions_and_labels(self):
        with self.assertRaisesRegex(d.SurgeonError, "blocked"):
            m.check(with_step({"type": "gtk_action", "label": "x", "reversible": False, "name": "win.move-trash", "param": None}), EOG)
        with self.assertRaisesRegex(d.SurgeonError, "blocked"):
            m.check(with_step({"type": "activate", "label": "x", "reversible": False, "role": "menu item",
                               "name": "Clear List", "within": None}), EOG)
        undo_quit = copy.deepcopy(ZOOM)
        undo_quit["undo"] = [{"type": "frame_action", "label": "x", "reversible": True, "name": "app.quit"}]
        with self.assertRaisesRegex(d.SurgeonError, "blocked"):
            m.check(undo_quit, EOG)


class MatcherTest(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(d.norm("_Stopwatch"), "stopwatch")
        self.assertEqual(d.norm("Save Ctrl+S"), "save")
        self.assertEqual(d.norm("Toggle Primary Side Bar (Ctrl+B)"), "toggle primary side bar")
        self.assertEqual(d.norm("Export as PDF..."), "export as pdf")
        self.assertEqual(d.norm("Zoom In\nShortcut key: Ctrl++"), "zoom in")


class HashAndPlaceholderTest(unittest.TestCase):
    def test_hash_ignores_claims(self):
        claimed = {**ZOOM, "verified": True, "routes_tried": []}
        self.assertEqual(m.manifest_hash(ZOOM), m.manifest_hash(claimed))
        self.assertNotEqual(m.manifest_hash(ZOOM), m.manifest_hash(with_step(ZOOM["undo"][0])))

    def test_placeholders_fixed_per_run(self):
        ident = {**EOG, "title": "report.odt — LibreOffice Writer", "run_started": 0}
        self.assertTrue(m.fill("{documents}/{stem}-{time}.pdf", ident).endswith("/report-" + m.placeholders(ident)["{time}"] + ".pdf"))
        self.assertEqual(m.fill("{time}", ident), m.fill("{time}", ident))


if __name__ == "__main__":
    unittest.main()
