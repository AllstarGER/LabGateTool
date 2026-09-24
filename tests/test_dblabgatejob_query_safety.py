import importlib
import sys
import types
import unittest


class FakeCursor:
    def __init__(self, fetchall_result=None):
        self.fetchall_result = fetchall_result if fetchall_result is not None else []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return self.fetchall_result

    def close(self):
        return


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return self._cursor

    def commit(self):
        self.commits += 1

    def close(self):
        return


def _install_stubs():
    mysql = types.ModuleType("mysql")
    mysql_connector = types.ModuleType("mysql.connector")
    mysql_connector.connect = lambda **kwargs: None
    mysql.connector = mysql_connector
    sys.modules["mysql"] = mysql
    sys.modules["mysql.connector"] = mysql_connector

    labgate_config = types.ModuleType("labgate_config")
    labgate_config.load_db_setting = lambda: {
        "host": "host",
        "dbname": "dbname",
        "user": "user",
        "password": "password",
    }
    sys.modules["labgate_config"] = labgate_config


class DBLabGateJobQuerySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stubs()
        if "labgate_db" in sys.modules:
            del sys.modules["labgate_db"]
        cls.labgate_db = importlib.import_module("labgate_db")

    def test_find_open_job_by_patient_id_uses_placeholder(self):
        cursor = FakeCursor(fetchall_result=[])
        conn = FakeConnection(cursor)
        self.labgate_db.update_labgate_job_structure = lambda: (True, "Success")
        self.labgate_db.get_connection = lambda: (True, conn)

        ok, _ = self.labgate_db.find_open_labgate_job_by_return_data(patient_id="7 OR 1=1")
        self.assertFalse(ok)
        query, params = cursor.executed[-1]
        self.assertIn("patient_id = %s", query)
        self.assertNotIn("SELECT *", query)
        self.assertEqual(params, ("pending", "7 OR 1=1"))

    def test_find_open_job_by_name_and_dob_uses_placeholders(self):
        cursor = FakeCursor(fetchall_result=[])
        conn = FakeConnection(cursor)
        self.labgate_db.update_labgate_job_structure = lambda: (True, "Success")
        self.labgate_db.get_connection = lambda: (True, conn)

        ok, _ = self.labgate_db.find_open_labgate_job_by_return_data(
            firstname="Max",
            secondname="Mustermann",
            dob="01.01.1980",
        )
        self.assertFalse(ok)
        query, params = cursor.executed[-1]
        self.assertIn("patient_firstname = %s", query)
        self.assertIn("patient_secondname = %s", query)
        self.assertIn("patient_dob = %s", query)
        self.assertNotIn("SELECT *", query)
        self.assertEqual(params, ("pending", "Max", "Mustermann", "01.01.1980"))

    def test_get_active_labgate_jobs_uses_in_placeholders(self):
        cursor = FakeCursor(fetchall_result=[])
        conn = FakeConnection(cursor)
        self.labgate_db.update_labgate_job_structure = lambda: (True, "Success")
        self.labgate_db.get_connection = lambda: (True, conn)

        ok, _ = self.labgate_db.get_active_labgate_jobs(["pending", "error"])
        self.assertTrue(ok)
        query, params = cursor.executed[-1]
        self.assertIn("WHERE status IN (%s, %s)", query)
        self.assertNotIn("SELECT *", query)
        self.assertEqual(params, ("pending", "error"))

    def test_get_today_case_for_patient_uses_placeholder(self):
        cursor = FakeCursor(fetchall_result=[])
        conn = FakeConnection(cursor)
        self.labgate_db.get_connection = lambda: (True, conn)

        ok, _ = self.labgate_db.get_today_case_for_patient("99 OR 1=1")
        self.assertFalse(ok)
        query, params = cursor.executed[-1]
        self.assertIn("patient_id = %s", query)
        self.assertEqual(params, ("99 OR 1=1",))


if __name__ == "__main__":
    unittest.main()
