# LabGate Action Onefile

Standalone source repository for the LabGate action client used to receive laboratory return files and create GDT request files.

## Run from source

```powershell
python -m pip install -r requirements.txt
python labgate_action_main.py
```

The application reads its LabGate/database settings through the existing settings loader. No credentials are stored in this repository.

## Tests

```powershell
python -m pytest
```

## Build

```powershell
python -m PyInstaller labgate_action_onefile.spec
```

The resulting executable is named `labgate_action_onefile.exe`.
