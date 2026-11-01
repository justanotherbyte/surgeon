"""Real desktop test: needs an X11 session. Run with SURGEON_DESKTOP_TESTS=1 from outside T3 Code."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from surgeon import desktop as d
from surgeon import manifest as m


@unittest.skipUnless(os.environ.get("SURGEON_DESKTOP_TESTS"), "set SURGEON_DESKTOP_TESTS=1 to drive a real app")
class ImageViewerTest(unittest.TestCase):
    def test_zoom_set_flips_zoom_fit(self):
        tmp = tempfile.mkdtemp()
        image = next(Path("/usr/share/backgrounds").glob("*.jpg"))
        env = {k: v for k, v in os.environ.items() if k not in m.CLEAN_ENV}
        env.update(GSETTINGS_BACKEND="memory", XDG_CONFIG_HOME=tmp, XDG_DATA_HOME=tmp, XDG_STATE_HOME=tmp)
        proc = subprocess.Popen(["eog", "--new-instance", str(image)], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            xid = d.wait(lambda: next((x for x in d.client_xids()
                                       if d.xprop(x, "_NET_WM_PID").get("_NET_WM_PID") == proc.pid), None), 10)
            self.assertIsNotNone(xid, "Image Viewer window never appeared")
            time.sleep(1)
            manifest = json.loads((Path(__file__).parent / "manifests" / "eog-zoom.json").read_text())
            result = m.run(manifest, d.identity(xid), test=True)
            self.assertTrue(result["ok"], result["error"])
            self.assertTrue(result["undo"]["ok"])
        finally:
            proc.terminate()


if __name__ == "__main__":
    unittest.main()
