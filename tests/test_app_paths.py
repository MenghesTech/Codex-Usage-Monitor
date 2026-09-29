from __future__ import annotations

import sys
from pathlib import Path

from src import app_paths


def test_source_resource_path_does_not_depend_on_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert app_paths.resource_path("assets", "icon.ico") == (
        Path(app_paths.__file__).resolve().parent.parent / "assets" / "icon.ico"
    )


def test_frozen_resources_use_meipass(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle resources"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    assert app_paths.resource_path("assets", "icon.ico") == (
        bundle.resolve() / "assets" / "icon.ico"
    )


def test_user_config_uses_local_appdata_and_is_never_inside_bundle(
    tmp_path, monkeypatch
):
    bundle = tmp_path / "bundle"
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    assert app_paths.user_config_path() == (
        local_appdata / "Codex Usage Monitor" / "settings.json"
    )
    assert bundle not in app_paths.user_config_path().parents


def test_legacy_path_uses_profile_without_a_hardcoded_username(
    tmp_path, monkeypatch
):
    profile = tmp_path / "arbitrary profile"
    monkeypatch.setattr(app_paths.Path, "home", classmethod(lambda cls: profile))

    assert app_paths.legacy_user_config_path() == (
        profile / ".codex-usage-monitor-qt-v062.json"
    )
