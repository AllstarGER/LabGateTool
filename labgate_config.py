import configparser
import json
import os

from loguru import logger

import app_paths


SETTINGS_FILE_NAME = "settings.ini"
LABGATE_SETTINGS_FILE_NAME = "labgate_action.ini"
FORMS_CACHE_FILE_NAME = "forms_manifest_cache.json"
DEFAULT_LAB_MARKER_CONTENT = "Laborergebnis liegt vor"

BACKEND_ENV_NAMES = ("HC_BACKEND_BASE_URL",)
API_KEY_ENV_NAMES = ("HC_DESKTOP_API_KEY", "DESKTOP_API_KEY")
SETTINGS_FILE_ENV_NAMES = ("HC_SETTINGS_FILE",)

_logged_settings_source = None


def _env_value(names):
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _read_config_file(config, path):
    """Liest settings.ini wie der PMS-Client (UTF-8 mit BOM oder UTF-16)."""
    if not path or not os.path.exists(path):
        return []
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return config.read_file(handle)
        except (UnicodeError, configparser.Error, OSError):
            continue
    try:
        return config.read(path)
    except Exception as error:
        logger.error(f"LabGate settings could not be read: path={path} error={error}")
        return []


def normalize_backend_base_url(value):
    backend = str(value or "").strip()
    if not backend:
        return ""
    if backend.startswith(("http://", "https://")):
        return backend.rstrip("/")
    if backend.startswith("//"):
        return ("https:" + backend).rstrip("/")
    if backend.startswith(("localhost", "127.0.0.1")):
        return ("http://" + backend).rstrip("/")
    return ("https://" + backend).rstrip("/")


def _own_settings_path():
    return app_paths.get_preferred_external_path(SETTINGS_FILE_NAME)


def get_settings_source():
    """Ermittelt, welche settings.ini verwendet wird.

    Das Werkzeug wird in den PMS-Ordner gelegt: dann liegt die settings.ini des
    PMS direkt neben der EXE und wird mitgelesen (Abschnitt [Backend] samt
    desktop_api_key). Reihenfolge wie in app_paths: EXE-Ordner, Arbeitsverzeichnis,
    uebergeordnete Ordner, Projektordner.
    """
    global _logged_settings_source

    env_path = _env_value(SETTINGS_FILE_ENV_NAMES)
    if env_path and os.path.exists(env_path):
        source = {"path": os.path.abspath(env_path), "origin": "HC_SETTINGS_FILE"}
    else:
        source = None
        exe_dir = os.path.abspath(app_paths.get_executable_dir())
        cwd = os.path.abspath(os.getcwd())
        for candidate_dir in app_paths.get_external_search_dirs():
            candidate = os.path.join(candidate_dir, SETTINGS_FILE_NAME)
            if not os.path.exists(candidate):
                continue
            candidate = os.path.abspath(candidate)
            if os.path.dirname(candidate) == exe_dir:
                origin = "PMS-Ordner (neben der EXE)"
            elif os.path.dirname(candidate) == cwd:
                origin = "Arbeitsverzeichnis"
            else:
                origin = "uebergeordneter Ordner"
            source = {"path": candidate, "origin": origin}
            break
        if source is None:
            source = {"path": _own_settings_path(), "origin": "wird neu angelegt"}

    if source["path"] != _logged_settings_source:
        _logged_settings_source = source["path"]
        logger.info(f"LabGate settings file: {source['path']} ({source['origin']})")
    return source


def get_main_settings_path():
    return get_settings_source()["path"]


def get_labgate_settings_path():
    return app_paths.find_external_path(LABGATE_SETTINGS_FILE_NAME) or app_paths.get_preferred_external_path(LABGATE_SETTINGS_FILE_NAME)


def _backend_setting_from_config(config):
    if not config.has_section("Backend"):
        return "", ""
    base_url = normalize_backend_base_url(config.get("Backend", "base_url", fallback=""))
    api_key = config.get("Backend", "desktop_api_key", fallback="").strip()
    return base_url, api_key


def _backend_base_url_from_cache(settings_path):
    """Wie im PMS: letzter bekannter Backend-Link aus dem Formular-Cache."""
    cache_path = os.path.join(os.path.dirname(settings_path), FORMS_CACHE_FILE_NAME)
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return normalize_backend_base_url(payload.get("backend_base_link", ""))


def load_backend_setting():
    """Backend-Adresse und Desktop-API-Key (Umgebung hat Vorrang, sonst settings.ini)."""
    source = get_settings_source()
    settings_obj = {
        "base_url": normalize_backend_base_url(_env_value(BACKEND_ENV_NAMES)),
        "desktop_api_key": _env_value(API_KEY_ENV_NAMES),
        "source": source,
    }

    config = configparser.ConfigParser()
    _read_config_file(config, source["path"])
    config_base_url, config_api_key = _backend_setting_from_config(config)
    if not settings_obj["base_url"]:
        settings_obj["base_url"] = config_base_url
    if not settings_obj["desktop_api_key"]:
        settings_obj["desktop_api_key"] = config_api_key
    if not settings_obj["base_url"]:
        settings_obj["base_url"] = _backend_base_url_from_cache(source["path"])
    return settings_obj


def load_labgate_action_setting():
    settings_obj = {
        "outgoing_folder": "",
        "outgoing_filename": "pat.gdt",
        "incoming_folder": "",
        "incoming_filename_filter": "*.gdt",
    }

    config = configparser.ConfigParser()
    _read_config_file(config, get_labgate_settings_path())
    if not config.has_section("LabGateAction"):
        # Fallback wie bisher: derselbe Abschnitt in der settings.ini des PMS.
        config = configparser.ConfigParser()
        _read_config_file(config, get_main_settings_path())
    if not config.has_section("LabGateAction"):
        return settings_obj

    settings_obj["outgoing_folder"] = config.get("LabGateAction", "outgoing_folder", fallback=settings_obj["outgoing_folder"])
    settings_obj["outgoing_filename"] = config.get("LabGateAction", "outgoing_filename", fallback=settings_obj["outgoing_filename"])
    settings_obj["incoming_folder"] = config.get("LabGateAction", "incoming_folder", fallback=settings_obj["incoming_folder"])
    settings_obj["incoming_filename_filter"] = config.get(
        "LabGateAction",
        "incoming_filename_filter",
        fallback=settings_obj["incoming_filename_filter"],
    )
    return settings_obj


def save_labgate_action_setting(labgate_info):
    config = configparser.ConfigParser()
    config["LabGateAction"] = {
        "outgoing_folder": str(labgate_info.get("outgoing_folder", "")),
        "outgoing_filename": str(labgate_info.get("outgoing_filename", "pat.gdt")),
        "incoming_folder": str(labgate_info.get("incoming_folder", "")),
        "incoming_filename_filter": str(labgate_info.get("incoming_filename_filter", "*.gdt")),
    }
    settings_path = get_labgate_settings_path()
    settings_dir = os.path.dirname(settings_path)
    if settings_dir:
        os.makedirs(settings_dir, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as configfile:
        config.write(configfile)
    return True
