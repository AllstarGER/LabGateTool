import configparser
import os

from cryptography.fernet import Fernet

import app_paths


SETTINGS_FILE_NAME = "settings.ini"
LABGATE_SETTINGS_FILE_NAME = "labgate_action.ini"
_FERNET_KEY = "kIDfMk5kxCTTJ5FnNKxLsVKz-DUQVWwocZcERmsRRlA="


def _find_settings_path(file_name):
    return app_paths.find_external_path(file_name) or app_paths.get_preferred_external_path(file_name)


def get_main_settings_path():
    return _find_settings_path(SETTINGS_FILE_NAME)


def get_labgate_settings_path():
    return _find_settings_path(LABGATE_SETTINGS_FILE_NAME)


def _safe_decrypt_or_raw(value):
    if value in (None, ""):
        return ""
    try:
        cipher = Fernet(_FERNET_KEY)
        return cipher.decrypt(str(value).encode()).decode()
    except Exception:
        return str(value)


def load_db_setting():
    settings_obj = {
        "host": "",
        "dbname": "",
        "user": "",
        "password": "",
    }
    config = configparser.ConfigParser()
    config.read(get_main_settings_path())
    if not config.has_section("Database"):
        return settings_obj
    settings_obj["host"] = config.get("Database", "host", fallback="")
    settings_obj["dbname"] = config.get("Database", "dbname", fallback="")
    settings_obj["user"] = config.get("Database", "user", fallback="")
    settings_obj["password"] = _safe_decrypt_or_raw(config.get("Database", "password", fallback=""))
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
