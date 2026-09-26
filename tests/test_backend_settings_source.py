"""Das Werkzeug liegt im PMS-Ordner und liest dessen settings.ini mit."""

import import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labgate_config  # noqa: E402


class BackendSettingsSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pms_dir = self.root / "PMS"
        self.exe_dir = self.pms_dir
        self.work_dir = self.root / "work"
        self.exe_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._old_cwd = os.getcwd()
        os.chdir(self.work_dir)

        self._old_search_dirs = labgate_config.app_paths.get_external_search_dirs
        self._old_exe_dir = labgate_config.app_paths.get_executable_dir
        labgate_config.app_paths.get_executable_dir = lambda: str(self.exe_dir)
        labgate_config.app_paths.get_external_search_dirs = lambda: [str(self.exe_dir), str(self.work_dir), str(self.root)]
        labgate_config.get_labgate_settings_path = lambda: str(self.exe_dir / "labgate_action.ini")
        labgate_config._logged_settings_source = None

        for name in ("HC_SETTINGS_FILE", "HC_BACKEND_BASE_URL", "HC_DESKTOP_API_KEY", "DESKTOP_API_KEY"):
            os.environ.pop(name, None)

    def tearDown(self):
        labgate_config.app_paths.get_external_search_dirs = self._old_search_dirs
        labgate_config.app_paths.get_executable_dir = self._old_exe_dir
        os.chdir(self._old_cwd)
        self.tmp.cleanup()

    def _write_settings(self, text, encoding="utf-8"):
        path = self.exe_dir / "settings.ini"
        path.write_text(text, encoding=encoding)
        return path

    def test_reads_pms_settings_next_to_the_executable(self):
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-1\n"
        )
        source = labgate_config.get_settings_source()
        self.assertEqual(source["path"], str(self.exe_dir / "settings.ini"))
        self.assertEqual(source["origin"], "PMS-Ordner (neben der EXE)")

        setting = labgate_config.load_backend_setting()
        self.assertEqual(setting["base_url"], "https://portal.example")
        self.assertEqual(setting["desktop_api_key"], "key-1")

    def test_reads_utf16_settings_file(self):
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-utf16\n",
            encoding="utf-16",
        )
        setting = labgate_config.load_backend_setting()
        self.assertEqual(setting["base_url"], "https://portal.example")
        self.assertEqual(setting["desktop_api_key"], "key-utf16")

    def test_reads_settings_file_with_bom(self):
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-bom\n",
            encoding="utf-8-sig",
        )
        setting = labgate_config.load_backend_setting()
        self.assertEqual(setting["base_url"], "https://portal.example")
        self.assertEqual(setting["desktop_api_key"], "key-bom")

    def test_environment_overrides_the_settings_file(self):
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-file\n"
        )
        os.environ["HC_BACKEND_BASE_URL"] = "https://env.example"
        os.environ["HC_DESKTOP_API_KEY"] = "key-env"
        try:
            setting = labgate_config.load_backend_setting()
        finally:
            os.environ.pop("HC_BACKEND_BASE_URL", None)
            os.environ.pop("HC_DESKTOP_API_KEY", None)
        self.assertEqual(setting["base_url"], "https://env.example")
        self.assertEqual(setting["desktop_api_key"], "key-env")

    def test_explicit_settings_file_via_environment(self):
        explicit = self.work_dir / "custom.ini"
        explicit.write_text("[Backend]\nbase_url = https://custom.example\ndesktop_api_key = key-custom\n", encoding="utf-8")
        self._write_settings("[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-1\n")
        os.environ["HC_SETTINGS_FILE"] = str(explicit)
        try:
            source = labgate_config.get_settings_source()
            setting = labgate_config.load_backend_setting()
        finally:
            os.environ.pop("HC_SETTINGS_FILE", None)
        self.assertEqual(source["path"], str(explicit))
        self.assertEqual(source["origin"], "HC_SETTINGS_FILE")
        self.assertEqual(setting["base_url"], "https://custom.example")

    def test_falls_back_to_the_cached_backend_link(self):
        self._write_settings("[Other]\nvalue = 1\n")
        (self.exe_dir / "forms_manifest_cache.json").write_text(
            json.dumps({"version": "1", "rows": [], "backend_base_link": "portal.example/"}), encoding="utf-8"
        )
        setting = labgate_config.load_backend_setting()
        self.assertEqual(setting["base_url"], "https://portal.example")

    def test_reports_missing_settings_file(self):
        source = labgate_config.get_settings_source()
        self.assertEqual(source["origin"], "wird neu angelegt")
        self.assertTrue(source["path"].endswith("settings.ini"))
        setting = labgate_config.load_backend_setting()
        self.assertEqual(setting["base_url"], "")
        self.assertEqual(setting["desktop_api_key"], "")

    def test_normalizes_backend_urls(self):
        self.assertEqual(labgate_config.normalize_backend_base_url("portal.example/"), "https://portal.example")
        self.assertEqual(labgate_config.normalize_backend_base_url("http://portal.example/"), "http://portal.example")
        self.assertEqual(labgate_config.normalize_backend_base_url("localhost:3006"), "http://localhost:3006")
        self.assertEqual(labgate_config.normalize_backend_base_url(""), "")

    def test_reads_labgate_action_section_from_pms_settings(self):
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-1\n\n"
            "[LabGateAction]\noutgoing_folder = C:\\LabGate\\out\noutgoing_filename = lab.gdt\n"
            "incoming_folder = C:\\LabGate\\in\nincoming_filename_filter = IN*.gdt\n"
        )
        config = labgate_config.load_labgate_action_setting()
        self.assertEqual(config["outgoing_folder"], r"C:\LabGate\out")
        self.assertEqual(config["outgoing_filename"], "lab.gdt")
        self.assertEqual(config["incoming_folder"], r"C:\LabGate\in")
        self.assertEqual(config["incoming_filename_filter"], "IN*.gdt")

    def test_own_labgate_action_file_wins_over_the_pms_settings(self):
        self._write_settings("[LabGateAction]\nincoming_folder = C:\\PMS\\in\n")
        (self.exe_dir / "labgate_action.ini").write_text(
            "[LabGateAction]\nincoming_folder = C:\\Tool\\in\n", encoding="utf-8"
        )
        config = labgate_config.load_labgate_action_setting()
        self.assertEqual(config["incoming_folder"], r"C:\Tool\in")

    def test_api_client_uses_the_discovered_settings(self):
        import labgate_api
        self._write_settings(
            "[Backend]\nbase_url = https://portal.example\ndesktop_api_key = key-1\n"
        )
        self.assertTrue(labgate_api.backend_is_configured())


if __name__ == "__main__":
    unittest.main()
