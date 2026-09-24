from datetime import datetime

import mysql.connector

from labgate_config import load_db_setting


TABLE_NAME = "tbl_case_labgate_job"


LABGATE_JOB_FIELDS = (
    "id",
    "case_no",
    "patient_id",
    "slot_no",
    "status",
    "request_file",
    "return_file",
    "lab_number_raw",
    "lab_number_clean",
    "patient_firstname",
    "patient_secondname",
    "patient_dob",
    "created_at",
    "updated_at",
    "error_text",
)

LABGATE_JOB_SELECT_COLUMNS = ", ".join(LABGATE_JOB_FIELDS)

TODAY_LIVE_PATIENT_FIELDS = (
    "id",
    "firstname",
    "secondname",
    "dob",
    "gender",
    "case_no",
    "case_date",
    "lab_code_1",
    "lab_code_2",
    "lab_code_3",
)

TODAY_CASE_FIELDS = (
    "case_no",
    "case_date",
    "patient_id",
    "lab_code_1",
    "lab_code_2",
    "lab_code_3",
    "create_time",
    "end_time",
)

LAB_MARKER_TABLE_NAME = "tbl_case_lab_marker"
LAB_MARKER_FIELDS = ("id", "case_no", "lab_no", "t_users", "t_content")
LAB_MARKER_SELECT_COLUMNS = ", ".join(LAB_MARKER_FIELDS)

LABGATE_USER_FIELDS = ("id", "user_id", "user_name")
LABGATE_USER_SELECT_COLUMNS = ", ".join(LABGATE_USER_FIELDS)


def _db_error(prefix, error):
    return f"{prefix}: {error}"


def get_connection():
    settings_obj = load_db_setting()
    try:
        connection = mysql.connector.connect(
            host=settings_obj.get("host", ""),
            database=settings_obj.get("dbname", ""),
            user=settings_obj.get("user", ""),
            password=settings_obj.get("password", ""),
        )
        return True, connection
    except Exception as error:
        return False, _db_error("Datenbankverbindung fehlgeschlagen", error)


def _close(cursor, connection):
    try:
        if cursor is not None:
            cursor.close()
    finally:
        if connection is not None:
            connection.close()


class _MappedRow(dict):
    def __init__(self, fields, source):
        super().__init__(source)
        self._fields = tuple(fields)
        self._values = tuple(source.get(field) for field in self._fields)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, slice):
            return self._values[key]
        return super().__getitem__(key)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def _row_to_dict(row, fields=LABGATE_JOB_FIELDS):
    if isinstance(row, dict):
        source = row
    else:
        source = dict(zip(fields, row))
    return {field: source.get(field) for field in fields}


def _row_to_mapped(row, fields=LABGATE_JOB_FIELDS):
    return _MappedRow(fields, _row_to_dict(row, fields))


def _rows_to_mapped(rows, fields=LABGATE_JOB_FIELDS):
    return [_row_to_mapped(row, fields) for row in rows]


def normalize_lab_marker_user_ids(user_ids):
    """Return a stable, duplicate-free list for tbl_case_lab_marker.t_users."""
    if isinstance(user_ids, str):
        user_ids = user_ids.split(",")

    normalized = []
    for user_id in user_ids or []:
        if user_id is None:
            continue
        value = str(user_id).strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def parse_lab_marker_user_ids(value):
    return normalize_lab_marker_user_ids(value or "")


