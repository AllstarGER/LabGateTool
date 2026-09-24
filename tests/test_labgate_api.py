import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

loguru = types.ModuleType("loguru")
loguru.logger = type(
    "Logger",
    (),
    {
        "error": staticmethod(lambda *args, **kwargs: None),
        "info": staticmethod(lambda *args, **kwargs: None),
    },
)()
sys.modules.setdefault("loguru", loguru)

import labgate_api  # noqa: E402


class _FakeResponse:
    def __init__(self, body, status=200):
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status

    def read(self):
        return self._body

    def close(self):
        return

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok(data):
    return json.dumps({"success": True, "data": data})


def _fail(message, code=400):
    return json.dumps({"success": False, "error": {"code": code, "message": message}})


class _ApiStub:
    """Faengt die HTTP-Aufrufe ab und liefert vorbereitete Antworten."""

    def __init__(self, responses=None):
        self.requests = []
        self.responses = list(responses or [])

    def enqueue(self, body, status=200):
        self.responses.append((body, status))

    def urlopen(self, request_obj, timeout=None):
        self.requests.append({
            "url": request_obj.full_url,
            "method": request_obj.get_method(),
            "body": json.loads(request_obj.data.decode("utf-8")) if request_obj.data else None,
            "headers": {key.lower(): value for key, value in request_obj.header_items()},
        })
        body, status = self.responses.pop(0) if self.responses else (_ok({}), 200)
        if status >= 400:
            from urllib import error as urllib_error

            raise urllib_error.HTTPError(request_obj.full_url, status, "error", {}, _FakeResponse(body, status))
        return _FakeResponse(body, status)

    def last(self):
        return self.requests[-1]


