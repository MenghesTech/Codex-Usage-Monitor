from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .app_paths import legacy_user_config_path, user_config_path


logger = logging.getLogger(__name__)
VALID_ANCHORS = {"free", "tl", "tr", "bl", "br", "cl", "cr"}


class SettingsError(ValueError):
    pass


def validate_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SettingsError("Settings must be a JSON object")

    result: dict[str, Any] = {}
    for name in ("compact", "topmost"):
        candidate = value.get(name)
        if isinstance(candidate, bool):
            result[name] = candidate

    anchor = value.get("anchor")
    if isinstance(anchor, str) and anchor in VALID_ANCHORS:
        result["anchor"] = anchor

    for name in ("x", "y"):
        candidate = value.get(name)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            result[name] = candidate
    return result


def _read_validated(path: Path) -> dict[str, Any]:
    return validate_settings(json.loads(path.read_text(encoding="utf-8")))


def atomic_write_settings(path: Path, settings: Mapping[str, Any]) -> None:
    if not isinstance(settings, Mapping):
        raise SettingsError("Settings must be a mapping")
    document = dict(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if json.loads(path.read_text(encoding="utf-8")) != document:
            raise SettingsError("Written settings could not be verified")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_settings(
    path: Path | None = None,
    legacy_path: Path | None = None,
) -> dict[str, Any]:
    destination = path or user_config_path()
    legacy = legacy_path or legacy_user_config_path()

    if destination.exists():
        try:
            return _read_validated(destination)
        except (OSError, UnicodeError, json.JSONDecodeError, SettingsError):
            logger.warning("Current settings are invalid; using defaults")
            return {}

    if not legacy.exists():
        return {}

    try:
        migrated = _read_validated(legacy)
        atomic_write_settings(destination, migrated)
        return _read_validated(destination)
    except (OSError, UnicodeError, json.JSONDecodeError, SettingsError):
        logger.warning("Legacy settings could not be migrated; using defaults")
        return {}


def save_settings(settings: Mapping[str, Any], path: Path | None = None) -> None:
    atomic_write_settings(path or user_config_path(), settings)