def get_lab_marker(case_no, lab_no):
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT {LAB_MARKER_SELECT_COLUMNS}
            FROM {LAB_MARKER_TABLE_NAME}
            WHERE case_no = %s AND lab_no = %s
            ORDER BY id
            LIMIT 1
            """,
            (case_no, lab_no),
        )
        row = cursor.fetchone()
        if row is None:
            return True, None
        return True, _row_to_mapped(row, LAB_MARKER_FIELDS)
    except Exception as error:
        return False, _db_error("Labormitarbeiter konnten nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def get_labgate_users():
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT {LABGATE_USER_SELECT_COLUMNS}
            FROM tbl_user
            WHERE is_deleted = 0
            ORDER BY user_name, user_id
            """
        )
        return True, _rows_to_mapped(cursor.fetchall(), LABGATE_USER_FIELDS)
    except Exception as error:
        return False, _db_error("Mitarbeiter konnten nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def save_lab_marker(case_no, lab_no, user_ids, content="Laborergebnis liegt vor"):
    try:
        lab_no = int(lab_no)
    except (TypeError, ValueError):
        return False, "Ungueltiger Laborslot"
    if lab_no not in (1, 2, 3):
        return False, "Ungueltiger Laborslot"
    if case_no in (None, ""):
        return False, "Fallnummer fehlt"

    normalized_ids = normalize_lab_marker_user_ids(user_ids)
    users_value = ",".join(normalized_ids)
    content = str(content or "").strip() or "Laborergebnis liegt vor"

    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT {LAB_MARKER_SELECT_COLUMNS}
            FROM {LAB_MARKER_TABLE_NAME}
            WHERE case_no = %s AND lab_no = %s
            ORDER BY id
            LIMIT 1
            """,
            (case_no, lab_no),
        )
        existing = cursor.fetchone()
        if existing is None:
            cursor.execute(
                f"""
                INSERT INTO {LAB_MARKER_TABLE_NAME}
                    (case_no, lab_no, t_users, t_content)
                VALUES (%s, %s, %s, %s)
                """,
                (case_no, lab_no, users_value, content),
            )
            marker_id = getattr(cursor, "lastrowid", None)
        else:
            existing_info = _row_to_dict(existing, LAB_MARKER_FIELDS)
            marker_id = existing_info.get("id")
            cursor.execute(
                f"""
                UPDATE {LAB_MARKER_TABLE_NAME}
                SET t_users = %s, t_content = %s
                WHERE id = %s
                """,
                (users_value, content, marker_id),
            )
        connection.commit()
        return True, {
            "id": marker_id,
            "case_no": case_no,
            "lab_no": lab_no,
            "t_users": users_value,
            "t_content": content,
            "user_list": normalized_ids,
        }
    except Exception as error:
        return False, _db_error("Labormitarbeiter konnten nicht gespeichert werden", error)
    finally:
        _close(cursor, connection)


def update_labgate_job_structure():
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                case_no char(255),
                patient_id INT(11),
                slot_no tinyint(1) DEFAULT 1,
                status char(32),
                request_file char(255),
                return_file char(255),
                lab_number_raw char(255),
                lab_number_clean char(255),
                patient_firstname char(255),
                patient_secondname char(255),
                patient_dob char(255),
                created_at datetime,
                updated_at datetime,
                error_text text
            )
            """
        )
        for index_sql in (
            f"CREATE INDEX idx_case_labgate_job_status ON {TABLE_NAME} (status)",
            f"CREATE INDEX idx_case_labgate_job_patient_status ON {TABLE_NAME} (patient_id, status)",
            f"CREATE INDEX idx_case_labgate_job_case_no ON {TABLE_NAME} (case_no)",
        ):
            try:
                cursor.execute(index_sql)
            except Exception:
                pass
        connection.commit()
        return True, "Success"
    except Exception as error:
        return False, _db_error("LabGate-Job-Tabelle konnte nicht angelegt werden", error)
    finally:
        _close(cursor, connection)


def create_labgate_job(job_info):
    ok, resp = update_labgate_job_structure()
    if not ok:
        return False, resp

    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        now = datetime.now()
        cursor = connection.cursor()
        cursor.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                case_no,
                patient_id,
                slot_no,
                status,
                request_file,
                return_file,
                lab_number_raw,
                lab_number_clean,
                patient_firstname,
                patient_secondname,
                patient_dob,
                created_at,
                updated_at,
                error_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job_info["case_no"],
                job_info["patient_id"],
                job_info["slot_no"],
                job_info.get("status", "pending"),
                job_info.get("request_file"),
                job_info.get("return_file"),
                job_info.get("lab_number_raw"),
                job_info.get("lab_number_clean"),
                job_info.get("patient_firstname"),
                job_info.get("patient_secondname"),
                job_info.get("patient_dob"),
                job_info.get("created_at", now),
                job_info.get("updated_at", now),
                job_info.get("error_text"),
            ),
        )
        connection.commit()
        created = dict(job_info)
        created["id"] = cursor.lastrowid
        created["created_at"] = job_info.get("created_at", now)
        created["updated_at"] = job_info.get("updated_at", now)
        return True, created
    except Exception as error:
        return False, _db_error("LabGate-Job konnte nicht angelegt werden", error)
    finally:
        _close(cursor, connection)


