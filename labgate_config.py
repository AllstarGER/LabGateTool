import configparser
import os

import app_paths


SETTINGS_FILE_NAME = "settings.ini"
LABGATE_SETTINGS_FILE_NAME = "labgate_action.ini"
DEFAULT_LAB_MARKER_CONTENT = "Laborergebnis liegt vor"


def _find_settings_path(file_name):
    return app_paths.find_external_path(file_name) or app_paths.get_preferred_external_path(file_name)


def get_main_settings_path():
    return _find_settings_path(SETTINGS_FILE_NAME)


def get_labgate_settings_path():
    return _find_settings_path(LABGATE_SETTINGS_FILE_NAME)


def load_backend_setting():
    """Backend-Adresse und Desktop-API-Key aus Umgebung bzw. settings.ini.

    Die LabGate-Aktion greift nicht mehr direkt auf die Portal-Datenbank zu
    (frueher ueber die Datenbanksektion der settings.ini): sie spricht wie der PMS-Client die
    Portal-API unter [Backend]/base_url an.
    """
    settings_obj = {
        "base_url": "",
        "desktop_api_key": "",
    }

    for env_name, key in (
        ("HC_BACKEND_BASE_URL", "base_url"),
        ("HC_DESKTOP_API_KEY", "desktop_api_key"),
        ("DESKTOP_API_KEY", "desktop_api_key"),
    ):
        env_value = str(os.getenv(env_name, "") or "").strip()
        if env_value and not settings_obj[key]:
            settings_obj[key] = env_value

    config = configparser.ConfigParser()
    if not config.read(get_main_settings_path()):
        return settings_obj
    if config.has_section("Backend"):
        if not settings_obj["base_url"]:
            settings_obj["base_url"] = config.get("Backend", "base_url", fallback="").strip()
        if not settings_obj["desktop_api_key"]:
            settings_obj["desktop_api_key"] = config.get("Backend", "desktop_api_key", fallback="").strip()
    return settings_obj


def load_labgate_action_setting():
    settings_obj = {
        "outgoing_folder": "",
        "outgoing_filename": "pat.gdt",
        "incoming_folder": "",
        "incoming_filename_filter": "*.gdt",
    }

    config = configparser.ConfigParser()
    config.read(get_labgate_settings_path())
    if config.has_section("LabGateAction"):
        settings_obj["outgoing_folder"] = config.get("LabGateAction", "outgoing_folder", fallback=settings_obj["outgoing_folder"])
        settings_obj["outgoing_filename"] = config.get("LabGateAction", "outgoing_filename", fallback=settings_obj["outgoing_filename"])
        settings_obj["incoming_folder"] = config.get("LabGateAction", "incoming_folder", fallback=settings_obj["incoming_folder"])
        settings_obj["incoming_filename_filter"] = config.get(
            "LabGateAction",
            "incoming_filename_filter",
            fallback=settings_obj["incoming_filename_filter"],
        )
        return settings_obj

    fallback_config = configparser.ConfigParser()
    fallback_config.read(get_main_settings_path())
    if fallback_config.has_section("LabGateAction"):
        settings_obj["outgoing_folder"] = fallback_config.get("LabGateAction", "outgoing_folder", fallback=settings_obj["outgoing_folder"])
        settings_obj["outgoing_filename"] = fallback_config.get("LabGateAction", "outgoing_filename", fallback=settings_obj["outgoing_filename"])
        settings_obj["incoming_folder"] = fallback_config.get("LabGateAction", "incoming_folder", fallback=settings_obj["incoming_folder"])
        settings_obj["incoming_filename_filter"] = fallback_config.get(
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
