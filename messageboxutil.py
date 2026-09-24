from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMessageBox, QSizePolicy


_PATCHED = False


def _resize_message_box(box: QMessageBox):
    box.setSizeGripEnabled(True)
    box.setMinimumSize(900, 320)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout = box.layout()
    if layout is not None:
        try:
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)
            layout.setColumnMinimumWidth(1, 760)
        except Exception:
            pass

    for label_name in ("qt_msgbox_label", "qt_msgbox_informativelabel"):
        label = box.findChild(QLabel, label_name)
        if label is None:
            continue
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(760)

    box.setStyleSheet("QTextEdit{min-width: 620px; min-height: 160px;}")


def _wrap_static_message_box(icon: QMessageBox.Icon):
    def _wrapped(parent, title, text, buttons=QMessageBox.StandardButton.Ok, default_button=QMessageBox.StandardButton.NoButton):
        box = QMessageBox(icon, str(title), str(text), buttons, parent)
        if default_button != QMessageBox.StandardButton.NoButton:
            box.setDefaultButton(default_button)
        _resize_message_box(box)
        return QMessageBox.StandardButton(box.exec())

    return _wrapped


def install_resizable_message_boxes():
    global _PATCHED
    if _PATCHED:
        return
    QMessageBox.information = staticmethod(_wrap_static_message_box(QMessageBox.Icon.Information))
    QMessageBox.warning = staticmethod(_wrap_static_message_box(QMessageBox.Icon.Warning))
    QMessageBox.critical = staticmethod(_wrap_static_message_box(QMessageBox.Icon.Critical))
    _PATCHED = True