def get_active_labgate_jobs(statuses=None):
    ok, resp = update_labgate_job_structure()
    if not ok:
        return False, resp

    statuses = statuses or ["pending"]
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        placeholders = ", ".join(["%s"] * len(statuses))
        cursor.execute(
            f"""
            SELECT {LABGATE_JOB_SELECT_COLUMNS} FROM {TABLE_NAME}
            WHERE status IN ({placeholders})
            ORDER BY id DESC
            """,
            tuple(statuses),
        )
        rows = cursor.fetchall()
        return True, _rows_to_mapped(rows)
    except Exception as error:
        return False, _db_error("LabGate-Jobs konnten nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def get_open_labgate_job_for_patient(patient_id):
    ok, resp = update_labgate_job_structure()
    if not ok:
        return False, resp

    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT {LABGATE_JOB_SELECT_COLUMNS} FROM {TABLE_NAME}
            WHERE patient_id = %s AND status = %s
            ORDER BY id DESC
            """,
            (patient_id, "pending"),
        )
        rows = cursor.fetchall()
        if len(rows) == 0:
            return False, None
        return True, _row_to_mapped(rows[0])
    except Exception as error:
        return False, _db_error("Offener LabGate-Job konnte nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def find_open_labgate_job_by_return_data(patient_id=None, firstname=None, secondname=None, dob=None):
    ok, resp = update_labgate_job_structure()
    if not ok:
        return False, resp

    where_clauses = ["status = %s"]
    params = ["pending"]

    if patient_id not in (None, ""):
        where_clauses.append("patient_id = %s")
        params.append(patient_id)
    else:
        if firstname in (None, "") or secondname in (None, "") or dob in (None, ""):
            return False, "Unvollstaendige Ruecklaufdaten fuer die Job-Suche"
        where_clauses.extend(
            [
                "patient_firstname = %s",
                "patient_secondname = %s",
                "patient_dob = %s",
            ]
        )
        params.extend([firstname, secondname, dob])

    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT {LABGATE_JOB_SELECT_COLUMNS} FROM {TABLE_NAME}
            WHERE {" AND ".join(where_clauses)}
            ORDER BY id DESC
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        if len(rows) == 1:
            return True, _row_to_mapped(rows[0])
        if len(rows) == 0:
            return False, "Kein passender offener LabGate-Job gefunden"
        return False, "Mehrere offene LabGate-Jobs passen auf den Ruecklauf"
    except Exception as error:
        return False, _db_error("LabGate-Job-Ruecklauf konnte nicht zugeordnet werden", error)
    finally:
        _close(cursor, connection)


def mark_labgate_job_imported(job_id, return_file, lab_number_raw, lab_number_clean):
    return _update_job_status(
        job_id=job_id,
        status="imported",
        return_file=return_file,
        lab_number_raw=lab_number_raw,
        lab_number_clean=lab_number_clean,
        error_text="",
    )


def mark_labgate_job_error(job_id, return_file, error_text, lab_number_raw=None, lab_number_clean=None):
    return _update_job_status(
        job_id=job_id,
        status="error",
        return_file=return_file,
        lab_number_raw=lab_number_raw,
        lab_number_clean=lab_number_clean,
        error_text=error_text,
    )


def _update_job_status(job_id, status, return_file, lab_number_raw=None, lab_number_clean=None, error_text=None):
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET status = %s,
                return_file = %s,
                lab_number_raw = %s,
                lab_number_clean = %s,
                updated_at = %s,
                error_text = %s
            WHERE id = %s
            """,
            (status, return_file, lab_number_raw, lab_number_clean, datetime.now(), error_text, job_id),
        )
        connection.commit()
        return True, job_id
    except Exception as error:
        return False, _db_error("LabGate-Jobstatus konnte nicht aktualisiert werden", error)
    finally:
        _close(cursor, connection)


