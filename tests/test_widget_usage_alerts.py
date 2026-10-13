from __future__ import annotations

import json
import gc
import weakref

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon

from src.usage_model import Usage, Window


class FakeWindowsTray:
    def __init__(self):
        self.messages = []
        self.fail = False

    def showMessage(self, *args):
        if self.fail:
            raise RuntimeError("simulated tray failure")
        self.messages.append(args)


def snapshot(primary, secondary):
    return Usage(
        True,
        Window(primary, 300, 2_000_000_000),
        Window(secondary, 10080, 2_000_500_000),
        "plus", None, 0,
    )


def make_monitor(tmp_path, monkeypatch):
    from src import widget

    class IdleClient:
        def __init__(self, notification_handler=None):
            pass

        def close(self):
            pass

    monkeypatch.setattr(widget, "CodexClient", IdleClient)
    monkeypatch.setattr(widget, "user_config_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(widget.Monitor, "setup_tray", lambda self: None)
    monkeypatch.setattr(widget.Monitor, "_apply_topmost", lambda self: True)
    monitor = widget.Monitor()
    monitor.refresh_timer.stop()
    monitor.tick_timer.stop()
    monitor.tray = FakeWindowsTray()
    return monitor


def dispose(monitor, app):
    monitor.hide()
    monitor.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def test_simulated_windows_notification_groups_both_windows(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        for window in ("primary", "secondary"):
            for threshold in (80, 90, 95):
                monitor.set_alert_enabled(window, threshold, True)
        monitor.apply_usage(snapshot(79, 79))
        monitor.apply_usage(snapshot(96, 96))
        assert len(monitor.tray.messages) == 1
        title, message, icon, timeout = monitor.tray.messages[0]
        assert "alerta de uso" in title
        assert "5 horas: 80 %, 90 %, 95 % (96 % usado)" in message
        assert "7 días: 80 %, 90 %, 95 % (96 % usado)" in message
        assert icon == QSystemTrayIcon.Information
        assert timeout == 5000
        monitor.apply_usage(snapshot(96, 96))
        assert len(monitor.tray.messages) == 1
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["state"]["primary"]["notified"] == [80, 90, 95]
    finally:
        dispose(monitor, app)


def test_tray_action_opens_dialog_and_cancel_preserves_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        tray_menu = QMenu()
        monitor.add_alert_action(tray_menu)
        assert [action.text() for action in tray_menu.actions()] == ["Configurar alertas…"]
        monitor.alert_action.trigger()
        dialog = monitor.alert_settings_dialog
        assert dialog.windowTitle() == "Configurar alertas"
        assert dialog.isVisible()
        assert not dialog.active_checkbox.isChecked()
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        assert "Configurar alertas" not in texts
        assert "Recibe avisos al alcanzar los porcentajes indicados (1–100 %)." in texts
        for window in ("primary", "secondary"):
            assert [field.placeholderText() for field in dialog.fields[window]] == [
                "Aviso 1", "Aviso 2", "Aviso 3",
            ]
            assert all(field.isEnabled() and not field.isReadOnly()
                       for field in dialog.fields[window])
        dialog.active_checkbox.setChecked(True)
        dialog.fields["primary"][0].setText("90")
        dialog.cancel_button.click()
        assert monitor.alerts.thresholds("primary") == []
        from src.widget import MenuPanel
        panel = MenuPanel(monitor)
        alert_label = next(label for label in panel.findChildren(QLabel)
                           if "Configurar alertas" in label.text())
        alert_label.clicked.emit()
        assert monitor.alert_settings_dialog.isVisible()
        monitor.alert_settings_dialog.cancel_button.click()
        panel.close()
    finally:
        dispose(monitor, app)


def test_temporary_save_failure_retries_without_losing_other_preferences(tmp_path, monkeypatch):
    from src import widget

    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        monitor.set_alert_enabled("primary", 80, True)
        monitor.apply_usage(snapshot(79, 79))
        real_save = widget.save_settings

        def fail_once(*args):
            monkeypatch.setattr(widget, "save_settings", real_save)
            raise OSError("temporary write failure")

        monkeypatch.setattr(widget, "save_settings", fail_once)
        monitor.apply_usage(snapshot(80, 79))
        assert monitor.tray.messages == []
        assert len(monitor.alerts.queued_alerts()) == 1
        monitor.apply_usage(snapshot(80, 79))
        assert len(monitor.tray.messages) == 1
        monitor.apply_usage(snapshot(80, 79))
        assert len(monitor.tray.messages) == 1
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["state"]["primary"]["notified"] == [80]
        assert saved["usage_alerts"]["queued"] == []
        assert saved["compact"] is monitor.compact
        assert saved["topmost"] is monitor.topmost
    finally:
        dispose(monitor, app)
    restarted = make_monitor(tmp_path, monkeypatch)
    try:
        restarted.apply_usage(snapshot(80, 79))
        assert restarted.tray.messages == []
    finally:
        dispose(restarted, app)


def test_tray_failure_keeps_durable_outbox_until_restart(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        monitor.set_alert_enabled("primary", 80, True)
        monitor.apply_usage(snapshot(79, 79))
        monitor.tray.fail = True
        monitor.apply_usage(snapshot(80, 79))
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert len(saved["usage_alerts"]["queued"]) == 1
        assert monitor.tray.messages == []
    finally:
        dispose(monitor, app)
    restarted = make_monitor(tmp_path, monkeypatch)
    try:
        restarted.apply_usage(snapshot(80, 79))
        assert len(restarted.tray.messages) == 1
        restarted.apply_usage(snapshot(80, 79))
        assert len(restarted.tray.messages) == 1
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["queued"] == []
        assert saved["usage_alerts"]["state"]["primary"]["notified"] == [80]
    finally:
        dispose(restarted, app)


def test_acknowledgement_save_failure_does_not_repeat_in_running_widget(tmp_path, monkeypatch):
    from src import widget

    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        monitor.set_alert_enabled("primary", 80, True)
        monitor.apply_usage(snapshot(79, 79))
        real_save = widget.save_settings
        calls = 0

        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("acknowledgement write failure")
            return real_save(*args)

        monkeypatch.setattr(widget, "save_settings", fail_second)
        monitor.apply_usage(snapshot(80, 79))
        assert len(monitor.tray.messages) == 1
        assert len(monitor.alerts.queued_alerts()) == 1
        monitor.apply_usage(snapshot(80, 79))
        assert len(monitor.tray.messages) == 1
        assert monitor.alerts.queued_alerts() == []
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["queued"] == []
    finally:
        dispose(monitor, app)


def test_alert_action_signal_does_not_keep_destroyed_monitor_alive(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    menu = QMenu()
    monitor.add_alert_action(menu)
    action = monitor.alert_action
    action.trigger()
    # Let the startup single-shot callback run before disposing the widget.
    QTest.qWait(200)
    dispose(monitor, app)
    reference = weakref.ref(monitor)
    del action, menu, monitor
    gc.collect()
    assert reference() is None


def test_dialog_save_sort_validate_and_restart(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        dialog = monitor.open_alert_settings()
        dialog.active_checkbox.setChecked(True)
        for field, value in zip(dialog.fields["primary"], ("95", "30", "1")):
            field.setText(value)
        dialog.fields["secondary"][0].setText("100")
        dialog.save_button.click()
        assert not dialog.isVisible()
        assert monitor.alerts.thresholds("primary") == [1, 30, 95]
        assert monitor.alerts.thresholds("secondary") == [100]
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["active"] is True
        assert saved["usage_alerts"]["thresholds"]["primary"] == [1, 30, 95]
    finally:
        dispose(monitor, app)
    restarted = make_monitor(tmp_path, monkeypatch)
    try:
        dialog = restarted.open_alert_settings()
        assert dialog.active_checkbox.isChecked()
        assert [field.text() for field in dialog.fields["primary"]] == ["1", "30", "95"]
        dialog.fields["primary"][1].setText("1")
        dialog.save_button.click()
        assert dialog.isVisible()
        assert "no repitas" in dialog.error_label.text()
        dialog.fields["primary"][1].setText("0")
        dialog.save_button.click()
        assert "del 1 al 100" in dialog.error_label.text()
        dialog.fields["primary"][1].setText("101")
        dialog.save_button.click()
        assert "del 1 al 100" in dialog.error_label.text()
        dialog.fields["primary"][1].setText("abc")
        dialog.save_button.click()
        assert "del 1 al 100" in dialog.error_label.text()
        dialog.fields["primary"][1].setText("")
        dialog.active_checkbox.setChecked(False)
        assert all(field.isEnabled() and not field.isReadOnly()
                   for window in ("primary", "secondary")
                   for field in dialog.fields[window])
        dialog.save_button.click()
        assert not restarted.alerts.is_active()
        assert restarted.alerts.thresholds("primary") == [1, 95]
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["usage_alerts"]["active"] is False
        assert saved["usage_alerts"]["thresholds"]["primary"] == [1, 95]
    finally:
        dispose(restarted, app)


def test_dialog_save_failure_preserves_existing_settings(tmp_path, monkeypatch):
    from src import widget

    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    try:
        original = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        dialog = monitor.open_alert_settings()
        dialog.active_checkbox.setChecked(True)
        dialog.fields["primary"][0].setText("42")
        real_save = widget.save_settings
        monkeypatch.setattr(widget, "save_settings", lambda *args: (_ for _ in ()).throw(OSError("full")))
        dialog.save_button.click()
        assert dialog.isVisible()
        assert "No se pudo guardar" in dialog.error_label.text()
        assert monitor.alerts.thresholds("primary") == []
        assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8")) == original
        monkeypatch.setattr(widget, "save_settings", real_save)
        dialog.save_button.click()
        assert monitor.alerts.thresholds("primary") == [42]
    finally:
        dispose(monitor, app)


def test_closed_widget_menu_does_not_keep_destroyed_monitor_alive(tmp_path, monkeypatch):
    from src.widget import MenuPanel

    app = QApplication.instance() or QApplication([])
    monitor = make_monitor(tmp_path, monkeypatch)
    panel = MenuPanel(monitor)
    monitor.menu = panel
    panel.close()
    QTest.qWait(200)
    dispose(monitor, app)
    reference = weakref.ref(monitor)
    del panel, monitor
    gc.collect()
    assert reference() is None
