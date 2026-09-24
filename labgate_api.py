"""Portal-API-Client der LabGate-Aktion.

Ersetzt den frueheren Direktzugriff auf die Portal-Datenbank:
alle Abfragen laufen ueber /api/desktop/... des PMS-Backends. Die Funktionsnamen
und Rueckgabewerte entsprechen bewusst der alten Datenbankschicht
(``(True, nutzlast)`` bzw. ``(False, meldung)``), damit UI und Dienst unveraendert
bleiben.
"""

import json
from urllib import error as urllib_error
from urllib import request as urllib_request

from loguru import logger

import labgate_config


REQUEST_TIMEOUT_SECONDS = 20.0
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = {502, 503, 504}
LAB_MARKER_SLOTS = (1, 2, 3)
LAB_MARKER_ALERT_TYPE = 15
LAB_MARKER_ALERT_LEVEL = 1
DEFAULT_LAB_MARKER_CONTENT = "Laborergebnis liegt vor"


def normalize_lab_marker_user_ids(user_ids):
    """Stabile, duplikatfreie Liste fuer tbl_case_lab_marker.t_users."""
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


def _api_base_url():
    return str(labgate_config.load_backend_setting().get("base_url") or "").strip().rstrip("/")


def _request_headers():
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = str(labgate_config.load_backend_setting().get("desktop_api_key") or "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _error_text(payload, fallback):
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message
    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        if message:
            return message
    return fallback


def _decode_response(raw_body):
    text = (raw_body or b"").decode("utf-8", "replace") if isinstance(raw_body, (bytes, bytearray)) else str(raw_body or "")
    text = text.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def backend_is_configured():
    """True, wenn Backend-Adresse und Desktop-API-Key gesetzt sind."""
    try:
        setting = labgate_config.load_backend_setting()
    except Exception as error:
        logger.error(f"LabGate backend settings could not be read: {error}")
        return False
    return bool(str(setting.get("base_url") or "").strip()) and bool(str(setting.get("desktop_api_key") or "").strip())


def request_api(path, payload=None, method=None, retry=None):
    """Ruft die Portal-API auf und liefert ``(True, data)`` bzw. ``(False, meldung)``.

    Wiederholt wird nur, wenn es gefahrlos ist: lesende Aufrufe (``retry=True``)
    duerfen nach einem Netzwerkfehler erneut laufen, schreibende Aufrufe
    (Job anlegen, Marker speichern, Jobstatus setzen, Alert senden) laufen genau
    einmal - ein zweiter Versuch koennte Doppeljobs oder Doppel-Alerts erzeugen.
    """
    try:
        base_url = _api_base_url()
        headers = _request_headers()
    except Exception as error:
        logger.error(f"LabGate API configuration could not be read: {error}")
        return False, "Backend-Konfiguration konnte nicht gelesen werden."

    if not base_url:
        return False, "Backend-Adresse fehlt (settings.ini [Backend] base_url)."

    url = f"{base_url}{path}"
    request_method = method or ("POST" if payload is not None else "GET")
    if retry is None:
        retry = request_method == "GET"
    attempts = max(1, MAX_ATTEMPTS if retry else 1)
    body = json.dumps(payload if payload is not None else {}).encode("utf-8") if request_method != "GET" else None
    last_error = "Portal-API nicht erreichbar."

    for attempt in range(1, attempts + 1):
        request_obj = urllib_request.Request(url, data=body, headers=headers, method=request_method)
        try:
            with urllib_request.urlopen(request_obj, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                parsed = _decode_response(response.read())
            if not parsed.get("success", False):
                return False, _error_text(parsed, "Portal-API hat die Anfrage abgelehnt.")
            data = parsed.get("data")
            return True, data if isinstance(data, dict) else {}
        except urllib_error.HTTPError as error:
            parsed = _decode_response(error.read())
            message = _error_text(parsed, f"Portal-API Fehler {error.code}")
            if error.code in RETRY_STATUS_CODES and attempt < attempts:
                last_error = message
                continue
            return False, message
        except Exception as error:
            last_error = f"Portal-API nicht erreichbar: {error}"
            if attempt < attempts:
                continue
            logger.error(f"LabGate API request failed: path={path} error={error}")
            return False, last_error

    return False, last_error


def get_labgate_users():
    ok, resp = request_api("/api/desktop/users", method="GET")
    if not ok:
        return False, f"Mitarbeiter konnten nicht geladen werden: {resp}"

    users = []
    for user in resp.get("users") or []:
        users.append({
            "id": user.get("id"),
            "user_id": user.get("user_id", ""),
            "user_name": user.get("user_name", ""),
        })
    return True, users


def get_lab_marker(case_no, lab_no):
    if case_no in (None, ""):
        return False, "Fallnummer fehlt"

    ok, resp = request_api(
        "/api/desktop/lab-markers",
        {"case_info": {"case_no": case_no}, "lab_no": lab_no},
        retry=True,
    )
    if not ok:
        return False, f"Labormitarbeiter konnten nicht geladen werden: {resp}"

    markers = resp.get("markers") or []
    if not markers:
        return True, None
    marker = markers[0] or {}
    return True, {
        "id": marker.get("id"),
        "case_no": marker.get("case_no", case_no),
        "lab_no": marker.get("lab_no", lab_no),
        "t_users": marker.get("t_users", "") or "",
        "t_content": marker.get("t_content", "") or "",
    }


def save_lab_marker(case_no, lab_no, user_ids, content=DEFAULT_LAB_MARKER_CONTENT):
    try:
        lab_no = int(lab_no)
    except (TypeError, ValueError):
        return False, "Ungueltiger Laborslot"
    if lab_no not in LAB_MARKER_SLOTS:
        return False, "Ungueltiger Laborslot"
    if case_no in (None, ""):
        return False, "Fallnummer fehlt"

    normalized_ids = normalize_lab_marker_user_ids(user_ids)
    users_value = ",".join(normalized_ids)
    content = str(content or "").strip() or DEFAULT_LAB_MARKER_CONTENT

    marker_flag, existing = get_lab_marker(case_no, lab_no)
    if not marker_flag:
        return False, existing

    marker_info = {
        "case_no": case_no,
        "lab_no": lab_no,
        "t_users": users_value,
        "t_content": content,
    }
    create = not existing or existing.get("id") in (None, "")
    if not create:
        marker_info["id"] = existing.get("id")

    ok, resp = request_api("/api/desktop/lab-marker", {"marker_info": marker_info, "create": create})
    if not ok:
        return False, f"Labormitarbeiter konnten nicht gespeichert werden: {resp}"

    marker = resp.get("marker") or {}
    return True, {
        "id": marker.get("id", marker_info.get("id")),
        "case_no": case_no,
        "lab_no": lab_no,
        "t_users": users_value,
        "t_content": content,
        "user_list": normalized_ids,
    }


def get_active_labgate_jobs(statuses=None):
    ok, resp = request_api("/api/desktop/labgate/jobs", {"statuses": list(statuses or ["pending"])}, retry=True)
    if not ok:
        return False, f"LabGate-Jobs konnten nicht geladen werden: {resp}"
    return True, resp.get("jobs") or []


def get_open_labgate_job_for_patient(patient_id):
    if patient_id in (None, ""):
        return False, "patient_id is required"

    ok, resp = request_api("/api/desktop/labgate/job/open", {"patient_id": patient_id}, retry=True)
    if not ok:
        return False, f"Offener LabGate-Job konnte nicht geladen werden: {resp}"

    job = resp.get("job")
    if not job:
        return False, None
    return True, job


def find_open_labgate_job_by_return_data(patient_id=None, firstname=None, secondname=None, dob=None):
    payload = {"status": "pending"}
    if patient_id not in (None, ""):
        payload["patient_id"] = patient_id
    else:
        if firstname in (None, "") or secondname in (None, "") or dob in (None, ""):
            return False, "Unvollstaendige Ruecklaufdaten fuer die Job-Suche"
        payload["firstname"] = firstname
        payload["secondname"] = secondname
        payload["dob"] = dob

    ok, resp = request_api("/api/desktop/labgate/job/match", payload, retry=True)
    if not ok:
        return False, resp
    job = resp.get("job")
    if not job:
        return False, "Kein passender offener LabGate-Job gefunden"
    return True, job


def create_labgate_job(job_info):
    job_info = dict(job_info or {})
    if job_info.get("case_no") in (None, ""):
        return False, "Fallnummer fehlt"
    if job_info.get("patient_id") in (None, ""):
        return False, "patient_id is required"

    ok, resp = request_api("/api/desktop/labgate/job", {"job_info": job_info})
    if not ok:
        return False, f"LabGate-Job konnte nicht angelegt werden: {resp}"
    return True, resp.get("job") or {}


def mark_labgate_job_imported(job_id, return_file, lab_number_raw, lab_number_clean, error_text=""):
    ok, resp = request_api(
        "/api/desktop/labgate/job/imported",
        {
            "job_id": job_id,
            "return_file": return_file,
            "lab_number_raw": lab_number_raw,
            "lab_number_clean": lab_number_clean,
            "error_text": error_text or "",
        },
    )
    if not ok:
        return False, f"LabGate-Jobstatus konnte nicht aktualisiert werden: {resp}"
    return True, resp.get("job_id", job_id)


def mark_labgate_job_error(job_id, return_file, error_text, lab_number_raw=None, lab_number_clean=None):
    ok, resp = request_api(
        "/api/desktop/labgate/job/error",
        {
            "job_id": job_id,
            "return_file": return_file,
            "lab_number_raw": lab_number_raw,
            "lab_number_clean": lab_number_clean,
            "error_text": error_text,
        },
    )
    if not ok:
        return False, f"LabGate-Jobstatus konnte nicht aktualisiert werden: {resp}"
    return True, resp.get("job_id", job_id)


def get_today_live_patients_for_labgate():
    ok, resp = request_api("/api/desktop/labgate/patients/live", {}, retry=True)
    if not ok:
        return False, f"Patientenliste fuer LabGate konnte nicht geladen werden: {resp}"
    return True, resp.get("patients") or []


def get_today_case_for_patient(patient_id):
    if patient_id in (None, ""):
        return False, "patient_id is required"

    ok, resp = request_api("/api/desktop/labgate/case/today", {"patient_id": patient_id}, retry=True)
    if not ok:
        return False, f"Heutiger Fall konnte nicht geladen werden: {resp}"

    case_info = resp.get("case")
    if not case_info:
        return False, None
    return True, case_info


def update_case_lab_code_slots(case_no, slot_values):
    if case_no in (None, ""):
        return False, "Fallnummer fehlt"

    normalized_slots = []
    used_slots = set()
    for slot_no, lab_number_clean in list(slot_values or []):
        try:
            slot_no = int(slot_no)
        except (TypeError, ValueError):
            return False, "Ungueltiger Laborslot"
        if slot_no not in LAB_MARKER_SLOTS:
            return False, "Ungueltiger Laborslot"
        if slot_no in used_slots:
            return False, "Doppelter Laborslot"
        used_slots.add(slot_no)
        normalized_slots.append([slot_no, "" if lab_number_clean is None else str(lab_number_clean)])

    if len(normalized_slots) == 0:
        return False, "Keine Labornummern zum Speichern"

    ok, resp = request_api(
        "/api/desktop/labgate/case/lab-codes",
        {"case_no": case_no, "slot_values": normalized_slots},
    )
    if not ok:
        return False, f"Labornummer konnte nicht im Fall gespeichert werden: {resp}"
    return True, resp.get("case_no", case_no)


def update_case_lab_code_slot(case_no, slot_no, lab_number_clean):
    return update_case_lab_code_slots(case_no, [(slot_no, lab_number_clean)])


def _assignment_info(case_no, slot_no, lab_number, marker, job=None):
    job = job or {}
    patient_name = " ".join(
        part for part in (job.get("patient_firstname"), job.get("patient_secondname")) if part
    ).strip()
    return {
        "case_no": case_no,
        "patient_id": job.get("patient_id"),
        "patient_name": patient_name,
        "case_date": job.get("case_date", ""),
        "lab_no": slot_no,
        "lab_code": lab_number,
        "marker_text": (marker or {}).get("t_content", ""),
    }


def notify_lab_report_assignment(case_no, slot_numbers, lab_numbers=None, job=None, file_name="", archive_path=""):
    """Informiert die im Labor-Marker benannten Mitarbeiter ueber den eingetroffenen Bericht.

    Entspricht der PMS-Funktion: der Marker (tbl_case_lab_marker) nennt pro Fall und
    Laborslot die Mitarbeiter; beim Eintreffen des Laborberichts erhalten genau diese
    Mitarbeiter einen Alert vom Typ 15 (Laborbericht eingetroffen).
    """
    if case_no in (None, ""):
        return False, "Fallnummer fehlt"

    lab_numbers = lab_numbers or {}
    notified = 0
    skipped = 0
    for slot_no in list(slot_numbers or []):
        marker_flag, marker = get_lab_marker(case_no, slot_no)
        if not marker_flag:
            return False, marker
        if not marker:
            skipped += 1
            continue

        recipients = parse_lab_marker_user_ids(marker.get("t_users"))
        if len(recipients) == 0:
            skipped += 1
            continue

        lab_number = lab_numbers.get(slot_no) or lab_numbers.get(str(slot_no)) or ""
        assignment_info = _assignment_info(case_no, slot_no, lab_number, marker, job)
        content = {
            "message": f"Laborbericht eingetroffen - {assignment_info['marker_text']}".strip(" -"),
            "data": {
                "marker_info": marker,
                "assignment_info": assignment_info,
                "report_info": assignment_info,
                "path": file_name,
                "file_path": archive_path,
            },
        }
        alert_flag, alert_resp = request_api(
            "/api/desktop/alert",
            {
                "alert_info": {
                    "t_type": LAB_MARKER_ALERT_TYPE,
                    "content": json.dumps(content, default=str),
                    "t_level": LAB_MARKER_ALERT_LEVEL,
                    "t_user": ",".join(recipients),
                    "user_list": recipients,
                }
            },
        )
        if not alert_flag:
            return False, f"Laborbenachrichtigung konnte nicht gesendet werden: {alert_resp}"
        notified += 1

    return True, {"notified": notified, "skipped": skipped}
