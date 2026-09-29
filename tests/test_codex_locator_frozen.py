from __future__ import annotations

import sys

import pytest

from src import codex_locator
from src.codex_locator import CodexNotFoundError, find_codex


def test_frozen_mode_still_honors_external_codex_exe(tmp_path, monkeypatch):
    external = tmp_path / "installed Codex" / "codex.exe"
    external.parent.mkdir()
    external.write_bytes(b"test executable placeholder")
    monkeypatch.setenv("CODEX_EXE", str(external))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    assert find_codex() == external


def test_missing_codex_raises_specific_technical_state(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_EXE", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(codex_locator.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(codex_locator.shutil, "which", lambda _name: None)

    with pytest.raises(CodexNotFoundError):
        find_codex()
