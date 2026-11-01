import ast
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from surgeon import install
from tests.test_manifest import EOG, ZOOM


class FakeGsettings:
    def __init__(self, paths):
        self.store = {(install.KEYS, "custom-keybindings"): str(paths)}

    def __call__(self, op, schema, key, value=None):
        if op == "get":
            return self.store.get((schema, key), "''" if key != "custom-keybindings" else "@as []")
        if op == "set":
            self.store[(schema, key)] = value if key == "custom-keybindings" else repr(value)
        if op == "reset":
            self.store.pop((schema, key), None)
        return ""


class InstallTest(unittest.TestCase):
    def test_install_then_uninstall_restores_keybindings(self):
        original = [install.BASE + "custom0/"]
        fake = FakeGsettings(original)
        fake.store[(f"{install.ITEM}:{original[0]}", "binding")] = "'<Control><Alt>1'"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(install, "gsettings", fake), \
                mock.patch.object(install, "EXT_DIR", Path(tmp)):
            r = install.install(ZOOM, EOG, "Zoom to 200%", "make it bigger")
            self.assertEqual(r["accelerator"], "Ctrl+Alt+2")  # Ctrl+Alt+1 was taken
            self.assertEqual(len(ast.literal_eval(fake.store[(install.KEYS, "custom-keybindings")])), 2)
            self.assertEqual(install.load(r["id"])["target"]["wm_class"], "Eog")
            install.uninstall(r["id"])
            self.assertEqual(ast.literal_eval(fake.store[(install.KEYS, "custom-keybindings")]), original)
            self.assertEqual(install.extensions(), [])


if __name__ == "__main__":
    unittest.main()
