import os
import sys

from runtime_bootstrap import maybe_relaunch

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if maybe_relaunch(project_dir=PROJECT_DIR):
    raise SystemExit(0)

from PyQt6.QtWidgets import QApplication

import labgate_logutil
import messageboxutil
import safeio
from ui.labgateaction import LabGateActionWindow


safeio.install_safe_print()


def main():
    os.makedirs("log", exist_ok=True)
    labgate_logutil.log_config()
    app = QApplication(sys.argv)
    app.setApplicationName("LabGate-Aktions-Tool")
    messageboxutil.install_resizable_message_boxes()

    window = LabGateActionWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
