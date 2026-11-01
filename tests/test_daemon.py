import unittest
from unittest import mock

from surgeon import daemon
from surgeon import desktop as d


class Node:
    def __init__(self, role, name):
        self.role, self.name = role, name

    def get_role_name(self):
        return self.role

    def get_name(self):
        return self.name


class ToolsTest(unittest.TestCase):
    def test_lists_enabled_actions_and_named_controls_without_blocked_ones(self):
        ident = {"exe": "/usr/bin/eog", "wm_class": "eog", "pid": 1}
        actions = {"win.zoom-in": {"enabled": True}, "win.zoom-out": {"enabled": False},
                   "app.quit": {"enabled": True}, "win.goto-3-4": {"enabled": True}}
        nodes = [Node("push button", "_Zoom In"), Node("push button", "Zoom in"), Node("push button", "Quit"),
                 Node("label", "Hello"), Node("menu item", "Print…")]
        with mock.patch.object(d, "identity", return_value=ident), \
                mock.patch.object(d, "gtk_actions", return_value=actions), \
                mock.patch.object(d, "frame_for", return_value=object()), \
                mock.patch.object(d, "action_names", return_value=[]), \
                mock.patch.object(d, "walk", return_value=((n, ()) for n in nodes)), \
                mock.patch.object(d, "dbus_names", return_value=[]):
            t = daemon.tools("0x1")
        self.assertEqual(t["actions"], ["zoom-in"])
        self.assertEqual(t["controls"], ["Zoom In", "Print…"])
        self.assertEqual(t["commands"], ["eog"])
