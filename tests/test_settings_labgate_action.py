import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_stubs():
    pass


class SettingsLabGateActionTests(unittest.TestCase):
    def setUp(self):
        _install_stubs()
        if "labgate_config" in sys.modules:
            del sys.modules["labgate_config"]
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.settings = importlib.import_module("labgate_config")
        self.settings.app_paths.find_external_path = lambda *parts: (
            str(Path(os.getcwd(), *parts)) if Path(os.getcwd(), *parts).exists() else None
        )
        self.settings.app_paths.get_preferred_external_path = lambda *parts: str(Path(os.getcwd(), *parts))

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_load_labgate_action_setting_defaults(self):
        self.assertEqual(
            self.settings.load_labgate_action_setting(),
            {
                "outgoing_folder": "",
                "outgoing_filename": "pat.gdt",
                "incoming_folder": "",
                "incoming_filename_filter": "*.gdt",
            },
        )

    def test_save_and_load_labgate_action_setting_roundtrip(self):
        ok = self.settings.save_labgate_action_setting(
            {
                "outgoing_folder": r"C:\out",
                "outgoing_filename": "pat.gdt",
                "incoming_folder": r"C:\in",
                "incoming_filename_filter": "IN*.gdt",
            }
        )
        self.assertTrue(ok)
        cfg_text = Path("labgate_action.ini").read_text(encoding="utf-8")
        self.assertIn("[LabGateAction]", cfg_text)
        self.assertEqual(
            self.settings.load_labgate_action_setting(),
            {
                "outgoing_folder": r"C:\out",
                "outgoing_filename": "pat.gdt",
                "incoming_folder": r"C:\in",
                "incoming_filename_filter": "IN*.gdt",
            },
        )

    def test_load_labgate_action_setting_falls_back_to_main_settings_ini(self):
        Path("settings.ini").write_text(
            "\n".join(
                [
                    "[LabGateAction]",
                    "outgoing_folder=C:\\fallback-out",
                    "outgoing_filename=out.gdt",
                    "incoming_folder=C:\\fallback-in",
                    "incoming_filename_filter=RET*.gdt",
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            self.settings.load_labgate_action_setting(),
            {
                "outgoing_folder": r"C:\fallback-out",
                "outgoing_filename": "out.gdt",
                "incoming_folder": r"C:\fallback-in",
                "incoming_filename_filter": "RET*.gdt",
            },
        )


if __name__ == "__main__":
    unittest.main()
