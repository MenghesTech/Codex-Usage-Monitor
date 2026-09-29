from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_final_version_is_consistent_across_runtime_and_build_metadata():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    client = (ROOT / "src" / "codex_client.py").read_text(encoding="utf-8")
    version_info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "CodexUsageMonitor.iss").read_text(
        encoding="utf-8"
    )

    assert 'setApplicationVersion("1.0.0")' in main
    assert '"version": "1.0.0"' in client
    assert "filevers=(1, 0, 0, 0)" in version_info
    assert "prodvers=(1, 0, 0, 0)" in version_info
    assert "StringStruct('FileVersion', '1.0.0.0')" in version_info
    assert "StringStruct('ProductVersion', '1.0.0')" in version_info
    assert '#define AppVersion "1.0.0"' in installer
    assert "VersionInfoVersion=1.0.0.0" in installer
