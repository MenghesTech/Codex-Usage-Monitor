"""Small Qt editor for local usage alert thresholds."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from .usage_alerts import MAX_THRESHOLDS, WINDOWS, normalize_alert_settings


class AlertSettingsDialog(QDialog):
    submitted = Signal(bool, object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        current = normalize_alert_settings(settings)
        self.setWindowTitle("Configurar alertas")
        self.setModal(True)
        self.setFixedWidth(340)
        self.setStyleSheet("""
            QDialog { background: #141d2a; color: #f4f7fb; }
            QLabel, QCheckBox { color: #f4f7fb; font: 10pt 'Segoe UI'; }
            QLineEdit {
                background: #223247; color: #f4f7fb; border: 1px solid #4c5e76;
                border-radius: 5px; padding: 6px; font: 10pt 'Segoe UI';
            }
            QLineEdit:focus { border-color: #63adff; }
            QPushButton {
                background: #28415e; color: #f4f7fb; border: 1px solid #4c5e76;
                border-radius: 5px; padding: 7px 12px; font: 10pt 'Segoe UI';
            }
            QPushButton:hover { background: #355878; }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.active_checkbox = QCheckBox("Activar alertas")
        self.active_checkbox.setChecked(current["active"])
        layout.addWidget(self.active_checkbox)
        description = QLabel("Recibe avisos al alcanzar los porcentajes indicados (1–100 %).")
        description.setWordWrap(True)
        description.setStyleSheet("color: #9aa7b8; font: 9pt 'Segoe UI';")
        layout.addWidget(description)

        self.fields: dict[str, list[QLineEdit]] = {}
        for name, (_, label) in WINDOWS.items():
            layout.addWidget(QLabel(f"Límite de {label}"))
            row = QHBoxLayout()
            self.fields[name] = []
            for index in range(MAX_THRESHOLDS):
                field = QLineEdit()
                field.setPlaceholderText(f"Aviso {index + 1}")
                field.setInputMethodHints(Qt.ImhDigitsOnly)
                levels = current["thresholds"][name]
                if index < len(levels):
                    field.setText(str(levels[index]))
                row.addWidget(field)
                self.fields[name].append(field)
            layout.addLayout(row)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ff7480; font: 9pt 'Segoe UI';")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancelar")
        self.save_button = QPushButton("Guardar")
        self.save_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._submit)

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)

    @Slot()
    def _submit(self) -> None:
        selected: dict[str, list[int]] = {}
        for name, (_, label) in WINDOWS.items():
            levels = []
            for field in self.fields[name]:
                value = field.text().strip()
                if not value:
                    continue
                if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 100:
                    self.show_error(f"{label}: introduce enteros del 1 al 100.")
                    return
                levels.append(int(value))
            if len(set(levels)) != len(levels):
                self.show_error(f"{label}: no repitas porcentajes.")
                return
            selected[name] = sorted(levels)
        self.show_error("")
        self.submitted.emit(self.active_checkbox.isChecked(), selected)
