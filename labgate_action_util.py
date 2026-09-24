import fnmatch
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime

import app_paths


DEFAULT_ENCODING = "iso-8859-15"
DEFAULT_LINE_ENDING = "\r\n"


def sanitize_gdt_value(value):
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def format_gender_for_gdt(gender):
    gender_value = str(gender or "").strip().upper()
    if gender_value in ("W", "F", "2"):
        return "2"
    return "1"


def format_dob_for_gdt(dob):
    value = sanitize_gdt_value(dob)
    if value == "":
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y%m%d", "%d%m%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%d%m%Y")
        except ValueError:
            continue
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 8:
        if digits.startswith(("19", "20")):
            return f"{digits[6:8]}{digits[4:6]}{digits[0:4]}"
        return digits
    return digits


def normalize_return_dob(dob):
    value = sanitize_gdt_value(dob)
    if value == "":
        return ""
    for fmt in ("%Y%m%d", "%d%m%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 8:
        if digits.startswith(("19", "20")):
            return f"{digits[6:8]}.{digits[4:6]}.{digits[0:4]}"
        return f"{digits[0:2]}.{digits[2:4]}.{digits[4:8]}"
    return value


def build_gdt_line(field_id, value, line_ending=DEFAULT_LINE_ENDING):
    field = sanitize_gdt_value(field_id)
    content = sanitize_gdt_value(value)
    payload = f"{field}{content}"
    total_length = len(payload) + 3 + len(line_ending)
    return f"{total_length:03d}{payload}{line_ending}"


def build_gdt_request_fields(patient_info):
    return [
        ("8000", "6302"),
        ("8100", "00000"),
        ("9218", "02.10"),
        ("3000", sanitize_gdt_value(patient_info.get("id"))),
        ("3101", patient_info.get("secondname", "")),
        ("3102", patient_info.get("firstname", "")),
        ("3103", format_dob_for_gdt(patient_info.get("dob", ""))),
        ("3110", format_gender_for_gdt(patient_info.get("gender", ""))),
        ("8402", "ALLG00"),
    ]


def build_gdt_request_text(patient_info, line_ending=DEFAULT_LINE_ENDING):
    fields = build_gdt_request_fields(patient_info)
    provisional = "".join(build_gdt_line(field_id, value, line_ending=line_ending) for field_id, value in fields)
    total_length = len(provisional.encode(DEFAULT_ENCODING))

    rendered_lines = []
    for field_id, value in fields:
        if field_id == "8100":
            value = f"{total_length:05d}"
        rendered_lines.append(build_gdt_line(field_id, value, line_ending=line_ending))
    return "".join(rendered_lines)


def write_gdt_request_file(patient_info, folder, filename, encoding=DEFAULT_ENCODING):
    if sanitize_gdt_value(folder) == "":
        raise ValueError("Outgoing folder is empty")
    if sanitize_gdt_value(filename) == "":
        raise ValueError("Outgoing filename is empty")

    os.makedirs(folder, exist_ok=True)
    target_path = os.path.join(folder, filename)
    if os.path.exists(target_path):
        raise FileExistsError(f"Target GDT file already exists: {target_path}")

    payload = build_gdt_request_text(patient_info)
    temp_folder = app_paths.get_preferred_external_path("tmp")
    os.makedirs(temp_folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="labgate_", suffix=".gdt", dir=temp_folder)
    os.close(fd)
    try:
        with open(temp_path, "w", encoding=encoding, newline="") as handle:
            handle.write(payload)
        _move_file_with_windows_cmd(temp_path, target_path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return target_path


def _move_file_with_windows_cmd(source_path, target_path):
    result = subprocess.run(
        ["cmd.exe", "/c", "move", "/Y", source_path, target_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Windows move failed: {message}")


def parse_gdt_text(content_text):
    parsed = {}
    if content_text in (None, ""):
        return parsed
    for raw_line in str(content_text).splitlines():
        line = raw_line.strip("\r\n")
        if len(line) < 7:
            continue
        length_part = line[:3]
        if not length_part.isdigit():
            continue
        field_id = line[3:7]
        value = line[7:]
        parsed.setdefault(field_id, []).append(value)
    return parsed


def parse_gdt_file(file_path, encodings=None):
    if encodings is None:
        encodings = (DEFAULT_ENCODING, "latin-1", "utf-8")
    last_error = None
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as handle:
                return parse_gdt_text(handle.read())
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    with open(file_path, "r", encoding=DEFAULT_ENCODING) as handle:
        return parse_gdt_text(handle.read())


def get_last_field_value(parsed, field_id, default=""):
    values = parsed.get(field_id, [])
    if len(values) == 0:
        return default
    return values[-1]


def get_indexed_field_value(parsed, field_id, index, default=""):
    values = parsed.get(field_id, [])
    if len(values) == 0:
        return default
    if index < len(values):
        return values[index]
    return values[-1]


def clean_lab_number(raw_value):
    digits = "".join(ch for ch in sanitize_gdt_value(raw_value) if ch.isdigit())
    if len(digits) < 5:
        raise ValueError("Lab number must contain at least 5 digits")
    return digits[4:]


def first_free_lab_slot(case_info):
    for slot_no in (1, 2, 3):
        if sanitize_gdt_value(case_info.get(f"lab_code_{slot_no}", "")) == "":
            return slot_no
    return None


def matches_filename_filter(filename, filename_filter):
    name = os.path.basename(filename)
    pattern_text = sanitize_gdt_value(filename_filter)
    if pattern_text == "":
        return True
    patterns = [part.strip() for part in re.split(r"[;,]", pattern_text) if part.strip()]
    if len(patterns) == 0:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def extract_return_record(parsed):
    return {
        "patient_id": sanitize_gdt_value(get_last_field_value(parsed, "3000")),
        "secondname": sanitize_gdt_value(get_last_field_value(parsed, "3101")),
        "firstname": sanitize_gdt_value(get_last_field_value(parsed, "3102")),
        "dob": normalize_return_dob(get_last_field_value(parsed, "3103")),
        "lab_number_raw": extract_return_lab_number(parsed),
    }


def extract_return_records(parsed, max_records=None):
    lab_numbers = extract_return_lab_numbers(parsed, max_records=max_records)
    if len(lab_numbers) == 0:
        return [extract_return_record(parsed)]

    records = []
    for index, lab_number in enumerate(lab_numbers):
        records.append(
            {
                "patient_id": sanitize_gdt_value(get_indexed_field_value(parsed, "3000", index)),
                "secondname": sanitize_gdt_value(get_indexed_field_value(parsed, "3101", index)),
                "firstname": sanitize_gdt_value(get_indexed_field_value(parsed, "3102", index)),
                "dob": normalize_return_dob(get_indexed_field_value(parsed, "3103", index)),
                "lab_number_raw": lab_number,
            }
        )
    return records


def extract_return_lab_number(parsed):
    lab_numbers = extract_return_lab_numbers(parsed, max_records=None)
    if len(lab_numbers) > 0:
        return lab_numbers[-1]
    return ""


def extract_return_lab_numbers(parsed, max_records=None):
    lab_numbers = []
    for value in parsed.get("6333", []):
        direct_value = sanitize_gdt_value(value)
        if direct_value:
            lab_numbers.append(direct_value)

    if len(lab_numbers) == 0:
        for value in parsed.get("6228", []):
            for match in re.finditer(
                r"Auftragsnummer\s*:\s*([0-9][0-9\s./-]*)",
                sanitize_gdt_value(value),
                re.IGNORECASE,
            ):
                lab_numbers.append(match.group(1).strip())

    if max_records is None:
        return lab_numbers
    return lab_numbers[: int(max_records)]


def make_archive_path(base_folder, subfolder_name, original_name):
    folder = os.path.join(base_folder, subfolder_name)
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(original_name)
    candidate = os.path.join(folder, original_name)
    if not os.path.exists(candidate):
        return candidate
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return os.path.join(folder, f"{stem}_{stamp}{ext}")


class FileStabilityTracker:
    def __init__(self, threshold_seconds=2.0):
        self.threshold_seconds = float(threshold_seconds)
        self._states = {}

    def update(self, path, size, mtime, now=None):
        now = time.time() if now is None else float(now)
        old_state = self._states.get(path)
        new_state = (size, mtime, now if old_state is None or old_state[:2] != (size, mtime) else old_state[2])
        self._states[path] = new_state
        return (now - new_state[2]) >= self.threshold_seconds

    def forget(self, path):
        self._states.pop(path, None)

    def prune(self, active_paths):
        active = set(active_paths)
        for path in list(self._states.keys()):
            if path not in active:
                self._states.pop(path, None)
