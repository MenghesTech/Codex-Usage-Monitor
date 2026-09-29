from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "installer" / "CodexUsageMonitor.iss"
APP_ID = "{5C6581F9-7DA6-4269-B760-9FE3799FABB7}"


def installer_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_installer_has_stable_version_independent_app_id():
    text = installer_text()
    assert '#define AppIdValue "' + APP_ID + '"' in text
    assert "AppId={{5C6581F9-7DA6-4269-B760-9FE3799FABB7}" in text
    assert "0.9.0" not in APP_ID
    assert '#define AppVersion "1.0.0"' in text
    assert "VersionInfoVersion=1.0.0.0" in text


def test_installer_is_per_user_and_consumes_only_portable_build():
    text = installer_text()
    assert "PrivilegesRequired=lowest" in text
    assert "DefaultDirName={localappdata}\\Programs\\{#AppName}" in text
    assert 'Source: "..\\dist\\CodexUsageMonitor\\*"' in text
    for forbidden in (".venv", "tests\\", "src\\", "auth.json", "codex.exe"):
        assert forbidden not in text.lower()


def test_installer_shortcuts_launch_and_close_application_contract():
    text = installer_text()
    assert "CloseApplications=yes" in text
    assert "CloseApplicationsFilter={#AppExeName}" in text
    assert 'Name: "desktopicon"' in text
    assert "Flags: unchecked" in text
    assert 'Name: "{autoprograms}\\{#AppName}"' in text
    run_line = next(line for line in text.splitlines() if line.startswith("Filename:"))
    assert "postinstall" in run_line
    assert "unchecked" not in run_line


def test_autostart_migration_and_uninstall_are_strictly_scoped():
    text = installer_text()
    assert "RunValueName = 'CodexUsageMonitor'" in text
    assert "TryParseCodexMonitorCommand" in text
    assert "CompareText(ExtractFileName(ExecutablePath), '{#AppExeName}')" in text
    assert "if Remainder <> '' then" in text
    assert "SameExecutablePath(ExistingExecutable, InstalledExecutable)" in text
    assert "RegDeleteValue(HKCU, RunKey, RunValueName)" in text