def get_today_live_patients_for_labgate():
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                p.id,
                p.firstname,
                p.secondname,
                p.dob,
                p.gender,
                c.case_no,
                c.case_date,
                c.lab_code_1,
                c.lab_code_2,
                c.lab_code_3
            FROM tbl_patient p
            INNER JOIN (
                SELECT
                    case_no,
                    case_date,
                    patient_id,
                    lab_code_1,
                    lab_code_2,
                    lab_code_3,
                    create_time,
                    end_time
                FROM (
                    SELECT
                        case_no,
                        case_date,
                        patient_id,
                        lab_code_1,
                        lab_code_2,
                        lab_code_3,
                        create_time,
                        end_time,
                        ROW_NUMBER() OVER (
                            PARTITION BY patient_id
                            ORDER BY
                                STR_TO_DATE(case_date, '%d.%m.%Y') DESC,
                                COALESCE(create_time, '00:00:00') DESC,
                                case_no DESC
                        ) AS rn
                    FROM tbl_case
                    WHERE updated != case_no
                      AND STR_TO_DATE(case_date, '%d.%m.%Y') = CURDATE()
                ) ranked_cases
                WHERE rn = 1
            ) c ON c.patient_id = p.id
            WHERE p.currently_practice = 1
            ORDER BY p.secondname ASC, p.firstname ASC, p.id ASC
            """
        )
        rows = cursor.fetchall()
        return True, _rows_to_mapped(rows, TODAY_LIVE_PATIENT_FIELDS)
    except Exception as error:
        return False, _db_error("Patientenliste fuer LabGate konnte nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def get_today_case_for_patient(patient_id):
    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                case_no,
                case_date,
                patient_id,
                lab_code_1,
                lab_code_2,
                lab_code_3,
                create_time,
                end_time
            FROM tbl_case
            WHERE patient_id = %s
              AND updated != case_no
              AND STR_TO_DATE(case_date, '%d.%m.%Y') = CURDATE()
            ORDER BY
                STR_TO_DATE(case_date, '%d.%m.%Y') DESC,
                COALESCE(create_time, '00:00:00') DESC,
                case_no DESC
            LIMIT 1
            """,
            (patient_id,),
        )
        rows = cursor.fetchall()
        if len(rows) == 0:
            return False, None
        return True, _row_to_mapped(rows[0], TODAY_CASE_FIELDS)
    except Exception as error:
        return False, _db_error("Heutiger Fall konnte nicht geladen werden", error)
    finally:
        _close(cursor, connection)


def update_case_lab_code_slot(case_no, slot_no, lab_number_clean):
    if slot_no not in (1, 2, 3):
        return False, "Ungueltiger Laborslot"

    return update_case_lab_code_slots(case_no, [(slot_no, lab_number_clean)])


def update_case_lab_code_slots(case_no, slot_values):
    slot_values = list(slot_values or [])
    if len(slot_values) == 0:
        return False, "Keine Labornummern zum Speichern"

    assignments = []
    params = []
    used_slots = set()
    for slot_no, lab_number_clean in slot_values:
        try:
            slot_no = int(slot_no)
        except (TypeError, ValueError):
            return False, "Ungueltiger Laborslot"
        if slot_no not in (1, 2, 3):
            return False, "Ungueltiger Laborslot"
        if slot_no in used_slots:
            return False, "Doppelter Laborslot"
        used_slots.add(slot_no)
        assignments.append(f"lab_code_{slot_no} = %s")
        params.append(lab_number_clean)

    resp, connection = get_connection()
    if resp is not True:
        return False, connection

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"UPDATE tbl_case SET {', '.join(assignments)} WHERE case_no = %s",
            tuple(params + [case_no]),
        )
        connection.commit()
        return True, case_no
    except Exception as error:
        return False, _db_error("Labornummer konnte nicht im Fall gespeichert werden", error)
    finally:
        _close(cursor, connection)
