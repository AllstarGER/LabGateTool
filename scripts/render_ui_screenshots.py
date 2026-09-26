"""Erzeugt die Oberflaechen-Screenshots fuer docs/screenshots/.

Ohne Bildschirm laufen lassen (offscreen). Achtung: die Offscreen-Plattform hat
nur 800x800 Pixel, dadurch werden breite Layouts beschnitten. Fuer realistische
Bilder eine groessere virtuelle Flaeche vorgeben, z.B.:

    QT_QPA_PLATFORM="vnc:size=1920x1080,depth=32" python scripts/render_ui_screenshots.py

Verwendet wird nur PyQt6 (bereits Abhaengigkeit des Werkzeugs); die API-Aufrufe
werden durch Beispieldaten ersetzt, es wird nichts gesendet.
"""

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "docs" / "screenshots"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import ui.labgateaction as lga  # noqa: E402

_SAMPLE_PATIENTS = [
    {"id": 1, "firstname": "Max", "secondname": "Mustermann", "dob": "01.01.1980", "gender": "M",
     "case_no": "202605210001", "case_date": "21.05.2026", "lab_code_1": "41591365",
     "lab_code_2": "", "lab_code_3": ""},
    {"id": 2, "firstname": "Erika", "secondname": "Musterfrau", "dob": "02.02.1975", "gender": "W",
     "case_no": "202605210002", "case_date": "21.05.2026", "lab_code_1": "",
     "lab_code_2": "", "lab_code_3": ""},
]

_SAMPLE_USERS = [
    {"id": 1, "user_id": "mmuster", "user_name": "Max Mustermann"},
    {"id": 2, "user_id": "emuster", "user_name": "Erika Musterfrau"},
    {"id": 3, "user_id": "abeispiel", "user_name": "Anna Beispiel"},
    {"id": 4, "user_id": "pprobst", "user_name": "Peter Probst"},
]


def _install_sample_data():
    lga.labgate_api.backend_is_configured = lambda: True
    lga.labgate_config.get_settings_source = lambda: {
        "path": r"C:\PMS\settings.ini",
        "origin": "PMS-Ordner (neben der EXE)",
    }
    lga.labgate_api.get_today_live_patients_for_labgate = lambda: (True, list(_SAMPLE_PATIENTS))
    lga.labgate_api.get_active_labgate_jobs = lambda statuses=None: (True, [])
    lga.labgate_api.get_open_labgate_job_for_patient = lambda patient_id: (False, None)
    lga.labgate_api.get_lab_marker = lambda case_no, lab_no: (True, None)
    lga.labgate_api.get_today_case_for_patient = lambda patient_id: (True, {
        "case_no": "202605210001",
        "case_date": "21.05.2026",
        "patient_id": patient_id,
        "lab_code_1": "41591365",
        "lab_code_2": "",
        "lab_code_3": "",
        "create_time": "08:00:00",
        "end_time": "",
    })


def _save(widget, name):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / name
    widget.grab().save(str(target))
    print(f"geschrieben: {target.relative_to(PROJECT_DIR)}", flush=True)


def main():
    _install_sample_data()
    window = lga.LabGateActionWindow()
    window.show()
    app.processEvents()
    _save(window, "tool-main.png")

    marker_dialog = lga.LabGateMarkerDialog(_SAMPLE_USERS, [1, 3], "Laborergebnis liegt vor", window)
    marker_dialog.show()
    app.processEvents()
    _save(marker_dialog, "tool-marker-dialog.png")

    settings_dialog = lga.LabGateSettingsDialog(window)
    settings_dialog.show()
    app.processEvents()
    _save(settings_dialog, "tool-settings.png")
    return 0


if __name__ == "__main__":
    # sys.exit, damit die Watcher-Threads den Prozess nicht offen halten.
    raise SystemExit(main())
