from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


class WindowsTopmostError(OSError):
    pass


def _functions():
    if sys.platform != "win32":
        raise OSError("Win32 topmost is only available on Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    long_ptr = ctypes.c_ssize_t
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        get_window_long_ptr = user32.GetWindowLongPtrW
        set_window_long_ptr = user32.SetWindowLongPtrW
    else:
        get_window_long_ptr = user32.GetWindowLongW
        set_window_long_ptr = user32.SetWindowLongW

    get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    get_window_long_ptr.restype = long_ptr
    set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, long_ptr]
    set_window_long_ptr.restype = long_ptr

    set_window_pos = user32.SetWindowPos
    set_window_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    set_window_pos.restype = wintypes.BOOL
    return get_window_long_ptr, set_window_long_ptr, set_window_pos


def _hwnd(value: int) -> wintypes.HWND:
    return wintypes.HWND(value)


HWND_TOPMOST = _hwnd(-1)
HWND_NOTOPMOST = _hwnd(-2)


def extended_style(hwnd: int) -> int:
    get_window_long_ptr, _, _ = _functions()
    ctypes.set_last_error(0)
    value = get_window_long_ptr(_hwnd(hwnd), GWL_EXSTYLE)
    error = ctypes.get_last_error()
    if value == 0 and error:
        raise WindowsTopmostError(error, ctypes.FormatError(error))
    return int(value)


def is_topmost(hwnd: int) -> bool:
    return bool(extended_style(hwnd) & WS_EX_TOPMOST)


def apply_topmost(hwnd: int, enabled: bool) -> bool:
    get_window_long_ptr, set_window_long_ptr, set_window_pos = _functions()
    native_hwnd = _hwnd(hwnd)

    ctypes.set_last_error(0)
    style = get_window_long_ptr(native_hwnd, GWL_EXSTYLE)
    error = ctypes.get_last_error()
    if style == 0 and error:
        raise WindowsTopmostError(error, ctypes.FormatError(error))

    wanted_style = (int(style) | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    if wanted_style != int(style):
        ctypes.set_last_error(0)
        previous = set_window_long_ptr(native_hwnd, GWL_EXSTYLE, wanted_style)
        error = ctypes.get_last_error()
        if previous == 0 and error:
            raise WindowsTopmostError(error, ctypes.FormatError(error))

    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
    ctypes.set_last_error(0)
    ok = set_window_pos(
        native_hwnd,
        HWND_TOPMOST if enabled else HWND_NOTOPMOST,
        0,
        0,
        0,
        0,
        flags,
    )
    if not ok:
        error = ctypes.get_last_error()
        raise WindowsTopmostError(error, ctypes.FormatError(error))

    actual = is_topmost(hwnd)
    if actual != enabled:
        raise WindowsTopmostError(
            0,
            "SetWindowPos returned success but WS_EX_TOPMOST did not match",
        )
    return actual