class LabGateApiTests(unittest.TestCase):
    def setUp(self):
        self.stub = _ApiStub()
        self._original_urlopen = labgate_api.urllib_request.urlopen
        labgate_api.urllib_request.urlopen = self.stub.urlopen
        labgate_api.labgate_config.load_backend_setting = lambda: {
            "base_url": "https://portal.example/api-root/",
            "desktop_api_key": "key-123",
        }

    def tearDown(self):
        labgate_api.urllib_request.urlopen = self._original_urlopen

    def test_missing_base_url_is_reported(self):
        labgate_api.labgate_config.load_backend_setting = lambda: {"base_url": "", "desktop_api_key": ""}
        ok, message = labgate_api.get_active_labgate_jobs(["pending"])
        self.assertFalse(ok)
        self.assertIn("Backend-Adresse fehlt", message)
        self.assertEqual(self.stub.requests, [])

    def test_backend_is_configured(self):
        self.assertTrue(labgate_api.backend_is_configured())
        labgate_api.labgate_config.load_backend_setting = lambda: {"base_url": "https://x", "desktop_api_key": ""}
        self.assertFalse(labgate_api.backend_is_configured())

    def test_get_labgate_users_uses_get_and_maps_fields(self):
        self.stub.enqueue(_ok({"users": [
            {"id": 7, "user_id": "max", "user_name": "Max Muster", "user_role": "admin", "portal_access": 1},
            {"id": 9, "user_id": "erika", "user_name": "Erika Muster"},
        ]}))
        ok, users = labgate_api.get_labgate_users()
        self.assertTrue(ok)
        self.assertEqual(users, [
            {"id": 7, "user_id": "max", "user_name": "Max Muster"},
            {"id": 9, "user_id": "erika", "user_name": "Erika Muster"},
        ])
        request = self.stub.last()
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["url"], "https://portal.example/api-root/api/desktop/users")
        self.assertEqual(request["headers"]["x-api-key"], "key-123")

    def test_get_lab_marker_returns_none_when_no_marker_exists(self):
        self.stub.enqueue(_ok({"markers": []}))
        ok, marker = labgate_api.get_lab_marker("CASE-5", 2)
        self.assertTrue(ok)
        self.assertIsNone(marker)
        self.assertEqual(self.stub.last()["body"], {"case_info": {"case_no": "CASE-5"}, "lab_no": 2})

    def test_get_lab_marker_returns_first_marker(self):
        self.stub.enqueue(_ok({"markers": [{"id": 4, "case_no": "CASE-5", "lab_no": 2, "t_users": "7,9", "t_content": "watch"}]}))
        ok, marker = labgate_api.get_lab_marker("CASE-5", 2)
        self.assertTrue(ok)
        self.assertEqual(marker, {"id": 4, "case_no": "CASE-5", "lab_no": 2, "t_users": "7,9", "t_content": "watch"})

    def test_save_lab_marker_creates_when_missing(self):
        self.stub.enqueue(_ok({"markers": []}))
        self.stub.enqueue(_ok({"marker": {"id": 11, "case_no": "CASE-5", "lab_no": 1, "t_users": "7,9", "t_content": "watch"}}))
        ok, marker = labgate_api.save_lab_marker("CASE-5", 1, [7, "9", "7", ""], "watch")
        self.assertTrue(ok)
        self.assertEqual(marker["user_list"], ["7", "9"])
        self.assertEqual(marker["t_users"], "7,9")
        create_call = self.stub.requests[-1]
        self.assertEqual(create_call["url"], "https://portal.example/api-root/api/desktop/lab-marker")
        self.assertEqual(create_call["body"], {
            "marker_info": {"case_no": "CASE-5", "lab_no": 1, "t_users": "7,9", "t_content": "watch"},
            "create": True,
        })

    def test_save_lab_marker_updates_existing_marker(self):
        self.stub.enqueue(_ok({"markers": [{"id": 4, "case_no": "CASE-5", "lab_no": 3, "t_users": "7", "t_content": "alt"}]}))
        self.stub.enqueue(_ok({"marker": {"id": 4, "case_no": "CASE-5", "lab_no": 3, "t_users": "9", "t_content": "neu"}}))
        ok, marker = labgate_api.save_lab_marker("CASE-5", 3, ["9"], "neu")
        self.assertTrue(ok)
        self.assertEqual(marker["id"], 4)
        update_call = self.stub.requests[-1]
        self.assertEqual(update_call["body"]["create"], False)
        self.assertEqual(update_call["body"]["marker_info"]["id"], 4)

    def test_save_lab_marker_validates_slot_and_case(self):
        ok, message = labgate_api.save_lab_marker("CASE-5", 4, [7])
        self.assertFalse(ok)
        self.assertEqual(message, "Ungueltiger Laborslot")
        ok, message = labgate_api.save_lab_marker("", 1, [7])
        self.assertFalse(ok)
        self.assertEqual(message, "Fallnummer fehlt")
        self.assertEqual(self.stub.requests, [])

    def test_active_jobs_pass_statuses(self):
        self.stub.enqueue(_ok({"jobs": [{"id": 3, "status": "pending"}]}))
        ok, jobs = labgate_api.get_active_labgate_jobs(["pending"])
        self.assertTrue(ok)
        self.assertEqual(jobs, [{"id": 3, "status": "pending"}])
        self.assertEqual(self.stub.last()["body"], {"statuses": ["pending"]})

    def test_open_job_for_patient_keeps_legacy_semantics(self):
        self.stub.enqueue(_ok({"job": None}))
        ok, value = labgate_api.get_open_labgate_job_for_patient(77)
        self.assertFalse(ok)
        self.assertIsNone(value)

        self.stub.enqueue(_ok({"job": {"id": 5, "patient_id": 77}}))
        ok, job = labgate_api.get_open_labgate_job_for_patient(77)
        self.assertTrue(ok)
        self.assertEqual(job, {"id": 5, "patient_id": 77})

    def test_today_case_keeps_legacy_semantics(self):
        self.stub.enqueue(_ok({"case": None}))
        ok, value = labgate_api.get_today_case_for_patient(77)
        self.assertFalse(ok)
        self.assertIsNone(value)

        self.stub.enqueue(_ok({"case": {"case_no": "CASE-1"}}))
        ok, case_info = labgate_api.get_today_case_for_patient(77)
        self.assertTrue(ok)
        self.assertEqual(case_info, {"case_no": "CASE-1"})

    def test_match_return_data_requires_complete_name_data(self):
        ok, message = labgate_api.find_open_labgate_job_by_return_data(firstname="Max")
        self.assertFalse(ok)
        self.assertEqual(message, "Unvollstaendige Ruecklaufdaten fuer die Job-Suche")
        self.assertEqual(self.stub.requests, [])

    def test_match_return_data_maps_backend_errors_to_tool_messages(self):
        self.stub.enqueue(_fail("Kein passender offener LabGate-Job gefunden", 404), status=404)
        ok, message = labgate_api.find_open_labgate_job_by_return_data(patient_id=77)
        self.assertFalse(ok)
        self.assertEqual(message, "Kein passender offener LabGate-Job gefunden")

        self.stub.enqueue(_fail("Mehrere offene LabGate-Jobs passen auf den Ruecklauf", 409), status=409)
        ok, message = labgate_api.find_open_labgate_job_by_return_data(patient_id=77)
        self.assertFalse(ok)
        self.assertEqual(message, "Mehrere offene LabGate-Jobs passen auf den Ruecklauf")

    def test_match_return_data_by_name_sends_all_fields(self):
        self.stub.enqueue(_ok({"job": {"id": 11}}))
        ok, job = labgate_api.find_open_labgate_job_by_return_data(firstname="Max", secondname="Muster", dob="01.01.1980")
        self.assertTrue(ok)
        self.assertEqual(job, {"id": 11})
        self.assertEqual(self.stub.last()["body"], {
            "status": "pending",
            "firstname": "Max",
            "secondname": "Muster",
            "dob": "01.01.1980",
        })

    def test_mark_job_imported_and_error(self):
        self.stub.enqueue(_ok({"job_id": 9}))
        ok, job_id = labgate_api.mark_labgate_job_imported(9, "processed/r.gdt", "12345", "12345")
        self.assertTrue(ok)
        self.assertEqual(job_id, 9)
        self.assertEqual(self.stub.last()["body"], {
            "job_id": 9,
            "return_file": "processed/r.gdt",
            "lab_number_raw": "12345",
            "lab_number_clean": "12345",
            "error_text": "",
        })

        self.stub.enqueue(_ok({"job_id": 9}))
        ok, job_id = labgate_api.mark_labgate_job_error(9, "error/r.gdt", "kaputt")
        self.assertTrue(ok)
        self.assertEqual(job_id, 9)
        self.assertEqual(self.stub.last()["body"]["error_text"], "kaputt")
        self.assertEqual(self.stub.last()["url"].endswith("/api/desktop/labgate/job/error"), True)

    def test_live_patients_uses_today_endpoint(self):
        self.stub.enqueue(_ok({"patients": [{"id": 77, "case_no": "CASE-1"}]}))
        ok, patients = labgate_api.get_today_live_patients_for_labgate()
        self.assertTrue(ok)
        self.assertEqual(patients, [{"id": 77, "case_no": "CASE-1"}])
        self.assertEqual(self.stub.last()["url"].endswith("/api/desktop/labgate/patients/live"), True)

    def test_update_case_lab_code_slots_validates_locally(self):
        ok, message = labgate_api.update_case_lab_code_slots("CASE-1", [])
        self.assertFalse(ok)
        self.assertEqual(message, "Keine Labornummern zum Speichern")

        ok, message = labgate_api.update_case_lab_code_slots("CASE-1", [(4, "x")])
        self.assertFalse(ok)
        self.assertEqual(message, "Ungueltiger Laborslot")

        ok, message = labgate_api.update_case_lab_code_slots("CASE-1", [(1, "a"), (1, "b")])
        self.assertFalse(ok)
        self.assertEqual(message, "Doppelter Laborslot")
        self.assertEqual(self.stub.requests, [])

    def test_update_case_lab_code_slots_sends_slots(self):
        self.stub.enqueue(_ok({"case_no": "CASE-1", "affected_rows": 1}))
        ok, case_no = labgate_api.update_case_lab_code_slots("CASE-1", [(1, "111"), (2, 222)])
        self.assertTrue(ok)
        self.assertEqual(case_no, "CASE-1")
        self.assertEqual(self.stub.last()["body"], {"case_no": "CASE-1", "slot_values": [[1, "111"], [2, "222"]]})

        self.stub.enqueue(_ok({"case_no": "CASE-1"}))
        labgate_api.update_case_lab_code_slot("CASE-1", 3, "333")
        self.assertEqual(self.stub.last()["body"], {"case_no": "CASE-1", "slot_values": [[3, "333"]]})

    def test_backend_error_is_reported_as_failure(self):
        self.stub.enqueue(_fail("Ungueltiger Laborslot", 400), status=400)
        ok, message = labgate_api.get_active_labgate_jobs(["pending"])
        self.assertFalse(ok)
        self.assertIn("Ungueltiger Laborslot", message)

    def test_lab_report_notification_targets_marker_recipients(self):
        self.stub.enqueue(_ok({"markers": [{"id": 4, "case_no": "CASE-1", "lab_no": 1, "t_users": "7,9", "t_content": "Laborergebnis liegt vor"}]}))
        self.stub.enqueue(_ok({"alert": {"id": 21}}))

        ok, resp = labgate_api.notify_lab_report_assignment(
            case_no="CASE-1",
            slot_numbers=[1],
            lab_numbers={1: "12345"},
            job={"patient_id": 77, "patient_firstname": "Max", "patient_secondname": "Muster"},
            file_name="return.gdt",
            archive_path="C:/in/processed/return.gdt",
        )
        self.assertTrue(ok)
        self.assertEqual(resp, {"notified": 1, "skipped": 0})

        alert_call = self.stub.requests[-1]
        self.assertEqual(alert_call["url"], "https://portal.example/api-root/api/desktop/alert")
        alert_info = alert_call["body"]["alert_info"]
        self.assertEqual(alert_info["t_type"], 15)
        self.assertEqual(alert_info["t_level"], 1)
        self.assertEqual(alert_info["t_user"], "7,9")
        content = json.loads(alert_info["content"])
        self.assertEqual(content["message"], "Laborbericht eingetroffen - Laborergebnis liegt vor")
        self.assertEqual(content["data"]["assignment_info"], {
            "case_no": "CASE-1",
            "patient_id": 77,
            "patient_name": "Max Muster",
            "case_date": "",
            "lab_no": 1,
            "lab_code": "12345",
            "marker_text": "Laborergebnis liegt vor",
        })
        self.assertEqual(content["data"]["file_path"], "C:/in/processed/return.gdt")

    def test_lab_report_notification_skips_slots_without_recipients(self):
        self.stub.enqueue(_ok({"markers": [{"id": 4, "case_no": "CASE-1", "lab_no": 1, "t_users": "", "t_content": "x"}]}))
        self.stub.enqueue(_ok({"markers": []}))
        ok, resp = labgate_api.notify_lab_report_assignment(case_no="CASE-1", slot_numbers=[1, 2])
        self.assertTrue(ok)
        self.assertEqual(resp, {"notified": 0, "skipped": 2})
        self.assertEqual(len(self.stub.requests), 2)

    def test_reading_calls_are_retried_on_transient_errors(self):
        self.stub.enqueue(_fail("gateway", 504), status=504)
        self.stub.enqueue(_ok({"jobs": [{"id": 1}]}))
        ok, jobs = labgate_api.get_active_labgate_jobs(["pending"])
        self.assertTrue(ok)
        self.assertEqual(jobs, [{"id": 1}])
        self.assertEqual(len(self.stub.requests), 2)

    def test_writing_calls_run_exactly_once_on_transient_errors(self):
        self.stub.enqueue(_fail("gateway", 504), status=504)
        self.stub.enqueue(_ok({"job": {"id": 12}}))
        ok, message = labgate_api.create_labgate_job({"case_no": "CASE-1", "patient_id": 77, "slot_no": 1})
        self.assertFalse(ok)
        self.assertIn("gateway", message)
        self.assertEqual(len(self.stub.requests), 1)

        self.stub.responses = []
        self.stub.requests = []
        self.stub.enqueue(_fail("gateway", 503), status=503)
        self.stub.enqueue(_ok({"alert": {"id": 3}}))
        ok, message = labgate_api.request_api("/api/desktop/alert", {"alert_info": {"t_type": 15}})
        self.assertFalse(ok)
        self.assertEqual(len(self.stub.requests), 1)

    def test_lab_report_notification_reports_api_failure(self):
        self.stub.enqueue(_ok({"markers": [{"id": 4, "lab_no": 1, "t_users": "7", "t_content": "x"}]}))
        self.stub.enqueue(_fail("alert t_type is required", 400), status=400)
        ok, message = labgate_api.notify_lab_report_assignment(case_no="CASE-1", slot_numbers=[1])
        self.assertFalse(ok)
        self.assertIn("alert t_type is required", message)


if __name__ == "__main__":
    unittest.main()
