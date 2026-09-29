from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CodexUsageMonitor"
LEGACY_CONFIG_FILENAME = ".codex-usage-monitor-qt-v062.json"
SETTINGS_DIRNAME = "Codex Usage Monitor"
WS_EX_TOPMOST = 0x00000008

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

if ctypes.sizeof(ctypes.c_void_p) == 8:
    get_window_long = user32.GetWindowLongPtrW
else:
    get_window_long = user32.GetWindowLongW
get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
get_window_long.restype = ctypes.c_ssize_t


def registry_value() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, value_type = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    return value if value_type == winreg.REG_SZ else None


def set_registry_value(value: str | None) -> None:
    if value is None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
        return
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, value)


def windows_for_pid(pid: int, visible_only: bool = True) -> list[int]:
    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd, _lparam):
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and (not visible_only or user32.IsWindowVisible(hwnd)):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return found


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    value = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.left, value.top, value.right, value.bottom


def window_size(hwnd: int) -> tuple[int, int]:
    left, top, right, bottom = window_rect(hwnd)
    return right - left, bottom - top


def is_topmost(hwnd: int) -> bool:
    return bool(get_window_long(wintypes.HWND(hwnd), -20) & WS_EX_TOPMOST)


def wait_until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise TimeoutError("Portable smoke-test timeout")


def main_window(pid: int) -> int | None:
    for hwnd in windows_for_pid(pid):
        if window_size(hwnd) in ((290, 175), (290, 65)):
            return hwnd
    return None


def click(x: int, y: int, *, right=False) -> None:
    user32.SetCursorPos(x, y)
    down, up = ((0x0008, 0x0010) if right else (0x0002, 0x0004))
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.25)


def click_pin(hwnd: int) -> None:
    left, top, _right, _bottom = window_rect(hwnd)
    click(left + 243, top + 19)


def popup_for_pid(pid: int, main_hwnd: int) -> int | None:
    for hwnd in windows_for_pid(pid):
        if hwnd == main_hwnd:
            continue
        width, height = window_size(hwnd)
        if 210 <= width <= 250 and height >= 200:
            return hwnd
    return None


