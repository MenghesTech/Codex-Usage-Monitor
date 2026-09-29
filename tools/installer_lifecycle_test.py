from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path


APP_NAME = "Codex Usage Monitor"
APP_VERSION = "1.0.0"
APP_EXE = "CodexUsageMonitor.exe"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "CodexUsageMonitor"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
LEGACY_CONFIG_NAME = ".codex-usage-monitor-qt-v062.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def query_value(root, key_path: str, name: str):
    try:
        with winreg.OpenKey(root, key_path) as key:
            return winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        return None


def restore_value(root, key_path: str, name: str, saved) -> None:
    if saved is None:
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        return
    value, value_type = saved
    with winreg.CreateKeyEx(root, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, value_type, value)


def set_run_command(command: str) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)


def run_command(args: list[str], timeout: float = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def user_shell_folder(name: str) -> Path:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    value = query_value(winreg.HKEY_CURRENT_USER, key_path, name)
    if value is None:
        raise RuntimeError(f"Could not resolve user shell folder {name}")
    return Path(os.path.expandvars(value[0]))


def uninstall_entries() -> list[tuple[str, dict[str, str]]]:
    found: list[tuple[str, dict[str, str]]] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        return found
    with root:
        index = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(root, subkey_name) as subkey:
                    values = {}
                    for name in ("DisplayName", "DisplayVersion", "InstallLocation"):
                        try:
                            values[name] = winreg.QueryValueEx(subkey, name)[0]
                        except FileNotFoundError:
                            pass
            except OSError:
                continue
            if values.get("DisplayName") == APP_NAME:
                found.append((subkey_name, values))
    return found


def wait_until(predicate, timeout: float = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def audit_installed(install_dir: Path) -> dict[str, object]:
    files = [path for path in install_dir.rglob("*") if path.is_file()]
    forbidden_names = {"auth.json", "codex.exe"}
    forbidden_suffixes = {".py", ".pyc", ".log", ".tmp"}
    forbidden_parts = {"tests", ".venv", "__pycache__", ".pytest_cache"}
    bad_files = [
        str(path.relative_to(install_dir))
        for path in files
        if path.name.lower() in forbidden_names
        or path.suffix.lower() in forbidden_suffixes
        or any(part.lower() in forbidden_parts for part in path.parts)
    ]
    needles = {
        "personal_path": str(Path.home()).encode("utf-8"),
        "auth_json": b"auth.json",
        "account_id": b'"accountId"',
        "consume_endpoint": b"account/rateLimitResetCredit/consume",
    }
    hits: dict[str, list[str]] = {name: [] for name in needles}
    for path in files:
        data = path.read_bytes().lower()
        for name, needle in needles.items():
            if needle.lower() in data:
                hits[name].append(str(path.relative_to(install_dir)))
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "forbidden_files": bad_files,
        "content_hits": hits,
    }


def silent_setup(path: Path) -> None:
    run_command(
        [
            str(path),
            "/SP-",
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/NORESTARTAPPLICATIONS",
            "/TASKS=desktopicon",
        ]
    )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    setup_final = root / "installer" / "output" / f"CodexUsageMonitor-Setup-v{APP_VERSION}.exe"
    setup_rc1 = (
        root.parent
        / "Codex-Usage-Monitor-v1.0.0-rc1"
        / "installer"
        / "output"
        / "CodexUsageMonitor-Setup-v1.0.0-rc1.exe"
    )
    dist_exe = root / "dist" / "CodexUsageMonitor" / APP_EXE
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME
    installed_exe = install_dir / APP_EXE
    legacy_config = Path.home() / LEGACY_CONFIG_NAME
    settings = Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "settings.json"
    start_shortcut = user_shell_folder("Programs") / f"{APP_NAME}.lnk"
    desktop_shortcut = user_shell_folder("Desktop") / f"{APP_NAME}.lnk"

    for required in (setup_final, setup_rc1, dist_exe):
        if not required.is_file():
            raise FileNotFoundError(required)
    if install_dir.exists() or uninstall_entries():
        raise RuntimeError("An installation already exists; refusing to alter it")

    tasklist = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}", "/NH"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if APP_EXE.lower() in tasklist.lower():
        raise RuntimeError(f"{APP_EXE} is already running")

    original_run = query_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE)
    original_legacy = legacy_config.read_bytes() if legacy_config.exists() else None
    original_settings = settings.read_bytes() if settings.exists() else None
    results: dict[str, object] = {}
    process: subprocess.Popen | None = None
    seeded = {
        "x": 500,
        "y": 300,
        "anchor": "free",
        "compact": True,
        "topmost": True,
    }

    try:
        settings.unlink(missing_ok=True)
        legacy_config.write_text(json.dumps(seeded), encoding="utf-8")

        silent_setup(setup_rc1)
        results["rc1_installed"] = installed_exe.is_file()
        entries = uninstall_entries()
        results["rc1_apps_entry_count"] = len(entries)
        results["rc1_display_version"] = (
            entries[0][1].get("DisplayVersion") if len(entries) == 1 else None
        )

        expected_command = subprocess.list2cmdline([str(installed_exe.resolve())])
        set_run_command(expected_command)
        process = subprocess.Popen([str(installed_exe)], cwd=install_dir)
        time.sleep(3)
        process.terminate()
        process.wait(10)
        process = None

        silent_setup(setup_final)
        results["upgrade_installed_exe_exists"] = installed_exe.is_file()
        entries = uninstall_entries()
        results["upgrade_apps_entry_count"] = len(entries)
        results["upgrade_same_install_dir"] = (
            len(entries) == 1
            and Path(entries[0][1].get("InstallLocation", "")) == install_dir
        )
        results["upgrade_display_version"] = (
            entries[0][1].get("DisplayVersion") if len(entries) == 1 else None
        )
        results["start_shortcut_exists"] = start_shortcut.is_file()
        results["optional_desktop_shortcut_exists"] = desktop_shortcut.is_file()
        registered = query_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE)
        results["autostart_preserved"] = bool(
            registered and registered[0] == expected_command
        )

        process = subprocess.Popen([str(installed_exe)], cwd=install_dir)
        if not wait_until(settings.is_file, 15):
            raise RuntimeError("Final version did not preserve migrated settings")
        time.sleep(1)
        process.terminate()
        process.wait(10)
        process = None

        migrated = json.loads(settings.read_text(encoding="utf-8"))
        results["settings_migrated"] = all(
            migrated.get(name) == value for name, value in seeded.items()
        )
        results["legacy_settings_preserved"] = legacy_config.is_file()
        results["new_settings_path"] = str(settings)
        results["installed_exe_sha256"] = sha256(installed_exe)
        results["dist_exe_sha256"] = sha256(dist_exe)
        results["installed_matches_dist"] = (
            results["installed_exe_sha256"] == results["dist_exe_sha256"]
        )
        results["installed_audit"] = audit_installed(install_dir)

        smoke = run_command(
            [sys.executable, str(root / "tools" / "portable_smoke_test.py"), str(installed_exe)]
        )
        results["installed_smoke"] = json.loads(smoke.stdout)

        config_before_uninstall = settings.read_bytes()
        uninstaller = install_dir / "unins000.exe"
        results["uninstaller_exists"] = uninstaller.is_file()
        run_command(
            [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        )
        results["install_dir_removed"] = wait_until(lambda: not install_dir.exists())
        results["apps_entry_removed"] = not uninstall_entries()
        results["start_shortcut_removed"] = not start_shortcut.exists()
        results["desktop_shortcut_removed"] = not desktop_shortcut.exists()
        results["autostart_removed"] = (
            query_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE) is None
        )
        results["settings_preserved_after_uninstall"] = (
            settings.is_file() and settings.read_bytes() == config_before_uninstall
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                process.kill()
        emergency_uninstaller = install_dir / "unins000.exe"
        if emergency_uninstaller.is_file():
            subprocess.run(
                [str(emergency_uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                capture_output=True,
                timeout=180,
            )
        restore_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE, original_run)
        if original_legacy is None:
            legacy_config.unlink(missing_ok=True)
        else:
            legacy_config.write_bytes(original_legacy)
        if original_settings is None:
            settings.unlink(missing_ok=True)
        else:
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_bytes(original_settings)

    results["original_autostart_restored"] = (
        query_value(winreg.HKEY_CURRENT_USER, RUN_KEY, RUN_VALUE) == original_run
    )
    results["original_legacy_restored"] = (
        legacy_config.read_bytes() == original_legacy
        if original_legacy is not None
        else not legacy_config.exists()
    )
    results["original_settings_restored"] = (
        settings.read_bytes() == original_settings
        if original_settings is not None
        else not settings.exists()
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
