import os
import shutil
import time

from PyQt6.QtCore import QThread, pyqtSignal
from loguru import logger

import labgate_config
import labgate_api
from labgate_action_util import (
    FileStabilityTracker,
    clean_lab_number,
    extract_return_record,
    extract_return_records,
    make_archive_path,
    matches_filename_filter,
    parse_gdt_file,
)


class LabGateReturnWatcher(QThread):
    processed = pyqtSignal(bool, object)

    def __init__(self, parent=None, poll_interval_seconds=1.0):
        super().__init__(parent)
        self._running = True
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._tracker = FileStabilityTracker(threshold_seconds=2.0)

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            active_paths = []
            try:
                setting = labgate_config.load_labgate_action_setting()
                incoming_folder = setting.get("incoming_folder", "")
                filename_filter = setting.get("incoming_filename_filter", "*.gdt")
                if incoming_folder and os.path.isdir(incoming_folder):
                    for entry_name in sorted(os.listdir(incoming_folder)):
                        file_path = os.path.join(incoming_folder, entry_name)
                        if not os.path.isfile(file_path):
                            continue
                        if not matches_filename_filter(entry_name, filename_filter):
                            continue
                        active_paths.append(file_path)
                        try:
                            stat = os.stat(file_path)
                        except FileNotFoundError:
                            continue
                        if not self._tracker.update(file_path, stat.st_size, stat.st_mtime):
                            continue
                        result_flag, result = process_incoming_return_file(file_path, incoming_folder)
                        self._tracker.forget(file_path)
                        self.processed.emit(result_flag, result)
            except Exception as e:
                logger.error(f"LabGate watcher failed: {e}")
                self.processed.emit(False, {"message": str(e)})

            self._tracker.prune(active_paths)
            for _ in range(int(max(self._poll_interval_seconds, 0.2) / 0.2)):
                if not self._running:
                    break
                time.sleep(0.2)


def process_incoming_return_file(file_path, incoming_folder):
    file_name = os.path.basename(file_path)
    try:
        parsed = parse_gdt_file(file_path)
    except Exception as e:
        archived = _move_to_error(file_path, incoming_folder)
        _log_return_error(file_name, archived, f"Unreadable GDT file: {e}")
        return False, {"message": f"Unreadable GDT file: {e}", "return_file": archived, "file_name": file_name}

    records = extract_return_records(parsed, max_records=None)
    record = records[0] if len(records) > 0 else extract_return_record(parsed)
    read_message = f"GDT-Ruecklauf eingelesen: {file_name}"
    _log_return_read(file_name, file_path, records)
    if len(records) > 3:
        archived = _move_to_error(file_path, incoming_folder)
        reason = f"Ruecklauf enthaelt mehr als drei Auftragsnummern: {len(records)}"
        _log_return_error(file_name, archived, reason, record=record)
        return False, {"message": reason, "return_file": archived, "file_name": file_name, "events": [read_message]}

    lookup_flag, job_or_message = _lookup_pending_job(record)
    if not lookup_flag:
        archived = _move_to_error(file_path, incoming_folder)
        _log_return_error(file_name, archived, str(job_or_message), record=record)
        return False, {"message": str(job_or_message), "return_file": archived, "file_name": file_name, "events": [read_message]}

    job = job_or_message
    raw_lab_numbers = [item.get("lab_number_raw", "") for item in records]
    raw_lab_number = ";".join(raw_lab_numbers)
    try:
        clean_numbers = [clean_lab_number(raw_value) for raw_value in raw_lab_numbers]
    except Exception as e:
        archived = _move_to_error(file_path, incoming_folder)
        _log_return_error(file_name, archived, str(e), record=record, job=job)
        labgate_api.mark_labgate_job_error(job["id"], archived, str(e), raw_lab_number, None)
        return False, {
            "message": str(e),
            "return_file": archived,
            "job_id": job["id"],
            "file_name": file_name,
            "events": [read_message],
        }

    start_slot_no = int(job["slot_no"])
    if start_slot_no + len(clean_numbers) - 1 > 3:
        reason = (
            f"Ruecklauf enthaelt {len(clean_numbers)} Auftragsnummern, "
            f"aber ab Slot {start_slot_no} sind nicht genug Laborslots frei"
        )
        archived = _move_to_error(file_path, incoming_folder)
        _log_return_error(file_name, archived, reason, record=record, job=job)
        labgate_api.mark_labgate_job_error(job["id"], archived, reason, raw_lab_number, None)
        return False, {
            "message": reason,
            "return_file": archived,
            "job_id": job["id"],
            "file_name": file_name,
            "events": [read_message],
        }

    archived = _move_to_processed(file_path, incoming_folder)
    slot_values = [(start_slot_no + offset, clean_number) for offset, clean_number in enumerate(clean_numbers)]
    update_flag, update_resp = labgate_api.update_case_lab_code_slots(job["case_no"], slot_values)
    if not update_flag:
        error_archived = _move_processed_to_error(archived, incoming_folder)
        _log_return_error(file_name, error_archived, str(update_resp), record=record, job=job)
        labgate_api.mark_labgate_job_error(job["id"], error_archived, str(update_resp), raw_lab_number, ";".join(clean_numbers))
        return False, {
            "message": str(update_resp),
            "return_file": error_archived,
            "job_id": job["id"],
            "file_name": file_name,
            "events": [read_message],
        }

    clean_number = ";".join(clean_numbers)
    status_flag, status_resp = labgate_api.mark_labgate_job_imported(job["id"], archived, raw_lab_number, clean_number)
    if not status_flag:
        logger.error(
            "LabGate return imported but job status update failed: "
            f"file={file_name} archived={archived} job_id={job.get('id')} reason={status_resp}"
        )
        return False, {
            "message": str(status_resp),
            "return_file": archived,
            "job_id": job["id"],
            "file_name": file_name,
            "events": [read_message],
        }

    slot_numbers = [start_slot_no + offset for offset in range(len(clean_numbers))]
    lab_numbers = {slot_no: lab_number for slot_no, lab_number in slot_values}
    notify_flag, notify_resp = labgate_api.notify_lab_report_assignment(
        case_no=job["case_no"],
        slot_numbers=slot_numbers,
        lab_numbers=lab_numbers,
        job=job,
        file_name=file_name,
        archive_path=archived,
    )
    if not notify_flag:
        logger.error(
            "LabGate return imported but lab notification failed: "
            f"file={file_name} case_no={job.get('case_no')} reason={notify_resp}"
        )
        notification = {"error": str(notify_resp)}
    else:
        notification = notify_resp
        if notify_resp.get("notified", 0) > 0:
            logger.info(
                "LabGate lab notification sent: "
                f"case_no={job.get('case_no')} slots={slot_numbers} notified={notify_resp.get('notified')}"
            )

    return True, {
        "message": f"LabGate import finished for case {job['case_no']} ({len(clean_numbers)} Auftragsnummern)",
        "return_file": archived,
        "job_id": job["id"],
        "case_no": job["case_no"],
        "slot_no": start_slot_no,
        "lab_number_clean": clean_number,
        "lab_numbers_clean": clean_numbers,
        "file_name": file_name,
        "notification": notification,
        "events": [read_message],
    }


