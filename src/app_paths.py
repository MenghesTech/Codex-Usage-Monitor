from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_DIRNAME = "Codex Usage Monitor"
SETTINGS_FILENAME = "settings.json"
LEGACY_CONFIG_FILENAME = ".codex-usage-monitor-qt-v062.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_path() -> Path:
    return Path(sys.executable).resolve()


def bundle_root() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def local_app_data_path() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"


def user_config_path() -> Path:
    return local_app_data_path() / APP_DATA_DIRNAME / SETTINGS_FILENAME


def legacy_user_config_path() -> Path:
    return Path.home() / LEGACY_CONFIG_FILENAME