def context_item(pid: int, main_hwnd: int, center_y: int) -> None:
    left, top, right, bottom = window_rect(main_hwnd)
    user32.SetForegroundWindow(wintypes.HWND(main_hwnd))
    click((left + right) // 2, (top + bottom) // 2, right=True)
    popup = wait_until(lambda: popup_for_pid(pid, main_hwnd), 5)
    pleft, ptop, pright, _pbottom = window_rect(popup)
    click((pleft + pright) // 2, ptop + center_y)


def exit_from_menu(pid: int, main_hwnd: int) -> None:
    context_item(pid, main_hwnd, 213)


def capture(hwnd: int, destination: Path) -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    left, top, right, bottom = window_rect(hwnd)
    screen = app.screenAt(QPoint((left + right) // 2, (top + bottom) // 2))
    screen = screen or app.primaryScreen()
    pixmap = screen.grabWindow(0, left, top, right - left, bottom - top)
    if pixmap.isNull() or not pixmap.save(str(destination), "PNG"):
        raise RuntimeError("No se pudo capturar la ventana portable")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    executable = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else root / "dist" / "CodexUsageMonitor" / "CodexUsageMonitor.exe"
    )
    if not executable.is_file():
        raise FileNotFoundError(executable)

    legacy_config = Path.home() / LEGACY_CONFIG_FILENAME
    config = Path(os.environ["LOCALAPPDATA"]) / SETTINGS_DIRNAME / "settings.json"
    original_legacy_config = (
        legacy_config.read_bytes() if legacy_config.exists() else None
    )
    original_config = config.read_bytes() if config.exists() else None
    original_registry = registry_value()
    old_cursor = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(old_cursor))
    processes: list[subprocess.Popen] = []
    result: dict[str, object] = {}
    screenshot = root / "build" / "portable-rate-limits.png"

    try:
        set_registry_value(None)
        config.unlink(missing_ok=True)
        legacy_config.write_text(
            json.dumps(
                {
                    "topmost": False,
                    "compact": False,
                    "anchor": "free",
                    "x": 500,
                    "y": 300,
                }
            ),
            encoding="utf-8",
        )
        with tempfile.TemporaryDirectory() as other_directory:
            first = subprocess.Popen([str(executable)], cwd=other_directory)
            processes.append(first)
            hwnd = wait_until(lambda: main_window(first.pid), 20)
            wait_until(config.is_file, 5)
            migrated = json.loads(config.read_text(encoding="utf-8"))
            result["settings_migrated"] = all(
                migrated.get(name) == expected
                for name, expected in {
                    "topmost": False,
                    "compact": False,
                    "anchor": "free",
                    "x": 500,
                    "y": 300,
                }.items()
            )
            result["legacy_settings_preserved"] = legacy_config.is_file()
            result["cwd_outside_workspace"] = Path(other_directory) != root
            result["first_window_size"] = window_size(hwnd)
            result["topmost_initial"] = is_topmost(hwnd)

            time.sleep(7)
            capture(hwnd, screenshot)
            result["rate_limits_screenshot"] = str(screenshot.relative_to(root))

            click_pin(hwnd)
            result["topmost_on"] = is_topmost(hwnd)
            click_pin(hwnd)
            result["topmost_off"] = not is_topmost(hwnd)
            context_item(first.pid, hwnd, 83)
            result["menu_topmost_on"] = is_topmost(hwnd)
            context_item(first.pid, hwnd, 83)
            result["menu_topmost_off"] = not is_topmost(hwnd)

            left, top, right, bottom = window_rect(hwnd)
            start_x, start_y = (left + right) // 2, top + 120
            user32.SetCursorPos(start_x, start_y)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.SetCursorPos(start_x + 80, start_y + 40)
            time.sleep(0.2)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.3)
            result["drag_moved"] = window_rect(hwnd)[:2] != (left, top)

            user32.SetWindowPos(hwnd, None, 5, 5, 0, 0, 0x0001 | 0x0004 | 0x0010)
            click(150, 120)
            result["snap_position"] = window_rect(hwnd)[:2]

            context_item(first.pid, hwnd, 114)
            expected_command = subprocess.list2cmdline([str(executable.resolve())])
            registered = registry_value()
            result["autostart_exact_exe"] = registered == expected_command
            result["autostart_has_python"] = bool(
                registered and "python" in registered.lower()
            )
            result["autostart_has_meipass"] = bool(
                registered and "_MEI" in registered
            )

            context_item(first.pid, hwnd, 52)
            result["compact_before_restart"] = window_size(hwnd)
            click_pin(hwnd)
            result["topmost_before_restart"] = is_topmost(hwnd)
            exit_from_menu(first.pid, hwnd)
            first.wait(10)
            result["first_exit_code"] = first.returncode

            second = subprocess.Popen(registered, cwd=other_directory)
            processes.append(second)
            hwnd2 = wait_until(lambda: main_window(second.pid), 20)
            result["registered_command_started"] = True
            result["restored_compact"] = window_size(hwnd2)
            result["restored_topmost"] = bool(
                wait_until(lambda: is_topmost(hwnd2), 5)
            )
            result["restored_snap_position"] = window_rect(hwnd2)[:2]

            duplicate = subprocess.Popen([str(executable)], cwd=other_directory)
            duplicate.wait(10)
            result["second_instance_exit_code"] = duplicate.returncode
            result["first_instance_alive"] = second.poll() is None

            left, top, right, _bottom = window_rect(hwnd2)
            click(right - 14, top + 19)
            result["hidden_by_x"] = wait_until(
                lambda: not bool(user32.IsWindowVisible(hwnd2)), 5
            )
            restore = subprocess.Popen([str(executable)], cwd=other_directory)
            restore.wait(10)
            result["restore_instance_exit_code"] = restore.returncode
            result["shown_by_second_instance"] = wait_until(
                lambda: bool(user32.IsWindowVisible(hwnd2)), 5
            )

            context_item(second.pid, hwnd2, 114)
            result["autostart_removed"] = registry_value() is None
            context_item(second.pid, hwnd2, 52)
            result["full_before_exit"] = window_size(hwnd2)
            if is_topmost(hwnd2):
                click_pin(hwnd2)
            exit_from_menu(second.pid, hwnd2)
            second.wait(10)
            result["final_exit_code"] = second.returncode
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(5)
                except subprocess.TimeoutExpired:
                    process.kill()
        set_registry_value(original_registry)
        if original_legacy_config is None:
            legacy_config.unlink(missing_ok=True)
        else:
            legacy_config.write_bytes(original_legacy_config)
        if original_config is None:
            config.unlink(missing_ok=True)
        else:
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_bytes(original_config)
        user32.SetCursorPos(old_cursor.x, old_cursor.y)

    result["registry_restored"] = registry_value() == original_registry
    result["config_restored"] = (
        config.read_bytes() == original_config if original_config is not None else not config.exists()
    )
    result["legacy_config_restored"] = (
        legacy_config.read_bytes() == original_legacy_config
        if original_legacy_config is not None
        else not legacy_config.exists()
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
