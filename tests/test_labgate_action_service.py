import importlib
import os
import sys
import tempfile
import types
import unittest

from labgate_action_util import DEFAULT_ENCODING, build_gdt_line


class _DummySignal:
    def connect(self, *args, **kwargs):
        return

    def emit(self, *args, **kwargs):
        return


class _DummyQThread:
    def __init__(self, *args, **kwargs):
        return


def _install_stubs():
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.QThread = _DummyQThread
    qtcore.pyqtSignal = lambda *args, **kwargs: _DummySignal()
    pyqt6 = types.ModuleType("PyQt6")
    pyqt6.QtCore = qtcore
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore

    labgate_config = types.ModuleType("labgate_config")
    labgate_config.load_labgate_action_setting = lambda: {}
    labgate_config.load_backend_setting = lambda: {"base_url": "", "desktop_api_key": ""}
    sys.modules["labgate_config"] = labgate_config

    loguru = types.ModuleType("loguru")
    loguru.logger = type(
        "Logger",
        (),
        {
            "error": staticmethod(lambda *args, **kwargs: None),
            "info": staticmethod(lambda *args, **kwargs: None),
        },
    )()
    sys.modules["loguru"] = loguru



class LabGateActionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs()
        if "labgate_action_service" in sys.modules:
            del sys.modules["labgate_action_service"]
        cls.service = importlib.import_module("labgate_action_service")
        # Die Tests tauschen API-Funktionen aus; nach jedem Test zuruecksetzen,
        # damit andere Testdateien das echte Modul sehen.
        cls._api_snapshot = {
            name: value
            for name, value in vars(cls.service.labgate_api).items()
            if not name.startswith("__")
        }

    def tearDown(self):
        api_module = self.service.labgate_api
        for name in list(vars(api_module).keys()):
            if name.startswith("__"):
                continue
            if name not in self._api_snapshot:
                delattr(api_module, name)
        for name, value in self._api_snapshot.items():
            setattr(api_module, name, value)

    def _write_return_file(self, file_path, lab_number_raw):
        payload = [
            build_gdt_line("3000", "12"),
            build_gdt_line("3101", "Mustermann"),
            build_gdt_line("3102", "Max"),
            build_gdt_line("3103", "19800422"),
        ]
        if lab_number_raw is not None:
            payload.append(build_gdt_line("6333", lab_number_raw))
        with open(file_path, "w", encoding=DEFAULT_ENCODING, newline="") as handle:
            handle.write("".join(payload))

    def _write_repeated_return_file(self, file_path, lab_numbers_raw):
        payload = []
        for lab_number_raw in lab_numbers_raw:
            payload.extend(
                [
                    build_gdt_line("3000", "7194"),
                    build_gdt_line("3101", "Althaus"),
                    build_gdt_line("3102", "Michael"),
                    build_gdt_line("3103", "03121980"),
                    build_gdt_line("3110", "1"),
                    build_gdt_line("6228", f"Auftragsnummer: {lab_number_raw}"),
                ]
            )
        with open(file_path, "w", encoding=DEFAULT_ENCODING, newline="") as handle:
            handle.write("".join(payload))

    def test_process_incoming_return_file_imports_clean_lab_number(self):
        captured = {}
        self.service.labgate_api.find_open_labgate_job_by_return_data = (
            lambda **kwargs: (True, {"id": 8, "case_no": "CASE-1", "slot_no": 2})
        )
        def _update_case_lab_code_slots(case_no, slot_values):
            captured["update"] = (case_no, slot_values)
            return True, "Success"

        def _mark_labgate_job_imported(job_id, return_file, raw, clean):
            captured["imported"] = (job_id, return_file, raw, clean)
            return True, job_id

        self.service.labgate_api.update_case_lab_code_slots = _update_case_lab_code_slots
        self.service.labgate_api.mark_labgate_job_imported = _mark_labgate_job_imported
        self.service.labgate_api.mark_labgate_job_error = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_error should not be called")
        )
        def _notify_lab_report_assignment(**kwargs):
            captured["notification"] = kwargs
            return True, {"notified": 1, "skipped": 0}

        self.service.labgate_api.notify_lab_report_assignment = _notify_lab_report_assignment

        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "IN123.gdt")
            self._write_return_file(source_path, "123456789")

            ok, payload = self.service.process_incoming_return_file(source_path, tmp)

            self.assertTrue(ok)
            self.assertEqual(payload["lab_number_clean"], "56789")
            self.assertEqual(captured["update"], ("CASE-1", [(2, "56789")]))
            self.assertEqual(captured["imported"][0], 8)
            self.assertEqual(captured["imported"][2:], ("123456789", "56789"))
            self.assertTrue(os.path.exists(payload["return_file"]))
            self.assertIn(os.path.join(tmp, "processed"), payload["return_file"])
            self.assertEqual(payload["events"], ["GDT-Ruecklauf eingelesen: IN123.gdt"])
            self.assertEqual(
                captured["notification"],
                {
                    "case_no": "CASE-1",
                    "slot_numbers": [2],
                    "lab_numbers": {2: "56789"},
                    "job": {"id": 8, "case_no": "CASE-1", "slot_no": 2},
                    "file_name": "IN123.gdt",
                    "archive_path": payload["return_file"],
                },
            )
            self.assertEqual(payload["notification"], {"notified": 1, "skipped": 0})

    def test_process_incoming_return_file_imports_multiple_lab_numbers(self):
        captured = {}
        self.service.labgate_api.find_open_labgate_job_by_return_data = (
            lambda **kwargs: (True, {"id": 10, "case_no": "CASE-3", "slot_no": 1})
        )

        def _update_case_lab_code_slots(case_no, slot_values):
            captured["update"] = (case_no, slot_values)
            return True, "Success"

        def _mark_labgate_job_imported(job_id, return_file, raw, clean):
            captured["imported"] = (job_id, return_file, raw, clean)
            return True, job_id

        self.service.labgate_api.update_case_lab_code_slots = _update_case_lab_code_slots
        self.service.labgate_api.mark_labgate_job_imported = _mark_labgate_job_imported
        self.service.labgate_api.mark_labgate_job_error = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_error should not be called")
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "DOPPEL.gdt")
            self._write_repeated_return_file(source_path, ["41591365", "41591366", "41591367"])

            ok, payload = self.service.process_incoming_return_file(source_path, tmp)

            self.assertTrue(ok)
            self.assertEqual(
                captured["update"],
                ("CASE-3", [(1, "1365"), (2, "1366"), (3, "1367")]),
            )
            self.assertEqual(captured["imported"][0], 10)
            self.assertEqual(captured["imported"][2:], ("41591365;41591366;41591367", "1365;1366;1367"))
            self.assertEqual(payload["lab_numbers_clean"], ["1365", "1366", "1367"])
            self.assertEqual(payload["lab_number_clean"], "1365;1366;1367")
            self.assertTrue(os.path.exists(payload["return_file"]))
            self.assertIn(os.path.join(tmp, "processed"), payload["return_file"])

    def test_process_incoming_return_file_rejects_more_than_three_lab_numbers(self):
        self.service.labgate_api.find_open_labgate_job_by_return_data = lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("find_open_labgate_job_by_return_data should not be called")
        )
        self.service.labgate_api.update_case_lab_code_slots = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("update_case_lab_code_slots should not be called")
        )
        self.service.labgate_api.mark_labgate_job_imported = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_imported should not be called")
        )
        self.service.labgate_api.mark_labgate_job_error = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_error should not be called")
        )

        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "VIER.gdt")
            self._write_repeated_return_file(source_path, ["41591365", "41591366", "41591367", "41591368"])

            ok, payload = self.service.process_incoming_return_file(source_path, tmp)

            self.assertFalse(ok)
            self.assertIn("mehr als drei", payload["message"])
            self.assertTrue(os.path.exists(payload["return_file"]))
            self.assertIn(os.path.join(tmp, "error"), payload["return_file"])

    def test_process_incoming_return_file_marks_error_when_slots_do_not_fit(self):
        captured = {}
        self.service.labgate_api.find_open_labgate_job_by_return_data = (
            lambda **kwargs: (True, {"id": 11, "case_no": "CASE-4", "slot_no": 3})
        )
        self.service.labgate_api.update_case_lab_code_slots = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("update_case_lab_code_slots should not be called")
        )
        self.service.labgate_api.mark_labgate_job_imported = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_imported should not be called")
        )

        def _mark_labgate_job_error(job_id, return_file, error_text, raw, clean):
            captured["error"] = (job_id, return_file, error_text, raw, clean)
            return True, job_id

        self.service.labgate_api.mark_labgate_job_error = _mark_labgate_job_error

        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "DOPPEL.gdt")
            self._write_repeated_return_file(source_path, ["41591365", "41591366"])

            ok, payload = self.service.process_incoming_return_file(source_path, tmp)

            self.assertFalse(ok)
            self.assertIn("nicht genug Laborslots frei", payload["message"])
            self.assertEqual(captured["error"][0], 11)
            self.assertEqual(captured["error"][3:], ("41591365;41591366", None))
            self.assertTrue(os.path.exists(payload["return_file"]))
            self.assertIn(os.path.join(tmp, "error"), payload["return_file"])

    def test_process_incoming_return_file_marks_error_for_short_lab_number(self):
        captured = {}
        self.service.labgate_api.find_open_labgate_job_by_return_data = (
            lambda **kwargs: (True, {"id": 9, "case_no": "CASE-2", "slot_no": 1})
        )
        self.service.labgate_api.update_case_lab_code_slots = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("update_case_lab_code_slots should not be called")
        )
        self.service.labgate_api.mark_labgate_job_imported = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mark_labgate_job_imported should not be called")
        )
        def _mark_labgate_job_error(job_id, return_file, error_text, raw, clean):
            captured["error"] = (job_id, return_file, error_text, raw, clean)
            return True, job_id

        self.service.labgate_api.mark_labgate_job_error = _mark_labgate_job_error

        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "IN124.gdt")
            self._write_return_file(source_path, "1234")

            ok, payload = self.service.process_incoming_return_file(source_path, tmp)

            self.assertFalse(ok)
            self.assertIn("at least 5 digits", payload["message"])
            self.assertEqual(captured["error"][0], 9)
            self.assertEqual(captured["error"][3:], ("1234", None))
            self.assertIn(os.path.join(tmp, "error"), captured["error"][1])
            self.assertTrue(os.path.exists(captured["error"][1]))
            self.assertEqual(payload["events"], ["GDT-Ruecklauf eingelesen: IN124.gdt"])


if __name__ == "__main__":
    unittest.main()
