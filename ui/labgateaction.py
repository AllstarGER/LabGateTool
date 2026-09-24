import os
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from loguru import logger

import labgate_config
import labgate_api
from labgate_action_service import LabGateReturnWatcher
from labgate_action_util import first_free_lab_slot, write_gdt_request_file


HINT_INFO = "info"
HINT_READY = "ready"
HINT_WARN = "warn"


GLOBAL_STYLESHEET = """
QWidget {
    background-color: #F2F5F9;
    color: #1F2A37;
    font-family: 'Segoe UI', 'Helvetica', sans-serif;
    font-size: 13pt;
}

/* ---- Header ---- */
QFrame#headerBar { background-color: #1565C0; }
QLabel#headerTitle {
    color: #FFFFFF;
    font-size: 24pt;
    font-weight: 600;
}
QLabel#headerSubtitle {
    color: #BBD2F2;
    font-size: 12pt;
}
QPushButton#header {
    background-color: rgba(255, 255, 255, 0.16);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13pt;
    font-weight: 500;
}
QPushButton#header:hover { background-color: rgba(255, 255, 255, 0.28); }
QPushButton#header:pressed { background-color: rgba(255, 255, 255, 0.40); }
QPushButton#headerExit {
    background-color: rgba(229, 57, 53, 0.30);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13pt;
    font-weight: 500;
}
QPushButton#headerExit:hover { background-color: #E53935; }

/* ---- Cards ---- */
QFrame#card {
    background-color: #FFFFFF;
    border: 1px solid #E1E6ED;
    border-radius: 14px;
}
QLabel#cardTitle {
    color: #4B5563;
    font-size: 11pt;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QLabel#fieldKey {
    color: #6B7280;
    font-size: 12pt;
}
QLabel#fieldValue {
    color: #111827;
    font-size: 16pt;
    font-weight: 500;
}

/* ---- Hint banner ---- */
QFrame#hintInfo {
    background-color: #E3F2FD;
    border: 1px solid #90CAF9;
    border-radius: 14px;
}
QFrame#hintReady {
    background-color: #E8F5E9;
    border: 1px solid #A5D6A7;
    border-radius: 14px;
}
QFrame#hintWarn {
    background-color: #FFF3E0;
    border: 1px solid #FFB74D;
    border-radius: 14px;
}
QLabel#hintIcon {
    font-size: 26pt;
}
QLabel#hintText {
    font-size: 15pt;
    font-weight: 500;
    color: #1F2A37;
}

/* ---- Slot tiles ---- */
QFrame#slotTile {
    background-color: #F9FAFB;
    border: 1px solid #E1E6ED;
    border-radius: 14px;
}
QFrame#slotTileFilled {
    background-color: #E8F5E9;
    border: 1px solid #66BB6A;
    border-radius: 14px;
}
QFrame#slotTileNext {
    background-color: #E3F2FD;
    border: 2px solid #1565C0;
    border-radius: 14px;
}
QLabel#slotLabel {
    color: #6B7280;
    font-size: 11pt;
    font-weight: 700;
    letter-spacing: 1.2px;
}
QLabel#slotValue {
    font-size: 22pt;
    font-weight: 600;
    color: #111827;
}
QLabel#slotValueFilled { color: #1B5E20; }
QLabel#slotValueNext { color: #0D47A1; }

/* ---- Buttons ---- */
QPushButton {
    background-color: #FFFFFF;
    color: #1F2A37;
    border: 1px solid #D1D5DB;
    border-radius: 12px;
    padding: 14px 22px;
    font-size: 14pt;
}
QPushButton:hover { background-color: #EAF1FB; }
QPushButton:pressed { background-color: #D6E4F7; }
QPushButton:disabled { background-color: #F3F4F6; color: #9CA3AF; border-color: #E5E7EB; }

QPushButton#primary {
    background-color: #2E7D32;
    color: white;
    border: none;
    border-radius: 16px;
    font-size: 20pt;
    font-weight: 700;
    padding: 22px 24px;
}
QPushButton#primary:hover { background-color: #388E3C; }
QPushButton#primary:pressed { background-color: #1B5E20; }
QPushButton#primary:disabled { background-color: #C8E6C9; color: #FFFFFF; }

QPushButton#warning {
    background-color: #FB8C00;
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 14pt;
    font-weight: 600;
    padding: 16px 22px;
}
QPushButton#warning:hover { background-color: #FFA726; }
QPushButton#warning:pressed { background-color: #F57C00; }
QPushButton#warning:disabled { background-color: #FFE0B2; color: #FFFFFF; }

/* ---- Patient list ---- */
QListWidget#patientList {
    background-color: transparent;
    border: none;
    outline: 0;
    padding: 0px;
}
QListWidget#patientList::item {
    background-color: #FFFFFF;
    color: #1F2A37;
    border: 1px solid #E1E6ED;
    border-radius: 12px;
    padding: 18px 20px;
    margin: 6px 2px;
    font-size: 14pt;
}
QListWidget#patientList::item:hover {
    background-color: #EAF1FB;
}
QListWidget#patientList::item:selected {
    background-color: #1565C0;
    color: #FFFFFF;
    border-color: #1565C0;
}

/* ---- Inputs ---- */
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 14pt;
    min-height: 32px;
}
QLineEdit:focus { border: 2px solid #1565C0; padding: 9px 13px; }

QPlainTextEdit {
    background-color: #FAFBFC;
    border: 1px solid #E1E6ED;
    border-radius: 10px;
    padding: 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11pt;
    color: #374151;
}

/* ---- Scrollbars (touch) ---- */
QScrollBar:vertical {
    background: transparent;
    width: 16px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #C5CCD6;
    border-radius: 7px;
    min-height: 48px;
}
QScrollBar::handle:vertical:hover { background: #98A2B3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def _make_card_frame():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(10)
    return frame, layout


def _make_card_title(text):
    label = QLabel(text.upper())
    label.setObjectName("cardTitle")
    return label


def _make_field_row(key_text):
    row = QHBoxLayout()
    row.setSpacing(12)
    key = QLabel(key_text)
    key.setObjectName("fieldKey")
    key.setMinimumWidth(150)
    key.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    value = QLabel("-")
    value.setObjectName("fieldValue")
    value.setWordWrap(True)
    value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    row.addWidget(key)
    row.addWidget(value, 1)
    return row, value


class LabGateSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LabGate Einstellungen")
        self.setModal(True)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.resize(900, 560)

        self.lnOutgoingFolder = QLineEdit()
        self.lnOutgoingFilename = QLineEdit()
        self.lnIncomingFolder = QLineEdit()
        self.lnIncomingFilter = QLineEdit()

        for line in (self.lnOutgoingFolder, self.lnOutgoingFilename,
                     self.lnIncomingFolder, self.lnIncomingFilter):
            line.setMinimumHeight(54)

        btnOutgoingBrowse = QPushButton("Ordner...")
        btnIncomingBrowse = QPushButton("Ordner...")
        btnSave = QPushButton("Speichern")
        btnCancel = QPushButton("Abbrechen")

        btnSave.setObjectName("primary")
        btnSave.setMinimumHeight(72)
        btnSave.setMinimumWidth(220)
        btnCancel.setMinimumHeight(72)
        btnCancel.setMinimumWidth(220)
        btnOutgoingBrowse.setMinimumHeight(54)
        btnOutgoingBrowse.setMinimumWidth(160)
        btnIncomingBrowse.setMinimumHeight(54)
        btnIncomingBrowse.setMinimumWidth(160)

        btnOutgoingBrowse.clicked.connect(self.on_outgoing_browse)
        btnIncomingBrowse.clicked.connect(self.on_incoming_browse)
        btnSave.clicked.connect(self.on_save)
        btnCancel.clicked.connect(self.reject)

        outgoing_card, outgoing_layout = _make_card_frame()
        outgoing_layout.addWidget(_make_card_title("Ausgehender Auftrag"))
        outgoing_layout.addWidget(QLabel("Ordner"))
        outgoing_row = QHBoxLayout()
        outgoing_row.setSpacing(10)
        outgoing_row.addWidget(self.lnOutgoingFolder, 1)
        outgoing_row.addWidget(btnOutgoingBrowse)
        outgoing_layout.addLayout(outgoing_row)
        outgoing_layout.addWidget(QLabel("Dateiname"))
        outgoing_layout.addWidget(self.lnOutgoingFilename)

        incoming_card, incoming_layout = _make_card_frame()
        incoming_layout.addWidget(_make_card_title("Eingehender Rücklauf"))
        incoming_layout.addWidget(QLabel("Ordner"))
        incoming_row = QHBoxLayout()
        incoming_row.setSpacing(10)
        incoming_row.addWidget(self.lnIncomingFolder, 1)
        incoming_row.addWidget(btnIncomingBrowse)
        incoming_layout.addLayout(incoming_row)
        incoming_layout.addWidget(QLabel("Dateifilter (z.B. *.gdt)"))
        incoming_layout.addWidget(self.lnIncomingFilter)

        actions = QHBoxLayout()
        actions.setSpacing(16)
        actions.addStretch(1)
        actions.addWidget(btnCancel)
        actions.addWidget(btnSave)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 24)
        root.setSpacing(18)

        title = QLabel("LabGate Einstellungen")
        title.setStyleSheet("font-size: 22pt; font-weight: 600; color: #1565C0;")
        root.addWidget(title)
        root.addWidget(outgoing_card)
        root.addWidget(incoming_card)
        root.addStretch(1)
        root.addLayout(actions)

        self.load_settings()

    def load_settings(self):
        config = labgate_config.load_labgate_action_setting()
        self.lnOutgoingFolder.setText(config.get("outgoing_folder", ""))
        self.lnOutgoingFilename.setText(config.get("outgoing_filename", "pat.gdt"))
        self.lnIncomingFolder.setText(config.get("incoming_folder", ""))
        self.lnIncomingFilter.setText(config.get("incoming_filename_filter", "*.gdt"))

    def get_settings(self):
        return {
            "outgoing_folder": self.lnOutgoingFolder.text().strip(),
            "outgoing_filename": self.lnOutgoingFilename.text().strip(),
            "incoming_folder": self.lnIncomingFolder.text().strip(),
            "incoming_filename_filter": self.lnIncomingFilter.text().strip() or "*.gdt",
        }

    def on_outgoing_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Ausgehenden Ordner waehlen", self.lnOutgoingFolder.text())
        if folder:
            self.lnOutgoingFolder.setText(folder)

    def on_incoming_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Eingehenden Ordner waehlen", self.lnIncomingFolder.text())
        if folder:
            self.lnIncomingFolder.setText(folder)

    def on_save(self):
        data = self.get_settings()
        if data["outgoing_folder"] == "":
            QMessageBox.information(self, "Hinweis", "Bitte einen ausgehenden Ordner angeben.")
            return
        if data["outgoing_filename"] == "":
            QMessageBox.information(self, "Hinweis", "Bitte einen ausgehenden Dateinamen angeben.")
            return
        if data["incoming_folder"] == "":
            QMessageBox.information(self, "Hinweis", "Bitte einen eingehenden Ordner angeben.")
            return
        if labgate_config.save_labgate_action_setting(data):
            self.accept()
            return
        QMessageBox.information(self, "Hinweis", "Die LabGate-Einstellungen konnten nicht gespeichert werden.")


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class LabGateMarkerDialog(QDialog):
    def __init__(self, users, selected_user_ids=None, content="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mitarbeiter für Laborbenachrichtigung")
        self.setModal(True)
        self.resize(620, 600)

        selected_ids = {str(user_id) for user_id in (selected_user_ids or [])}
        self.user_list = QListWidget()
        self.user_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.user_list.setMinimumHeight(360)
        for user in users:
            user_id = user.get("id")
            label = str(user.get("user_name") or user.get("user_id") or user_id)
            if user.get("user_id") and user.get("user_name"):
                label = f"{user['user_name']} ({user['user_id']})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, user_id)
            item.setSelected(str(user_id) in selected_ids)
            self.user_list.addItem(item)

        self.lnContent = QLineEdit(content or "Laborergebnis liegt vor")
        self.lnContent.setPlaceholderText("Hinweis für die Benachrichtigung")

        btnSave = QPushButton("Speichern")
        btnCancel = QPushButton("Abbrechen")
        btnSave.setObjectName("primary")
        btnSave.clicked.connect(self.accept)
        btnCancel.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(btnCancel)
        actions.addWidget(btnSave)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(QLabel("Ein oder mehrere Mitarbeiter auswählen:"))
        layout.addWidget(self.user_list, 1)
        layout.addWidget(QLabel("Hinweis:"))
        layout.addWidget(self.lnContent)
        layout.addLayout(actions)

    def selected_user_ids(self):
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.user_list.selectedItems()
        ]

    def content(self):
        return self.lnContent.text().strip()


class LabGateActionWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_patient = None
        self._selected_case_info = None
        self._watcher = None
        self._blocking_job = None
        self._build_ui()
        self.ensure_schema()
        self.reload_patients()
        self.restart_watcher()

    # Boot maximized instead of exclusive fullscreen so the Windows taskbar and
    # normal window controls stay available while the LabGate host app can move
    # to the foreground.
    def show(self):
        self.showMaximized()

    def _build_ui(self):
        self.setWindowTitle("LabGate-Aktions-Tool")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.resize(1366, 768)
        self.setStyleSheet(GLOBAL_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        body_layout.setSpacing(20)
        body_layout.addWidget(self._build_left_panel(), 35)
        body_layout.addWidget(self._build_right_panel(), 65)
        root.addWidget(body, 1)

        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)

    def _build_header(self):
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(96)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 14, 28, 14)
        layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("LabGate")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Aktions-Tool – Laboraufträge senden und Rückläufe verfolgen")
        subtitle.setObjectName("headerSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.btnRefresh = QPushButton("Aktualisieren")
        self.btnSettings = QPushButton("Einstellungen")
        self.btnExit = QPushButton("Beenden")

        self.btnRefresh.setObjectName("header")
        self.btnSettings.setObjectName("header")
        self.btnExit.setObjectName("headerExit")
        for btn in (self.btnRefresh, self.btnSettings, self.btnExit):
            btn.setMinimumHeight(60)
            btn.setMinimumWidth(170)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btnRefresh.clicked.connect(self.reload_patients)
        self.btnSettings.clicked.connect(self.open_settings)
        self.btnExit.clicked.connect(self.close)

        layout.addLayout(title_box)
        layout.addStretch(1)
        layout.addWidget(self.btnRefresh)
        layout.addWidget(self.btnSettings)
        layout.addWidget(self.btnExit)
        return header

    def _build_left_panel(self):
        card, card_layout = _make_card_frame()
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)

        header_row = QHBoxLayout()
        title_label = QLabel("PATIENTEN HEUTE")
        title_label.setObjectName("cardTitle")
        self.lbPatientCount = QLabel("0")
        self.lbPatientCount.setStyleSheet(
            "background-color: #1565C0; color: white; border-radius: 12px;"
            " padding: 4px 14px; font-size: 12pt; font-weight: 600;"
        )
        header_row.addWidget(title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.lbPatientCount)
        card_layout.addLayout(header_row)

        self.listPatients = QListWidget()
        self.listPatients.setObjectName("patientList")
        self.listPatients.setSpacing(0)
        self.listPatients.setUniformItemSizes(False)
        self.listPatients.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.listPatients.currentItemChanged.connect(self.on_patient_changed)
        card_layout.addWidget(self.listPatients, 1)

        return card

    def _build_right_panel(self):
        wrapper = QWidget()
        right = QVBoxLayout(wrapper)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)

        right.addWidget(self._build_hint_banner())
        right.addWidget(self._build_info_row())
        right.addWidget(self._build_slot_card())
        right.addWidget(self._build_action_row())
        right.addWidget(self._build_log_card(), 1)

        return wrapper

    def _build_hint_banner(self):
        self.hintFrame = QFrame()
        self.hintFrame.setObjectName("hintInfo")
        self.hintFrame.setMinimumHeight(72)
        layout = QHBoxLayout(self.hintFrame)
        layout.setContentsMargins(22, 14, 22, 14)
        layout.setSpacing(16)

        self.lbHintIcon = QLabel("i")
        self.lbHintIcon.setObjectName("hintIcon")
        self.lbHintIcon.setFixedWidth(40)
        self.lbHintIcon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbActionHint = QLabel("Bitte einen Patienten auswählen.")
        self.lbActionHint.setObjectName("hintText")
        self.lbActionHint.setWordWrap(True)
        self.lbActionHint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout.addWidget(self.lbHintIcon)
        layout.addWidget(self.lbActionHint, 1)
        return self.hintFrame

    def _set_hint(self, text, level):
        if level == HINT_READY:
            self.hintFrame.setObjectName("hintReady")
            self.lbHintIcon.setText("✓")
        elif level == HINT_WARN:
            self.hintFrame.setObjectName("hintWarn")
            self.lbHintIcon.setText("!")
        else:
            self.hintFrame.setObjectName("hintInfo")
            self.lbHintIcon.setText("i")
        self.hintFrame.style().unpolish(self.hintFrame)
        self.hintFrame.style().polish(self.hintFrame)
        self.lbActionHint.setText(text)

    def _build_info_row(self):
        row = QHBoxLayout()
        row.setSpacing(16)

        # Patient card
        patient_card, patient_layout = _make_card_frame()
        patient_layout.addWidget(_make_card_title("Patient"))
        name_row, self.lbPatientName = _make_field_row("Name")
        dob_row, self.lbPatientDob = _make_field_row("Geburtsdatum")
        patient_layout.addLayout(name_row)
        patient_layout.addLayout(dob_row)
        patient_layout.addStretch(1)

        # Case / Job card
        case_card, case_layout = _make_card_frame()
        case_layout.addWidget(_make_card_title("Fall & Auftrag"))
        case_no_row, self.lbCaseNo = _make_field_row("Fall")
        case_date_row, self.lbCaseDate = _make_field_row("Falldatum")
        job_status_row, self.lbJobStatus = _make_field_row("Jobstatus")
        request_row, self.lbOpenRequestFile = _make_field_row("Datei")
        case_layout.addLayout(case_no_row)
        case_layout.addLayout(case_date_row)
        case_layout.addLayout(job_status_row)
        case_layout.addLayout(request_row)

        row.addWidget(patient_card, 1)
        row.addWidget(case_card, 1)

        wrapper = QWidget()
        wrapper.setLayout(row)
        return wrapper

    def _build_slot_card(self):
        card, layout = _make_card_frame()
        header_row = QHBoxLayout()
        header_row.addWidget(_make_card_title("Labornummern"))
        header_row.addStretch(1)
        self.lbNextSlot = QLabel("-")
        self.lbNextSlot.setStyleSheet(
            "background-color: #E3F2FD; color: #0D47A1; border: 1px solid #90CAF9;"
            " border-radius: 12px; padding: 4px 14px; font-size: 12pt; font-weight: 600;"
        )
        header_row.addWidget(QLabel("Nächster freier Slot:"))
        header_row.addWidget(self.lbNextSlot)
        layout.addLayout(header_row)

        grid = QGridLayout()
        grid.setSpacing(14)
        self._slot_tiles = []
        self._slot_value_labels = []
        for idx in range(3):
            tile = ClickableFrame()
            tile.setObjectName("slotTile")
            tile.setMinimumHeight(110)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(18, 14, 18, 14)
            tile_layout.setSpacing(4)

            slot_label = QLabel(f"SLOT {idx + 1}")
            slot_label.setObjectName("slotLabel")
            slot_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            value_label = QLabel("-")
            value_label.setObjectName("slotValue")
            value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            tile_layout.addWidget(slot_label)
            tile_layout.addWidget(value_label, 1)

            grid.addWidget(tile, 0, idx)
            self._slot_tiles.append(tile)
            self._slot_value_labels.append(value_label)
            tile.clicked.connect(lambda slot_no=idx + 1: self.open_marker_dialog(slot_no))

        # Map back to legacy attribute names so existing logic still works.
        self.lbSlot1, self.lbSlot2, self.lbSlot3 = self._slot_value_labels

        layout.addLayout(grid)
        return card

    def _refresh_slot_styles(self, next_slot=None):
        for idx, (tile, value_label) in enumerate(zip(self._slot_tiles, self._slot_value_labels)):
            text = (value_label.text() or "").strip()
            is_filled = text not in ("", "-", "(leer)")
            is_next = (next_slot is not None and (idx + 1) == next_slot)
            if is_filled:
                tile.setObjectName("slotTileFilled")
                value_label.setObjectName("slotValueFilled")
            elif is_next:
                tile.setObjectName("slotTileNext")
                value_label.setObjectName("slotValueNext")
            else:
                tile.setObjectName("slotTile")
                value_label.setObjectName("slotValue")
            tile.style().unpolish(tile)
            tile.style().polish(tile)
            value_label.style().unpolish(value_label)
            value_label.style().polish(value_label)

    def _build_action_row(self):
        card, layout = _make_card_frame()
        layout.addWidget(_make_card_title("Aktion"))

        row = QHBoxLayout()
        row.setSpacing(16)

        self.btnCreateOrder = QPushButton("Auftrag senden")
        self.btnCreateOrder.setObjectName("primary")
        self.btnCreateOrder.setMinimumHeight(120)
        self.btnCreateOrder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.btnCreateOrder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnCreateOrder.clicked.connect(self.create_order)

        self.btnResetOrder = QPushButton("Offenen Auftrag\nzurücksetzen")
        self.btnResetOrder.setObjectName("warning")
        self.btnResetOrder.setMinimumHeight(120)
        self.btnResetOrder.setMinimumWidth(280)
        self.btnResetOrder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnResetOrder.clicked.connect(self.reset_open_job)

        row.addWidget(self.btnCreateOrder, 2)
        row.addWidget(self.btnResetOrder, 1)
        layout.addLayout(row)

        return card

    def _build_log_card(self):
        card, layout = _make_card_frame()
        layout.addWidget(_make_card_title("Rücklauf & Ereignisse"))
        self.txtLog = QPlainTextEdit()
        self.txtLog.setReadOnly(True)
        self.txtLog.setMinimumHeight(140)
        layout.addWidget(self.txtLog, 1)
        return card

    def _toggle_fullscreen(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def ensure_schema(self):
        """Prueft die Backend-Konfiguration (frueher: Anlegen der Jobtabelle)."""
        if labgate_api.backend_is_configured():
            return
        QMessageBox.information(
            self,
            "Backend nicht konfiguriert",
            "Bitte in der settings.ini unter [Backend] base_url und desktop_api_key hinterlegen.",
        )

    def append_log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.txtLog.appendPlainText(f"[{stamp}] {message}")

    def reload_patients(self):
        selected_id = None if self._selected_patient is None else self._selected_patient.get("id")
        self.listPatients.clear()
        self._selected_patient = None

        resp_flag, rows = labgate_api.get_today_live_patients_for_labgate()
        if not resp_flag:
            self.lbPatientCount.setText("0")
            QMessageBox.information(self, "Hinweis", str(rows))
            self.refresh_details(None)
            return

        for row in rows:
            display = f"{row['secondname']}, {row['firstname']}\n{row['dob']}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.listPatients.addItem(item)
            if selected_id is not None and row["id"] == selected_id:
                self.listPatients.setCurrentItem(item)

        self.lbPatientCount.setText(str(len(rows)))

        if selected_id is None and self.listPatients.count() > 0:
            self.listPatients.setCurrentRow(0)
        elif self.listPatients.currentItem() is None:
            self.refresh_details(None)
        self.refresh_action_state()

    def on_patient_changed(self, current, previous):
        if current is None:
            self._selected_patient = None
            self.refresh_details(None)
            return
        self._selected_patient = current.data(Qt.ItemDataRole.UserRole)
        self.refresh_details(self._selected_patient)

    def refresh_details(self, patient_row):
        if patient_row is None:
            self._selected_case_info = None
            self.lbPatientName.setText("-")
            self.lbPatientDob.setText("-")
            self.lbCaseNo.setText("-")
            self.lbCaseDate.setText("-")
            self.lbJobStatus.setText("-")
            self.lbOpenRequestFile.setText("-")
            self.lbSlot1.setText("-")
            self.lbSlot2.setText("-")
            self.lbSlot3.setText("-")
            self.lbNextSlot.setText("-")
            self._refresh_slot_styles(next_slot=None)
            self.refresh_action_state()
            return

        case_flag, case_info = labgate_api.get_today_case_for_patient(patient_row["id"])
        if not case_flag or case_info is None:
            case_info = {
                "case_no": patient_row.get("case_no", ""),
                "case_date": patient_row.get("case_date", ""),
                "lab_code_1": patient_row.get("lab_code_1", ""),
                "lab_code_2": patient_row.get("lab_code_2", ""),
                "lab_code_3": patient_row.get("lab_code_3", ""),
            }
        self._selected_case_info = case_info

        job_flag, job_info = labgate_api.get_open_labgate_job_for_patient(patient_row["id"])

        self.lbPatientName.setText(f"{patient_row['firstname']} {patient_row['secondname']}")
        self.lbPatientDob.setText(patient_row["dob"])
        self.lbCaseNo.setText(case_info.get("case_no", "-") or "-")
        self.lbCaseDate.setText(case_info.get("case_date", "-") or "-")
        self.lbSlot1.setText(case_info.get("lab_code_1", "") or "(leer)")
        self.lbSlot2.setText(case_info.get("lab_code_2", "") or "(leer)")
        self.lbSlot3.setText(case_info.get("lab_code_3", "") or "(leer)")

        next_slot = first_free_lab_slot(case_info)
        self.lbNextSlot.setText("-" if next_slot is None else str(next_slot))
        self._refresh_slot_styles(next_slot=next_slot)
        for slot_no, tile in enumerate(self._slot_tiles, start=1):
            has_lab_number = bool(case_info.get(f"lab_code_{slot_no}") or "")
            tile.setCursor(
                Qt.CursorShape.PointingHandCursor
                if has_lab_number
                else Qt.CursorShape.ArrowCursor
            )
            tile.setToolTip(
                "Mitarbeiter für Laborbenachrichtigung auswählen"
                if has_lab_number
                else "Noch keine Labornummer vorhanden"
            )
        if job_flag and job_info:
            self.lbJobStatus.setText(f"Offen in Slot {job_info['slot_no']}")
            self.lbOpenRequestFile.setText(job_info.get("request_file", "") or "-")
        else:
            self.lbJobStatus.setText("Kein offener Auftrag")
            self.lbOpenRequestFile.setText("-")
        self.refresh_action_state(case_info=case_info, has_open_job=bool(job_flag and job_info))

    def open_marker_dialog(self, slot_no):
        case_info = self._selected_case_info
        if self._selected_patient is None or not case_info:
            return
        if not str(case_info.get(f"lab_code_{slot_no}") or "").strip():
            QMessageBox.information(self, "Hinweis", "Dieser Slot hat noch keine Labornummer.")
            return

        marker_flag, marker = labgate_api.get_lab_marker(case_info.get("case_no"), slot_no)
        if not marker_flag:
            QMessageBox.information(self, "Hinweis", str(marker))
            return
        users_flag, users = labgate_api.get_labgate_users()
        if not users_flag:
            QMessageBox.information(self, "Hinweis", str(users))
            return

        selected_user_ids = []
        content = "Laborergebnis liegt vor"
        if marker:
            selected_user_ids = labgate_api.parse_lab_marker_user_ids(marker.get("t_users"))
            content = marker.get("t_content") or content

        dialog = LabGateMarkerDialog(users, selected_user_ids, content, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        save_flag, save_resp = labgate_api.save_lab_marker(
            case_info.get("case_no"),
            slot_no,
            dialog.selected_user_ids(),
            dialog.content(),
        )
        if not save_flag:
            QMessageBox.information(self, "Hinweis", str(save_resp))
            return

        selected_count = len(save_resp.get("user_list", []))
        self.append_log(
            f"Laborbenachrichtigung für Slot {slot_no} gespeichert ({selected_count} Mitarbeiter)."
        )

    def refresh_action_state(self, case_info=None, has_open_job=None):
        any_open_flag, open_jobs = labgate_api.get_active_labgate_jobs(["pending"])
        any_open_job = bool(any_open_flag and open_jobs)
        self._blocking_job = open_jobs[0] if any_open_job else None

        if self._selected_patient is None:
            self.btnCreateOrder.setEnabled(False)
            self.btnResetOrder.setEnabled(self._blocking_job is not None)
            if self._blocking_job is not None:
                message = self._format_blocking_job_message(self._blocking_job, own_job=False)
                self._set_hint(message, HINT_WARN)
            else:
                message = "Bitte zuerst einen Patienten auswählen."
                self._set_hint(message, HINT_INFO)
            return

        if case_info is None:
            case_flag, case_info = labgate_api.get_today_case_for_patient(self._selected_patient["id"])
            if not case_flag:
                case_info = None

        if has_open_job is None:
            job_flag, job_info = labgate_api.get_open_labgate_job_for_patient(self._selected_patient["id"])
            has_open_job = bool(job_flag and job_info)
        if has_open_job and any_open_job:
            for candidate in open_jobs:
                if candidate.get("patient_id") == self._selected_patient["id"]:
                    self._blocking_job = candidate
                    break

        if case_info is None:
            self.btnCreateOrder.setEnabled(False)
            self.btnResetOrder.setEnabled(self._blocking_job is not None)
            self._set_hint("Kein heutiger Fall für den ausgewählten Patienten gefunden.", HINT_WARN)
            return
        if first_free_lab_slot(case_info) is None:
            self.btnCreateOrder.setEnabled(False)
            self.btnResetOrder.setEnabled(self._blocking_job is not None)
            self._set_hint("Alle drei Labornummern-Slots sind bereits belegt.", HINT_WARN)
            return
        if has_open_job or any_open_job:
            self.btnCreateOrder.setEnabled(False)
            self.btnResetOrder.setEnabled(self._blocking_job is not None)
            if has_open_job:
                message = self._format_blocking_job_message(self._blocking_job, own_job=True)
            else:
                message = self._format_blocking_job_message(self._blocking_job, own_job=False)
            self._set_hint(message, HINT_WARN)
            return
        self.btnCreateOrder.setEnabled(True)
        self.btnResetOrder.setEnabled(False)
        self._set_hint("Bereit zum Senden eines neuen LabGate-Auftrags.", HINT_READY)

    def _format_blocking_job_message(self, job_info, own_job):
        if not job_info:
            return "Es existiert ein offener LabGate-Auftrag."
        name = f"{job_info.get('patient_firstname', '')} {job_info.get('patient_secondname', '')}".strip()
        if name == "":
            name = f"Patient {job_info.get('patient_id', '-')}"
        prefix = (
            "Für diesen Patienten existiert bereits ein offener LabGate-Auftrag"
            if own_job
            else "Ein anderer offener LabGate-Auftrag blockiert neue Sendungen"
        )
        return (
            f"{prefix}: {name} "
            f"(Fall {job_info.get('case_no', '-')}, Slot {job_info.get('slot_no', '-')})."
        )

    def open_settings(self):
        dialog = LabGateSettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.append_log("LabGate-Einstellungen gespeichert.")
            self.restart_watcher()

    def create_order(self):
        if self._selected_patient is None:
            QMessageBox.information(self, "Hinweis", "Bitte zuerst einen Patienten auswählen.")
            return

        any_open_flag, open_jobs = labgate_api.get_active_labgate_jobs(["pending"])
        if any_open_flag and open_jobs:
            QMessageBox.information(self, "Hinweis", "Es existiert bereits ein offener LabGate-Auftrag.")
            return

        config = labgate_config.load_labgate_action_setting()
        if config.get("outgoing_folder", "").strip() == "":
            QMessageBox.information(self, "Hinweis", "Bitte zuerst die LabGate-Einstellungen konfigurieren.")
            return

        case_flag, case_info = labgate_api.get_today_case_for_patient(self._selected_patient["id"])
        if not case_flag or case_info is None:
            QMessageBox.information(self, "Hinweis", "Kein heutiger Fall für den Patienten gefunden.")
            return

        slot_no = first_free_lab_slot(case_info)
        if slot_no is None:
            QMessageBox.information(self, "Hinweis", "Alle drei Labornummern-Slots sind bereits belegt.")
            return

        request_path = None
        try:
            request_path = write_gdt_request_file(
                self._selected_patient,
                config["outgoing_folder"],
                config["outgoing_filename"],
            )
            write_message = f"GDT-Datei geschrieben: {request_path}"
            logger.info(
                "LabGate request GDT written: "
                f"file={request_path} patient_id={self._selected_patient.get('id', '')} "
                f"firstname={self._selected_patient.get('firstname', '')} "
                f"secondname={self._selected_patient.get('secondname', '')} "
                f"dob={self._selected_patient.get('dob', '')}"
            )
            self.append_log(write_message)
            job_flag, job_resp = labgate_api.create_labgate_job(
                {
                    "case_no": case_info["case_no"],
                    "patient_id": self._selected_patient["id"],
                    "slot_no": slot_no,
                    "status": "pending",
                    "request_file": request_path,
                    "return_file": "",
                    "lab_number_raw": "",
                    "lab_number_clean": "",
                    "patient_firstname": self._selected_patient["firstname"],
                    "patient_secondname": self._selected_patient["secondname"],
                    "patient_dob": self._selected_patient["dob"],
                    "error_text": "",
                }
            )
            if not job_flag:
                if request_path and os.path.exists(request_path):
                    os.unlink(request_path)
                raise RuntimeError(str(job_resp))

            self.append_log(
                f"LabGate-Auftrag angelegt für {self._selected_patient['firstname']} {self._selected_patient['secondname']} in Slot {slot_no}."
            )
            self.reload_patients()
        except Exception as e:
            QMessageBox.information(self, "Hinweis", str(e))

    def reset_open_job(self):
        any_open_flag, open_jobs = labgate_api.get_active_labgate_jobs(["pending"])
        if not any_open_flag:
            self._blocking_job = None
            self.btnCreateOrder.setEnabled(False)
            self.btnResetOrder.setEnabled(False)
            self._set_hint("Offene LabGate-Aufträge konnten nicht geladen werden.", HINT_WARN)
            QMessageBox.information(self, "Hinweis", str(open_jobs))
            return
        if not open_jobs:
            QMessageBox.information(self, "Hinweis", "Es existiert kein offener LabGate-Auftrag.")
            self.reload_patients()
            return

        job_info = None
        if self._selected_patient is not None:
            for candidate in open_jobs:
                if candidate.get("patient_id") == self._selected_patient["id"]:
                    job_info = candidate
                    break
        if job_info is None:
            if len(open_jobs) > 1:
                QMessageBox.information(
                    self,
                    "Hinweis",
                    "Es existieren mehrere offene LabGate-Aufträge. Bitte zuerst den betroffenen Patienten auswählen.",
                )
                self.reload_patients()
                return
            job_info = open_jobs[0]

        own_job = bool(self._selected_patient is not None and job_info.get("patient_id") == self._selected_patient["id"])
        prompt = (
            f"{self._format_blocking_job_message(job_info, own_job)}\n\n"
            "Soll dieser Auftrag auf Fehler gesetzt werden, damit wieder ein neuer Auftrag angelegt werden kann?"
        )
        answer = QMessageBox.question(self, "Offenen Auftrag zurücksetzen", prompt)
        if answer != QMessageBox.StandardButton.Yes:
            return

        error_text = f"Manuell zurückgesetzt am {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        reset_flag, reset_resp = labgate_api.mark_labgate_job_error(
            job_info["id"],
            job_info.get("return_file", "") or "",
            error_text,
            job_info.get("lab_number_raw", "") or "",
            job_info.get("lab_number_clean", "") or "",
        )
        if not reset_flag:
            QMessageBox.information(self, "Hinweis", str(reset_resp))
            return

        patient_name = f"{job_info.get('patient_firstname', '')} {job_info.get('patient_secondname', '')}".strip()
        self.append_log(f"Offener LabGate-Auftrag zurückgesetzt: {job_info.get('case_no', '-')} / {patient_name}")
        self.reload_patients()

    def restart_watcher(self):
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher.wait(3000)
            self._watcher = None

        config = labgate_config.load_labgate_action_setting()
        incoming_folder = config.get("incoming_folder", "").strip()
        if incoming_folder == "":
            self.append_log("Watcher nicht gestartet: kein eingehender Ordner konfiguriert.")
            return

        self._watcher = LabGateReturnWatcher(self)
        self._watcher.processed.connect(self.on_return_processed)
        self._watcher.start()
        self.append_log("Rücklauf-Watcher gestartet.")

    def on_return_processed(self, success, payload):
        if isinstance(payload, dict):
            for event_message in payload.get("events", []):
                self.append_log(str(event_message))
            message = payload.get("message", "Rücklauf verarbeitet.")
        else:
            message = str(payload)
        self.append_log(message)
        self.reload_patients()

    def closeEvent(self, event):
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher.wait(3000)
            self._watcher = None
        super().closeEvent(event)
