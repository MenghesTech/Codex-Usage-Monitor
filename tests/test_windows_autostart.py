from __future__ import annotations

import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

from src import windows_autostart


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


class FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.fail_writes = False

    def OpenKey(self, root, path, reserved=0, access=0):
        if not self.values:
            raise FileNotFoundError
        return FakeKey(self)

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        return FakeKey(self)

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name]

    def SetValueEx(self, key, name, reserved, value_type, value):
        if self.fail_writes:
            raise PermissionError("denied")
        self.values[name] = (value, value_type)

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_enable_disable_and_initial_state():
    registry = FakeRegistry()
    command = '"C:\\Program Files\\Codex Monitor\\monitor.exe"'

    assert windows_autostart.is_enabled(command, registry=registry) is False
    assert windows_autostart.enable(command, registry=registry) == command
    assert windows_autostart.is_enabled(command, registry=registry) is True
    windows_autostart.disable(registry=registry)
    assert windows_autostart.is_enabled(command, registry=registry) is False


def test_python_command_quotes_paths_with_spaces():
    command = windows_autostart.build_startup_command(
        executable=r"C:\Program Files\Python\python.exe",
        launcher=r"C:\My Projects\Codex Monitor\launch.py",
        frozen=False,
    )

    assert command == subprocess.list2cmdline(
        [
            r"C:\Program Files\Python\pythonw.exe",
            r"C:\My Projects\Codex Monitor\launch.py",
        ]
    )


def test_frozen_command_uses_only_packaged_executable():
    command = windows_autostart.build_startup_command(
        executable=r"C:\Program Files\Codex Monitor\monitor.exe",
        frozen=True,
    )
    assert command == subprocess.list2cmdline(
        [r"C:\Program Files\Codex Monitor\monitor.exe"]
    )


def test_frozen_command_ignores_meipass_and_launcher(tmp_path, monkeypatch):
    executable = tmp_path / "Portable App" / "CodexUsageMonitor.exe"
    meipass = tmp_path / "temporary bundle extraction"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    command = windows_autostart.build_startup_command()

    assert command == subprocess.list2cmdline([str(executable.resolve())])
    assert "python" not in command.lower()
    assert "launch.py" not in command.lower()
    assert str(meipass) not in command


def test_write_error_is_reported_without_false_enabled_state():
    registry = FakeRegistry()
    registry.fail_writes = True

    with pytest.raises(windows_autostart.AutostartError):
        windows_autostart.enable("command", registry=registry)

    assert windows_autostart.is_enabled("command", registry=registry) is False


def test_external_different_value_is_not_our_autostart():
    registry = FakeRegistry()
    registry.values[windows_autostart.VALUE_NAME] = (
        '"C:\\Other App\\other.exe"',
        registry.REG_SZ,
    )

    assert windows_autostart.is_enabled("our-command", registry=registry) is False
    assert windows_autostart.read_registered_command(registry=registry) != "our-command"


def test_real_hkcu_round_trip_uses_isolated_temporary_value():
    value_name = f"CodexUsageMonitorTest-{uuid.uuid4()}"
    command = '"C:\\Temporary Test Path\\codex-monitor.exe" --test-only'
    try:
        assert windows_autostart.read_registered_command(value_name=value_name) is None
        windows_autostart.enable(command, value_name=value_name)
        assert windows_autostart.read_registered_command(value_name=value_name) == command
        assert windows_autostart.is_enabled(command, value_name=value_name) is True
    finally:
        windows_autostart.disable(value_name=value_name)
    assert windows_autostart.read_registered_command(value_name=value_name) is None


def test_context_menu_reloads_real_state_each_time():
    from PySide6.QtWidgets import QApplication

    from src.widget import ClickableLabel, MenuPanel

    app = QApplication.instance() or QApplication([])
    states = iter([False, True])
    noop = lambda: None
    owner = SimpleNamespace(
        compact=False,
        topmost=False,
        anchor="free",
        menu=None,
        hide=noop,
        toggle_compact=noop,
        toggle_topmost=noop,
        toggle_autostart=noop,
        refresh=noop,
        close_app=noop,
        autostart_enabled=lambda: next(states),
    )

    first = MenuPanel(owner)
    first_text = next(
        label.text()
        for label in first.findChildren(ClickableLabel)
        if "Abrir al iniciar Windows" in label.text()
    )
    first.close()
    second = MenuPanel(owner)
    second_text = next(
        label.text()
        for label in second.findChildren(ClickableLabel)
        if "Abrir al iniciar Windows" in label.text()
    )
    second.close()

    assert "✓" not in first_text
    assert "✓" in second_text
    app.processEvents()
