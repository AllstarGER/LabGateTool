#!/bin/bash
# Baut die Windows-EXE der LabGate-Aktion (PyInstaller onefile).
#
# Auf einem Linux-Rechner laeuft der Build ueber Wine mit einer Windows-Python-
# Installation. Auf dem Portal-Host ist das der Prefix /root/.wine-healthcard-release
# mit C:\Python311 (PyQt6, loguru, PyInstaller). Auf Windows reicht:
#   python -m pip install -r requirements.txt && bash scripts/build_windows_exe.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SPEC_FILE="${SPEC_FILE:-labgate_action_onefile.spec}"

cd "$PROJECT_DIR"

if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
    PYTHON_BIN="${PYTHON_BIN:-python}"
    "$PYTHON_BIN" -m PyInstaller --clean -y "$SPEC_FILE"
else
    WINE_BIN="${WINE_BIN:-wine}"
    WINDOWS_PYTHON="${WINDOWS_PYTHON:-C:\\Python311\\python.exe}"
    if ! command -v "$WINE_BIN" >/dev/null 2>&1; then
        echo "Wine nicht gefunden ($WINE_BIN). Auf Windows direkt ausfuehren." >&2
        exit 1
    fi
    if [[ -z "${WINEPREFIX:-}" ]]; then
        echo "WINEPREFIX muss auf den Windows-Prefix zeigen (z. B. /root/.wine-healthcard-release)." >&2
        exit 1
    fi
    # Wine braucht echte stdio-Handles: Ausgabe deshalb ueber eine Pipe, nicht
    # direkt in eine Datei umleiten.
    "$WINE_BIN" "$WINDOWS_PYTHON" -m PyInstaller --clean -y "$SPEC_FILE" 2>&1 | cat
fi

echo "Fertig: $PROJECT_DIR/dist/${SPEC_FILE%.spec}.exe"
