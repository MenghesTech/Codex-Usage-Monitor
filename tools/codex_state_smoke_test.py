from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from portable_smoke_test import capture, context_item, main_window, wait_until


def isolated_environment(profile: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("CODEX_EXE", None)
    environment["HOME"] = str(profile)
    environment["USERPROFILE"] = str(profile)
    environment["LOCALAPPDATA"] = str(profile / "AppData" / "Local")
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    # Codex itself may use the normal local authentication it already owns;
    # the monitor never opens or copies those files.
    environment["CODEX_HOME"] = str(Path.home() / ".codex")
    return environment


def stop(process: subprocess.Popen) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            return process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.wait(10)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    executable = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else root / "dist" / "CodexUsageMonitor" / "CodexUsageMonitor.exe"
    )
    real_codex = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) > 2
        else Path(subprocess.check_output(["where.exe", "codex.exe"], text=True).splitlines()[0])
    )
    if not executable.is_file() or not real_codex.is_file():
        raise FileNotFoundError(executable if not executable.is_file() else real_codex)

    output = root / "build"
    output.mkdir(exist_ok=True)
    cursor = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
    results: dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="codex-monitor-state-") as directory:
        temp = Path(directory)
        profile = temp / "profile"
        profile.mkdir()
        environment = isolated_environment(profile)
        process = subprocess.Popen([str(executable)], env=environment, cwd=temp)
        try:
            hwnd = wait_until(lambda: main_window(process.pid), 20)
            time.sleep(2)
            missing_image = output / "codex-not-found.png"
            capture(hwnd, missing_image)
            results["missing_screenshot"] = str(missing_image.relative_to(root))

            destination = (
                profile
                / ".vscode"
                / "extensions"
                / "openai.chatgpt-99.0.0"
                / "bin"
                / "windows-x86_64"
                / "codex.exe"
            )
            destination.parent.mkdir(parents=True)
            os.link(real_codex, destination)
            context_item(process.pid, hwnd, 181)
            time.sleep(8)
            recovered_image = output / "codex-appeared.png"
            capture(hwnd, recovered_image)
            results["appeared_screenshot"] = str(recovered_image.relative_to(root))
            results["process_alive_after_codex_appeared"] = process.poll() is None
        finally:
            results["missing_recovery_exit_code"] = stop(process)

        error_profile = temp / "error-profile"
        error_profile.mkdir()
        error_environment = isolated_environment(error_profile)
        fake_codex = temp / "located-but-broken-codex.exe"
        fake_codex.write_bytes(b"not a Windows executable")
        error_environment["CODEX_EXE"] = str(fake_codex)
        error_process = subprocess.Popen(
            [str(executable)], env=error_environment, cwd=temp
        )
        try:
            error_hwnd = wait_until(lambda: main_window(error_process.pid), 20)
            time.sleep(2)
            error_image = output / "codex-real-error.png"
            capture(error_hwnd, error_image)
            results["error_screenshot"] = str(error_image.relative_to(root))
            results["process_alive_after_real_error"] = error_process.poll() is None
        finally:
            results["error_exit_code"] = stop(error_process)

    ctypes.windll.user32.SetCursorPos(cursor.x, cursor.y)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