def _lookup_pending_job(record):
    patient_id = record.get("patient_id", "")
    if patient_id.isdigit():
        return labgate_api.find_open_labgate_job_by_return_data(patient_id=int(patient_id))
    return labgate_api.find_open_labgate_job_by_return_data(
        firstname=record.get("firstname", ""),
        secondname=record.get("secondname", ""),
        dob=record.get("dob", ""),
    )


def _move_to_processed(file_path, incoming_folder):
    target_path = make_archive_path(incoming_folder, "processed", os.path.basename(file_path))
    shutil.move(file_path, target_path)
    return target_path


def _move_to_error(file_path, incoming_folder):
    target_path = make_archive_path(incoming_folder, "error", os.path.basename(file_path))
    shutil.move(file_path, target_path)
    return target_path


def _move_processed_to_error(file_path, incoming_folder):
    target_path = make_archive_path(incoming_folder, "error", os.path.basename(file_path))
    shutil.move(file_path, target_path)
    return target_path


def _log_return_error(file_name, archived_path, reason, record=None, job=None):
    record = record or {}
    job = job or {}
    logger.error(
        "LabGate return moved to error: "
        f"file={file_name} error_path={archived_path} reason={reason} "
        f"patient_id={record.get('patient_id', '')} "
        f"firstname={record.get('firstname', '')} "
        f"secondname={record.get('secondname', '')} "
        f"dob={record.get('dob', '')} "
        f"lab_number_raw={record.get('lab_number_raw', '')} "
        f"job_id={job.get('id', '')} "
        f"case_no={job.get('case_no', '')}"
    )


def _log_return_read(file_name, file_path, records):
    if not isinstance(records, list):
        records = [records]
    record = records[0] if len(records) > 0 else {}
    lab_numbers = ";".join(item.get("lab_number_raw", "") for item in records)
    logger.info(
        "LabGate return GDT read: "
        f"file={file_name} path={file_path} records={len(records)} "
        f"patient_id={record.get('patient_id', '')} "
        f"firstname={record.get('firstname', '')} "
        f"secondname={record.get('secondname', '')} "
        f"dob={record.get('dob', '')} "
        f"lab_number_raw={lab_numbers}"
    )
