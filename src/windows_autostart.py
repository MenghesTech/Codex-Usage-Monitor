from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover - the application targets Windows
    winreg = None  # type: ignore[assignment]


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CodexUsageMonitor"


class AutostartError(RuntimeError):
    pass


def build_startup_command(
    *,
    executable: str | Path | None = None,
    frozen: bool | None = None,
    launcher: str | Path | None = None,
) -> str:
    executable_path = Path(executable or sys.executable).resolve()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen

    if is_frozen:
        arguments = [str(executable_path)]
    else:
        if executable_path.name.lower() != "pythonw.exe":
            executable_path = executable_path.with_name("pythonw.exe")
        launcher_path = Path(launcher).resolve() if launcher else (
            Path(__file__).resolve().parent.parent / "launch.py"
        )
        arguments = [str(executable_path), str(launcher_path)]

    return subprocess.list2cmdline(arguments)


def _registry(registry: Any | None):
    selected = registry if registry is not None else winreg
    if selected is None:
        raise AutostartError("El registro de Windows no está disponible")
    return selected


def read_registered_command(
    *, value_name: str = VALUE_NAME, registry: Any | None = None
) -> str | None:
    reg = _registry(registry)
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_QUERY_VALUE) as key:
            value, value_type = reg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AutostartError("No se pudo leer el autostart de Windows") from exc

    if value_type != reg.REG_SZ or not isinstance(value, str):
        return None
    return value


def is_enabled(
    command: str | None = None,
    *,
    value_name: str = VALUE_NAME,
    registry: Any | None = None,
) -> bool:
    expected = command if command is not None else build_startup_command()
    return read_registered_command(value_name=value_name, registry=registry) == expected


def enable(
    command: str | None = None,
    *,
    value_name: str = VALUE_NAME,
    registry: Any | None = None,
) -> str:
    reg = _registry(registry)
    expected = command if command is not None else build_startup_command()
    try:
        with reg.CreateKeyEx(
            reg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            reg.KEY_SET_VALUE | reg.KEY_QUERY_VALUE,
        ) as key:
            reg.SetValueEx(key, value_name, 0, reg.REG_SZ, expected)
    except OSError as exc:
        raise AutostartError("No se pudo activar el autostart de Windows") from exc

    if not is_enabled(expected, value_name=value_name, registry=reg):
        raise AutostartError("Windows no conservó el comando de autostart esperado")
    return expected


def disable(
    *, value_name: str = VALUE_NAME, registry: Any | None = None
) -> None:
    reg = _registry(registry)
    try:
        with reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            reg.KEY_SET_VALUE | reg.KEY_QUERY_VALUE,
        ) as key:
            try:
                reg.DeleteValue(key, value_name)
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AutostartError("No se pudo desactivar el autostart de Windows") from exc

    if read_registered_command(value_name=value_name, registry=reg) is not None:
        raise AutostartError("Windows conservó el valor de autostart")
