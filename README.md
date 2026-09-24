# LabGate Action Onefile

Standalone client for the LabGate action: it receives laboratory return files (GDT),
writes GDT request files and reports the results back to the portal.

Since the move to the portal API this tool **has no direct database access anymore**.
All job, marker and case data is read and written through the desktop API of the
PMS backend (`/api/desktop/...`), exactly like the PMS client does.

## Run from source

```powershell
python -m pip install -r requirements.txt
python labgate_action_main.py
```

## Configuration

`settings.ini` (next to the executable or in the working directory):

```ini
[Backend]
base_url = https://portal.example
desktop_api_key = <desktop api key>
```

* `base_url` - portal address; the desktop API lives under `<base_url>/api/desktop`.
* `desktop_api_key` - desktop API key of the practice.
* The environment variables `HC_BACKEND_BASE_URL`, `HC_DESKTOP_API_KEY` (or
  `DESKTOP_API_KEY`) override the file values.
* A missing or wrong configuration is reported when the tool starts; no credentials
  are stored in this repository.

`labgate_action.ini` (settings for the action itself):

```ini
[LabGateAction]
outgoing_folder = C:\\LabGate\\out
outgoing_filename = pat.gdt
incoming_folder = C:\\LabGate\\in
incoming_filename_filter = *.gdt
```

## Lab notification

For every case and lab slot (1-3) one or more employees can be selected
("Mitarbeiter fuer Laborbenachrichtigung"). The selection is stored per case and slot
in the portal.

As soon as a return file arrives and the job is imported, exactly these employees are
informed: the tool creates a lab report alert (type 15) for the selected employees, so
they see it in the PMS notification list and can open the assignment. Slots without a
marker or without selected employees are skipped; a failing notification is logged and
never blocks the import itself.

## Tests

```powershell
python -m pytest
```

## Build

```powershell
python -m PyInstaller labgate_action_onefile.spec
```

The resulting executable is named `labgate_action_onefile.exe`.
