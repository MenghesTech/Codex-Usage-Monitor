from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

from src.codex_locator import CodexNotFoundError
from src.usage_model import Usage, Window


def wait_until(app, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Qt state did not update before timeout")


def destroy_widget(window, app):
    from PySide6.QtCore import QCoreApplication, QEvent

    window.hide()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


class SequencedClient:
    def __init__(self, notification_handler=None):
        self.notification_handler = notification_handler
        self.outcome = "missing"

    def usage(self):
        if self.outcome == "missing":
            raise CodexNotFoundError("controlled missing executable")
        if self.outcome == "error":
            raise OSError("controlled app-server failure")
        return Usage(
            allowed=True,
            primary=Window(12, 300, 2_000_000_000),
            secondary=Window(34, 10080, 2_000_500_000),
            plan="plus",
            reached_type=None,
            reset_credits=0,
        )

    def close(self):
        pass


def create_monitor(tmp_path, monkeypatch):
    from src import widget

    monkeypatch.setattr(widget, "CodexClient", SequencedClient)
    monkeypatch.setattr(widget, "user_config_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(widget.Monitor, "setup_tray", lambda self: None)
    monkeypatch.setattr(widget.Monitor, "_apply_topmost", lambda self: True)
    return widget.Monitor()


def test_missing_codex_clears_data_and_recovers_when_codex_appears(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    window = create_monitor(tmp_path, monkeypatch)
    try:
        window.refresh()
        wait_until(app, lambda: "Codex no encontrado" in window.status.text())
        assert window.p1[1].text() == "—"
        assert window.p2[1].text() == "—"

        window.client.outcome = "usage"
        window.refresh()
        wait_until(app, lambda: window.p1[1].text() == "12%")
        assert window.p2[1].text() == "34%"
        assert "Disponible" in window.status.text()
    finally:
        window.refresh_timer.stop()
        window.tick_timer.stop()
        destroy_widget(window, app)


def test_located_codex_failure_remains_real_error(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = create_monitor(tmp_path, monkeypatch)
    try:
        window.client.outcome = "error"
        window.refresh()
        wait_until(app, lambda: "Error de Codex" in window.status.text())
        assert window.p1[1].text() == "—"
        assert window.p2[1].text() == "—"
    finally:
        window.refresh_timer.stop()
        window.tick_timer.stop()
        destroy_widget(window, app)
