import unittest

import labgate_db


class DummyCursor:
    def __init__(self):
        self.query = None
        self.params = None

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return [
            (
                123,
                "Kevin",
                "Schwarz",
                "20.11.1992",
                "M",
                "CASE-1",
                "28.04.2026",
                "A",
                "B",
                "C",
            )
        ]

    def close(self):
        pass


class DummyConnection:
    def __init__(self):
        self.cursor_instance = DummyCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        pass


class MarkerCursor:
    def __init__(self, fetchone_value=None, rows=None):
        self.fetchone_value = fetchone_value
        self.rows = rows or []
        self.executed = []
        self.lastrowid = 77

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_value

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class MarkerConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        pass


class LabgateDbTests(unittest.TestCase):
    def test_lab_marker_user_ids_are_normalized_without_duplicates(self):
        self.assertEqual(
            labgate_db.normalize_lab_marker_user_ids([7, "8", "7", "", None]),
            ["7", "8"],
        )
        self.assertEqual(labgate_db.parse_lab_marker_user_ids("7, 8,7"), ["7", "8"])

    def test_get_lab_marker_maps_named_fields(self):
        fields = list(labgate_db.LAB_MARKER_FIELDS)
        values = {field: f"value-{field}" for field in fields}
        values.update({"id": 12, "case_no": "CASE-5", "lab_no": 2, "t_users": "7,8"})
        row = tuple(values[field] for field in fields)
        cursor = MarkerCursor(fetchone_value=row)
        connection = MarkerConnection(cursor)
        original_get_connection = labgate_db.get_connection
        labgate_db.get_connection = lambda: (True, connection)

        try:
            success, marker = labgate_db.get_lab_marker("CASE-5", 2)
        finally:
            labgate_db.get_connection = original_get_connection

        self.assertTrue(success)
        self.assertEqual(marker["id"], 12)
        self.assertEqual(marker["case_no"], "CASE-5")
        self.assertEqual(marker["lab_no"], 2)
        self.assertEqual(marker["t_users"], "7,8")

    def test_save_lab_marker_updates_existing_row_with_named_mapping(self):
        existing = (12, "CASE-6", 1, "7", "Laborergebnis liegt vor")
        cursor = MarkerCursor(fetchone_value=existing)
        connection = MarkerConnection(cursor)
        original_get_connection = labgate_db.get_connection
        labgate_db.get_connection = lambda: (True, connection)

        try:
            success, marker = labgate_db.save_lab_marker("CASE-6", 1, [8, 7, 8])
        finally:
            labgate_db.get_connection = original_get_connection

        self.assertTrue(success)
        self.assertEqual(marker["user_list"], ["8", "7"])
        self.assertEqual(marker["t_users"], "8,7")
        self.assertEqual(
            cursor.executed[-1][1],
            ("8,7", "Laborergebnis liegt vor", 12),
        )
        self.assertTrue(connection.committed)

    def test_today_live_patients_maps_gender_without_shifting_fields(self):
        connection = DummyConnection()
        original_get_connection = labgate_db.get_connection
        labgate_db.get_connection = lambda: (True, connection)

        try:
            success, patients = labgate_db.get_today_live_patients_for_labgate()
        finally:
            labgate_db.get_connection = original_get_connection

        self.assertTrue(success)
        self.assertIn("p.gender", connection.cursor_instance.query)
        self.assertNotIn("SELECT *", connection.cursor_instance.query)
        self.assertEqual(
            patients,
            [
                {
                    "id": 123,
                    "firstname": "Kevin",
                    "secondname": "Schwarz",
                    "dob": "20.11.1992",
                    "gender": "M",
                    "case_no": "CASE-1",
                    "case_date": "28.04.2026",
                    "lab_code_1": "A",
                    "lab_code_2": "B",
                    "lab_code_3": "C",
                }
            ],
        )

    def test_update_case_lab_code_slots_writes_multiple_slots_in_one_update(self):
        connection = DummyConnection()
        original_get_connection = labgate_db.get_connection
        labgate_db.get_connection = lambda: (True, connection)

        try:
            success, response = labgate_db.update_case_lab_code_slots(
                "CASE-1",
                [(1, "1365"), (2, "1366"), (3, "1367")],
            )
        finally:
            labgate_db.get_connection = original_get_connection

        self.assertTrue(success)
        self.assertEqual(response, "CASE-1")
        self.assertEqual(
            connection.cursor_instance.query,
            "UPDATE tbl_case SET lab_code_1 = %s, lab_code_2 = %s, lab_code_3 = %s WHERE case_no = %s",
        )
        self.assertEqual(connection.cursor_instance.params, ("1365", "1366", "1367", "CASE-1"))
        self.assertTrue(connection.committed)

    def test_labgate_job_mapping_survives_inserted_column(self):
        fields = list(labgate_db.LABGATE_JOB_FIELDS)
        fields.insert(fields.index("return_file"), "new_db_column")
        values = {field: f"value-{field}" for field in labgate_db.LABGATE_JOB_FIELDS}
        values.update(
            {
                "id": 9,
                "case_no": "CASE-2",
                "patient_id": 123,
                "return_file": "return.gdt",
                "new_db_column": "shift",
            }
        )
        row = tuple(values.get(field) for field in fields)

        mapped = labgate_db._row_to_dict(row, fields)

        self.assertEqual(mapped["id"], 9)
        self.assertEqual(mapped["case_no"], "CASE-2")
        self.assertEqual(mapped["patient_id"], 123)
        self.assertEqual(mapped["return_file"], "return.gdt")

    def test_today_live_patient_mapping_survives_inserted_column(self):
        fields = list(labgate_db.TODAY_LIVE_PATIENT_FIELDS)
        fields.insert(fields.index("case_no"), "new_db_column")
        values = {field: f"value-{field}" for field in labgate_db.TODAY_LIVE_PATIENT_FIELDS}
        values.update(
            {
                "id": 123,
                "firstname": "Kevin",
                "secondname": "Schwarz",
                "gender": "M",
                "case_no": "CASE-3",
                "lab_code_3": "C",
                "new_db_column": "shift",
            }
        )
        row = tuple(values.get(field) for field in fields)

        mapped = labgate_db._row_to_dict(row, fields)

        self.assertEqual(mapped["id"], 123)
        self.assertEqual(mapped["firstname"], "Kevin")
        self.assertEqual(mapped["gender"], "M")
        self.assertEqual(mapped["case_no"], "CASE-3")
        self.assertEqual(mapped["lab_code_3"], "C")

    def test_today_case_mapping_survives_inserted_column(self):
        fields = list(labgate_db.TODAY_CASE_FIELDS)
        fields.insert(fields.index("lab_code_1"), "new_db_column")
        values = {field: f"value-{field}" for field in labgate_db.TODAY_CASE_FIELDS}
        values.update(
            {
                "case_no": "CASE-4",
                "patient_id": 123,
                "lab_code_1": "A",
                "lab_code_2": "B",
                "lab_code_3": "C",
                "new_db_column": "shift",
            }
        )
        row = tuple(values.get(field) for field in fields)

        mapped = labgate_db._row_to_dict(row, fields)

        self.assertEqual(mapped["case_no"], "CASE-4")
        self.assertEqual(mapped["patient_id"], 123)
        self.assertEqual(mapped["lab_code_1"], "A")
        self.assertEqual(mapped["lab_code_3"], "C")


if __name__ == "__main__":
    unittest.main()
