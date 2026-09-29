from __future__ import annotations

import json

import pytest

from src import settings


PREFERENCES = {
    "compact": True,
    "topmost": False,
    "anchor": "br",
    "x": -240,
    "y": 315,
}


def test_migrates_known_preferences_from_legacy_file(tmp_path):
    old = tmp_path / ".codex-usage-monitor-qt-v062.json"
    new = tmp_path / "LocalAppData" / "Codex Usage Monitor" / "settings.json"
    old.write_text(json.dumps({**PREFERENCES, "obsolete": "discard me"}), encoding="utf-8")

    loaded = settings.load_settings(new, old)

    assert loaded == PREFERENCES
    assert json.loads(new.read_text(encoding="utf-8")) == PREFERENCES
    assert old.exists()


def test_new_settings_take_priority_over_legacy(tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new" / "settings.json"
    new.parent.mkdir()
    old.write_text(json.dumps(PREFERENCES), encoding="utf-8")
    current = {**PREFERENCES, "compact": False, "x": 999}
    new.write_text(json.dumps(current), encoding="utf-8")

    assert settings.load_settings(new, old) == current


def test_corrupt_legacy_uses_defaults_and_is_not_destroyed(tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new" / "settings.json"
    original = b"{not valid json"
    old.write_bytes(original)

    assert settings.load_settings(new, old) == {}
    assert old.read_bytes() == original
    assert not new.exists()


def test_atomic_write_replaces_verified_file_and_leaves_no_temp(tmp_path):
    destination = tmp_path / "settings.json"
    destination.write_text('{"compact": false}', encoding="utf-8")

    settings.atomic_write_settings(destination, PREFERENCES)

    assert settings.load_settings(destination, tmp_path / "missing") == PREFERENCES
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


def test_failed_replace_keeps_previous_settings_and_cleans_temp(
    tmp_path, monkeypatch
):
    destination = tmp_path / "settings.json"
    original = b'{"compact": false}\n'
    destination.write_bytes(original)

    def fail_replace(_source, _destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr(settings.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        settings.atomic_write_settings(destination, PREFERENCES)

    assert destination.read_bytes() == original
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


@pytest.mark.parametrize("name", ["compact", "topmost", "anchor", "x", "y"])
def test_each_active_preference_is_preserved(name, tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new" / "settings.json"
    old.write_text(json.dumps(PREFERENCES), encoding="utf-8")

    assert settings.load_settings(new, old)[name] == PREFERENCES[name]


@pytest.mark.parametrize("anchor", ["free", "tl", "tr", "bl", "br", "cl", "cr"])
def test_every_active_anchor_is_migrated(anchor, tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new" / "settings.json"
    old.write_text(json.dumps({**PREFERENCES, "anchor": anchor}), encoding="utf-8")

    assert settings.load_settings(new, old)["anchor"] == anchor
