"""Isolated Windows tray notification harness; never connects to Codex.

Run from the repository root with a Python environment containing PySide6:
    python tests/manual_windows_notifications.py
    python tests/manual_windows_notifications.py --self-test
    python tests/manual_windows_notifications.py --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QLabel, QPlainTextEdit, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from src import widget
from src.settings import load_settings, save_settings
from src.usage_model import Usage, Window


class OfflineClient:
    def __init__(self, notification_handler=None):
        pass

    def close(self):
        pass

    def usage(self):
        raise RuntimeError("The notification harness cannot query Codex")


class Harness:
    def __init__(self, app: QApplication, silent: bool):
        self.app = app
        self.silent = silent
        self.root = Path(tempfile.mkdtemp(prefix="codex-usage-alert-visual-"))
        self.settings_path = self.root / "settings.json"
        self.settings_path.write_text(
            json.dumps({"compact": False, "topmost": False, "anchor": "free"}),
            encoding="utf-8",
        )
        self.notices: list[tuple[str, str]] = []
        self.on_event = lambda message: None
        now = int(time.time())
        self.primary_deadline = now + 300 * 60
        self.secondary_deadline = now + 10080 * 60
        self.last_usage: Usage | None = None
        self.originals = {
            "CodexClient": widget.CodexClient,
            "QSystemTrayIcon": widget.QSystemTrayIcon,
            "user_config_path": widget.user_config_path,
            "load_settings": widget.load_settings,
            "save_settings": widget.save_settings,
        }

        harness = self

        class RecordingTray(QSystemTrayIcon):
            def showMessage(self, *args, **kwargs):
                result = None if harness.silent else super().showMessage(*args, **kwargs)
                harness.notices.append((args[0], args[1]))
                harness.on_event(f"Qt showMessage #{len(harness.notices)}: {args[1]}")
                return result

        class OfflineMonitor(widget.Monitor):
            def refresh(self):
                # Timers and the tray's Refresh action must never query Codex.
                return None

            def _apply_topmost(self, *args, **kwargs):
                return True

            def autostart_enabled(self):
                return False

            def toggle_autostart(self):
                return None

        def safe_path(path):
            if Path(path).resolve() != self.settings_path.resolve():
                raise RuntimeError("Refusing to access settings outside the harness")

        def safe_load(path):
            safe_path(path)
            return load_settings(path, legacy_path=self.root / "unused-legacy.json")

        def safe_save(settings, path=None):
            safe_path(path)
            return save_settings(settings, path)

        widget.CodexClient = OfflineClient
        widget.QSystemTrayIcon = RecordingTray
        widget.user_config_path = lambda: self.settings_path
        widget.load_settings = safe_load
        widget.save_settings = safe_save
        self.monitor_type = OfflineMonitor
        self.monitor = self._create_monitor()

    def _create_monitor(self):
        monitor = self.monitor_type()
        monitor.tray.setToolTip("Codex Usage Monitor [ARNÉS AISLADO]")
        return monitor

    def _dispose_monitor(self):
        self.monitor.refresh_timer.stop()
        self.monitor.tick_timer.stop()
        if self.monitor.menu is not None:
            self.monitor.menu.close()
        if self.monitor.alert_settings_dialog is not None:
            self.monitor.alert_settings_dialog.close()
        self.monitor.tray_menu.close()
        self.monitor.tray.hide()
        self.monitor.hide()
        self.monitor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def restart(self):
        self._dispose_monitor()
        self.monitor = self._create_monitor()
        self.on_event("Widget reiniciado desde el settings.json temporal")

    def configure(self, active: bool, primary: tuple[int, ...],
                  secondary: tuple[int, ...]):
        self.monitor.alert_action.trigger()
        dialog = self.monitor.alert_settings_dialog
        assert dialog.isVisible()
        dialog.active_checkbox.setChecked(active)
        for name, levels in (("primary", primary), ("secondary", secondary)):
            for index, field in enumerate(dialog.fields[name]):
                field.setText(str(levels[index]) if index < len(levels) else "")
        dialog.save_button.click()
        assert not dialog.isVisible(), dialog.error_label.text()
        self.app.processEvents()

    def emit(self, primary: int | None, secondary: int | None):
        sample = Usage(
            True,
            Window(primary, 300, self.primary_deadline) if primary is not None else None,
            Window(secondary, 10080, self.secondary_deadline)
            if secondary is not None else None,
            "plus", None, 0,
        )
        self.last_usage = sample
        self.monitor.apply_usage(sample)
        self.on_event(f"Lectura simulada: 5 h={primary}, 7 d={secondary}")
        self.app.processEvents()

    def repeat(self):
        if self.last_usage is not None:
            self.monitor.apply_usage(self.last_usage)
            self.on_event("Lectura repetida")
            self.app.processEvents()

    def new_cycle(self):
        self.primary_deadline += 300 * 60
        self.secondary_deadline += 10080 * 60
        self.emit(5, 5)
        self.on_event("Nuevo ciclo simulado; ambos consumos al 5 %")

    def close(self):
        try:
            self._dispose_monitor()
        finally:
            for name, original in self.originals.items():
                setattr(widget, name, original)
            shutil.rmtree(self.root)


class Controls(QWidget):
    def __init__(self, harness: Harness):
        super().__init__()
        self.harness = harness
        self.setWindowTitle("Prueba aislada de alertas de Windows")
        self.resize(570, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"PySide6 {PYSIDE_VERSION} | Bandeja: "
            f"{'sí' if QSystemTrayIcon.isSystemTrayAvailable() else 'NO'} | "
            f"Mensajes: {'sí' if QSystemTrayIcon.supportsMessages() else 'NO'}"
        ))
        layout.addWidget(QLabel(f"Configuración aislada: {harness.settings_path}"))
        layout.addWidget(QLabel(
            "Abre «Configurar alertas…» desde la bandeja o el widget. Activa las "
            "alertas, introduce hasta tres porcentajes (1–100) por ventana y "
            "pulsa Guardar. Los botones solo cambian lecturas simuladas."
        ))
        grid = QGridLayout()
        buttons = [
            ("79 % / 79 %", lambda: harness.emit(79, 79)),
            ("80 % / 79 %", lambda: harness.emit(80, 79)),
            ("90 % / 79 %", lambda: harness.emit(90, 79)),
            ("95 % / 79 %", lambda: harness.emit(95, 79)),
            ("96 % / 96 %", lambda: harness.emit(96, 96)),
            ("Nuevo ciclo: 5 % / 5 %", harness.new_cycle),
            ("Repetir lectura", harness.repeat),
            ("Datos ausentes", lambda: harness.emit(None, None)),
            ("Reiniciar widget", harness.restart),
            ("Ocultar / mostrar widget", lambda: harness.monitor.toggle_visibility()),
        ]
        for index, (label, callback) in enumerate(buttons):
            button = QPushButton(label)
            button.clicked.connect(callback)
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        harness.on_event = self.log.appendPlainText

    def closeEvent(self, event):
        super().closeEvent(event)
        QApplication.quit()


def self_test(harness: Harness):
    assert not harness.monitor.alerts.is_active()
    harness.emit(96, 96)
    harness.configure(True, (95, 80, 90), (95, 80, 90))
    assert harness.monitor.alerts.thresholds("primary") == [80, 90, 95]
    harness.emit(96, 96)
    assert len(harness.notices) == 0  # Activation above limits is not retroactive.

    harness.new_cycle()
    harness.emit(79, 79)
    for used, expected in ((80, 1), (90, 2), (95, 3)):
        harness.emit(used, 79)
        assert len(harness.notices) == expected
    harness.repeat()
    assert len(harness.notices) == 3
    harness.restart()
    harness.repeat()
    assert len(harness.notices) == 3

    harness.new_cycle()
    harness.emit(79, 79)
    harness.emit(96, 96)
    assert len(harness.notices) == 4
    assert "5 horas: 80 %, 90 %, 95 %" in harness.notices[-1][1]
    assert "7 días: 80 %, 90 %, 95 %" in harness.notices[-1][1]

    harness.configure(False, (80, 90, 95), (80, 90, 95))
    assert harness.monitor.alerts.thresholds("primary") == [80, 90, 95]
    harness.new_cycle()
    harness.emit(79, 79)
    harness.emit(96, 96)
    assert len(harness.notices) == 4

    harness.configure(True, (80,), ())
    harness.new_cycle()
    harness.emit(79, 79)
    harness.monitor.hide()
    harness.emit(80, 79)
    assert not harness.monitor.isVisible()
    assert len(harness.notices) == 5
    saved = json.loads(harness.settings_path.read_text(encoding="utf-8"))
    assert saved["usage_alerts"]["state"]["primary"]["notified"] == [80]
    assert saved["usage_alerts"]["queued"] == []
    print("SELF_TEST_OK: menus, no retroactive alerts, exact thresholds, grouping, "
          "restart, reset, disable, hidden tray, persistence")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="exercise Qt integration without showing Windows notifications")
    parser.add_argument("--smoke", action="store_true",
                        help="open and close the native controls without sending notifications")
    args = parser.parse_args()
    app = QApplication([])
    app.setApplicationName("Codex Usage Monitor")
    app.setQuitOnLastWindowClosed(False)
    harness = Harness(app, silent=args.self_test)
    try:
        if args.self_test:
            self_test(harness)
            return 0
        controls = Controls(harness)
        controls.show()
        if args.smoke:
            app.processEvents()
            assert controls.isVisible()
            QTimer.singleShot(300, controls.close)
        return app.exec()
    finally:
        harness.close()


if __name__ == "__main__":
    raise SystemExit(main())
