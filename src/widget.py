from __future__ import annotations

import sys
import logging
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QGuiApplication, QIcon, QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame,
    QSystemTrayIcon, QMenu
)

from .codex_client import CodexClient
from .codex_locator import CodexNotFoundError
from .app_paths import user_config_path
from .settings import load_settings, save_settings
from .usage_model import ResetDeadlines, seconds_until
from .window_geometry import anchor_position, recover_position


logger = logging.getLogger(__name__)

FULL = (290, 175)
COMPACT = (290, 65)
RADIUS = 14
MARGIN = 14
SNAP = 30

BG = QColor(10, 18, 29, 242)
HEADER = QColor(15, 29, 45, 246)
BORDER = QColor(73, 94, 119, 210)
TEXT = "#f4f7fb"
MUTED = "#9aa7b8"
BLUE = "#63adff"
GREEN = "#45e66a"
RED = "#ff5263"
AMBER = "#f2b84b"
TRACK = "#2a3442"


def codex_failure_text(kind: str, compact: bool = False) -> str:
    if compact:
        return "● Codex no encontrado" if kind == "not_found" else "● ERROR"
    return "●  Codex no encontrado" if kind == "not_found" else "●  Error de Codex"


class Bridge(QObject):
    usage_ready = Signal(object)
    usage_error = Signal(str)
    rate_limits_updated = Signal()


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class RoundedPanel(QWidget):
    def __init__(self, radius=RADIUS, color=BG, border=BORDER, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.color = color
        self.border = border
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        p.fillPath(path, self.color)
        # All effects stay inside the layered-window bounds.  This avoids
        # UpdateLayeredWindowIndirect failures on Windows caused by graphics
        # effects whose dirty rectangle extends to negative coordinates.
        inner = QRectF(self.rect()).adjusted(2.0, 2.0, -2.0, -2.0)
        inner_path = QPainterPath()
        inner_path.addRoundedRect(inner, max(1, self.radius - 2), max(1, self.radius - 2))
        p.setPen(QPen(QColor(0, 0, 0, 75), 2.0))
        p.drawPath(inner_path)
        if self.border:
            p.setPen(QPen(self.border, 1.2))
            p.drawPath(path)


class Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.moveTo(0, 14)
        path.quadTo(0, 0, 14, 0)
        path.lineTo(r.width()-14, 0)
        path.quadTo(r.width(), 0, r.width(), 14)
        path.lineTo(r.width(), r.height())
        path.lineTo(0, r.height())
        path.closeSubpath()
        p.fillPath(path, HEADER)


class Progress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.color = QColor(GREEN)
        self.setFixedHeight(7)

    def set_value(self, value, color):
        self.value = max(0, min(100, int(value or 0)))
        self.color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(r, 3.5, 3.5)
        if self.value:
            fill = QRectF(r.x(), r.y(), r.width() * self.value / 100.0, r.height())
            p.setBrush(self.color)
            p.drawRoundedRect(fill, 3.5, 3.5)


class MenuPanel(RoundedPanel):
    def __init__(self, owner, position_menu=False):
        super().__init__(radius=11, color=QColor(20, 29, 42, 238),
                         border=QColor(76, 94, 118, 205))
        self.owner = owner
        self.position_menu = position_menu
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(230)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 7, 6, 7)
        self.layout.setSpacing(2)
        if position_menu:
            for label, anchor in [
                ("•   Posición libre", "free"),
                ("↖   Superior izquierda", "tl"),
                ("↗   Superior derecha", "tr"),
                ("↙   Inferior izquierda", "bl"),
                ("↘   Inferior derecha", "br"),
                ("◁   Centro izquierda", "cl"),
                ("▷   Centro derecha", "cr"),
            ]:
                self.item(label, lambda a=anchor: self.choose_anchor(a),
                          checked=owner.anchor == anchor)
        else:
            self.item("◉   Mostrar / ocultar", owner.hide)
            self.item("▣   Modo compacto", owner.toggle_compact, checked=owner.compact)
            self.item("◆   Siempre visible", owner.toggle_topmost, checked=owner.topmost)
            self.item(
                "↗   Abrir al iniciar Windows",
                owner.toggle_autostart,
                checked=owner.autostart_enabled(),
            )
            self.item("⌖   Anclar a                                      ›", self.open_anchor)
            self.sep()
            self.item("↻   Actualizar ahora", owner.refresh)
            self.sep()
            self.item("×   Salir de Codex Usage Monitor", owner.close_app, danger=True)

    def item(self, text, fn, checked=False, danger=False):
        lab = ClickableLabel(text + ("   ✓" if checked else ""))
        lab.setFixedHeight(29)
        lab.setCursor(Qt.PointingHandCursor)
        lab.setStyleSheet(f"""
            QLabel {{
                color: {'#ff5b69' if danger else '#f4f7fb'};
                padding-left: 8px; border-radius: 7px;
                font: 10px 'Segoe UI';
            }}
            QLabel:hover {{ background: rgba(65,82,105,185); }}
        """)
        lab.clicked.connect(lambda fn=fn: (self.close(), fn()))
        self.layout.addWidget(lab)

    def sep(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(80,99,124,150); margin: 3px 7px;")
        self.layout.addWidget(line)

    def open_anchor(self):
        pos = self.pos()
        self.close()
        m = MenuPanel(self.owner, True)
        self.owner.menu = m
        m.adjustSize()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(pos.x() + 215, area.right() - m.width())
        y = min(pos.y(), area.bottom() - m.height())
        m.move(x, y)
        m.show()
        m.raise_()
        m.activateWindow()

    def choose_anchor(self, anchor):
        self.close()
        self.owner.set_anchor(anchor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        # Qt.Popup normally closes itself when it loses activation. Keep this
        # fallback for Windows/Qt combinations where a frameless translucent
        # popup can remain visible after the owner loses focus.
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(0, self.close)
        super().changeEvent(event)


class Monitor(RoundedPanel):
    def __init__(self):
        super().__init__()
        self.bridge = Bridge()
        self.bridge.usage_ready.connect(self.apply_usage)
        self.bridge.usage_error.connect(self.show_error)
        self.bridge.rate_limits_updated.connect(self.request_reconciliation)
        self.client = CodexClient(notification_handler=self._on_notification)

        self.cfg_path = user_config_path()
        self.cfg = self.load_cfg()
        self.compact = bool(self.cfg.get("compact", False))
        self.topmost = bool(self.cfg.get("topmost", True))
        self.anchor = self.cfg.get("anchor", "free")
        self.usage = None
        self.deadlines = ResetDeadlines()
        self.refreshing = False
        self.reconciliation_pending = False
        self.reconciliation_scheduled = False
        self._applying_topmost = False
        self._last_topmost_error = None
        self._last_autostart_error = None
        self._screen_recovery_scheduled = False
        self._tracked_screens = []
        self.drag_offset = None
        self.menu = None

        # Use a normal top-level window. Qt.Tool has special z-order behaviour
        # on Windows and can remain above normal application windows even after
        # WindowStaysOnTopHint is removed.
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.build()
        self.apply_geometry()
        self.save_cfg()
        self.setup_tray()
        self.show()
        self.raise_()
        self._apply_topmost()
        self.setup_screen_tracking()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(60_000)
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(1000)
        QTimer.singleShot(150, self.refresh)

    def make_tray_icon(self):
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#45e66a"))
        p.drawEllipse(3, 3, 58, 58)
        p.setPen(QPen(QColor("#0a121d"), 7))
        f = QFont("Segoe UI", 31)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignCenter, "C")
        p.end()
        return QIcon(pix)

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self.make_tray_icon(), self)
        self.tray.setToolTip("Codex Usage Monitor")
        menu = QMenu()
        show_action = QAction("Mostrar / ocultar", menu)
        show_action.triggered.connect(self.toggle_visibility)
        compact_action = QAction("Modo compacto", menu)
        compact_action.triggered.connect(self.toggle_compact)
        update_action = QAction("Actualizar ahora", menu)
        update_action.triggered.connect(self.refresh)
        exit_action = QAction("Salir de Codex Usage Monitor", menu)
        exit_action.triggered.connect(self.close_app)
        menu.addAction(show_action)
        menu.addAction(compact_action)
        menu.addSeparator()
        menu.addAction(update_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.toggle_visibility()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def load_cfg(self):
        return load_settings(self.cfg_path)

    def save_cfg(self):
        self.cfg["x"], self.cfg["y"] = self.x(), self.y()
        self.cfg.pop("stable_reset_primary", None)
        self.cfg.pop("stable_reset_secondary", None)
        self.cfg.update(
            compact=self.compact,
            topmost=self.topmost,
            anchor=self.anchor,
        )
        try:
            save_settings(self.cfg, self.cfg_path)
        except (OSError, ValueError):
            logger.warning("Could not save settings", exc_info=True)

    def clear_layout(self):
        old = self.layout()
        if old:
            QWidget().setLayout(old)

    def label(self, text="", size=10, bold=False, color=TEXT, widget_class=QLabel):
        l = widget_class(text)
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        l.setFont(f)
        l.setStyleSheet(f"color:{color}; background:transparent;")
        return l

    def build(self):
        self.clear_layout()
        self.setFixedSize(*(COMPACT if self.compact else FULL))
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self.header = Header()
        h = QHBoxLayout(self.header)
        h.setContentsMargins(12, 0, 8, 0)
        h.setSpacing(6)
        self.dot = self.label("●", 12, False, MUTED)
        self.title_label = self.label("CODEX", 11, True)
        self.plan = self.label("Plus", 8, True, BLUE)
        self.plan.setStyleSheet(
            "color:#63adff;background:#17345b;border-radius:7px;padding:3px 9px;"
        )
        h.addWidget(self.dot); h.addWidget(self.title_label); h.addWidget(self.plan)
        h.addStretch()
        self.pin = self.label(
            "◆", 10, False, "#d4dfeb", widget_class=ClickableLabel
        )
        # Preserve the glyph's previous position while extending the invisible
        # hit target to the left; the visual layout remains unchanged.
        self.pin.setFixedWidth(25)
        self.pin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.pin.setCursor(Qt.PointingHandCursor)
        self.pin.clicked.connect(self.toggle_topmost)
        self.update_pin_state()
        close = self.label("×", 11, False, "#d4dfeb")
        close.setCursor(Qt.PointingHandCursor)
        close.mousePressEvent = lambda e: self.hide()
        h.addWidget(self.pin); h.addSpacing(8); h.addWidget(close)
        root.addWidget(self.header)

        if self.compact:
            self.build_compact(root)
        else:
            self.build_full(root)

    def build_full(self, root):
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(12, 5, 12, 5)
        v.setSpacing(2)
        self.p1 = self.meter(v, "◷  5 horas")
        self.sep(v)
        self.p2 = self.meter(v, "▣  7 días")
        self.sep(v)
        foot = QHBoxLayout()
        self.status = self.label("●  Conectando…", 8, True, MUTED)
        self.resets = self.label("↻  Reset ×—", 8, False, "#c6d0dd")
        foot.addWidget(self.status); foot.addStretch(); foot.addWidget(self.resets)
        v.addLayout(foot)
        root.addWidget(body)

    def meter(self, v, title):
        row = QHBoxLayout()
        name = self.label(title, 8, True)
        pct = self.label("—", 12, True)
        row.addWidget(name); row.addStretch(); row.addWidget(pct)
        v.addLayout(row)
        bar = Progress()
        v.addWidget(bar)
        reset = self.label("↻  Se reinicia en —", 7, False, MUTED)
        v.addWidget(reset)
        return bar, pct, reset

    def sep(self, v):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:rgba(65,82,105,125);")
        v.addWidget(line)

    def build_compact(self, root):
        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(9, 2, 9, 4)
        h.setSpacing(5)
        self.c5n = self.label("◷ 5H", 7, False, "#c5d0dc")
        self.c5 = self.chip("—")
        self.c7n = self.label("▣ 7D", 7, False, "#c5d0dc")
        self.c7 = self.chip("—")
        self.cstate = self.label("● Límite", 7, True, MUTED)
        self.ctime = self.label("—", 7)
        self.cresets = self.label("↻ ×—", 7, False, "#c6d0dd")
        for w in [self.c5n,self.c5,self.c7n,self.c7,self.cstate,self.ctime]:
            h.addWidget(w)
        h.addStretch()
        h.addWidget(self.cresets)
        root.addWidget(body)

    def chip(self, text):
        l = self.label(text, 7, True)
        l.setAlignment(Qt.AlignCenter)
        l.setMinimumWidth(35)
        l.setFixedHeight(18)
        l.setStyleSheet("color:#09111b;background:#536170;border-radius:7px;padding:0 5px;")
        return l

    def usage_color(self, window):
        if not window or window.used is None: return MUTED
        if window.used >= 100: return RED
        if window.used >= 80: return AMBER
        return GREEN

    def refresh(self):
        if self.refreshing: return
        self.refreshing = True
        def work():
            try:
                self.bridge.usage_ready.emit(self.client.usage())
            except CodexNotFoundError:
                self.bridge.usage_error.emit("not_found")
            except Exception:
                self.bridge.usage_error.emit("error")
        threading.Thread(target=work, daemon=True).start()

    def _on_notification(self, message):
        if message.get("method") == "account/rateLimits/updated":
            # This callback runs in the stdout reader. The Qt signal queues the
            # reconciliation in the GUI thread, where a normal read is safe.
            self.bridge.rate_limits_updated.emit()

    def request_reconciliation(self):
        self.reconciliation_pending = True
        if self.reconciliation_scheduled:
            return
        self.reconciliation_scheduled = True
        QTimer.singleShot(200, self._run_reconciliation)

    def _run_reconciliation(self):
        self.reconciliation_scheduled = False
        if not self.reconciliation_pending:
            return
        if self.refreshing:
            self.reconciliation_scheduled = True
            QTimer.singleShot(200, self._run_reconciliation)
            return
        self.reconciliation_pending = False
        self.refresh()

    def show_error(self, kind):
        self.refreshing = False
        self.usage = None
        self.deadlines = ResetDeadlines()
        if self.compact:
            for label in (self.c5, self.c7):
                label.setText("—")
                label.setStyleSheet(
                    f"color:#09111b;background:{MUTED};"
                    "border-radius:7px;padding:0 5px;"
                )
            self.ctime.setText("—")
            self.cresets.setText("↻ ×—")
            self.cstate.setText(codex_failure_text(kind, compact=True))
        else:
            for meter in (self.p1, self.p2):
                meter[0].set_value(0, MUTED)
                meter[1].setText("—")
                meter[1].setStyleSheet(f"color:{MUTED};background:transparent;")
                meter[2].setText("↻  Se reinicia en —")
            self.resets.setText("↻  Reset ×—")
            self.status.setText(codex_failure_text(kind))

    def apply_usage(self, u):
        self.refreshing = False
        self.deadlines.replace(u)
        self.usage = u
        self.save_cfg()
        state = GREEN if u.allowed is True else RED if u.allowed is False else MUTED
        self.dot.setStyleSheet(f"color:{state};background:transparent;")
        self.plan.setText((u.plan or "—").title())
        if self.compact:
            p = u.primary.used if u.primary and u.primary.used is not None else None
            s = u.secondary.used if u.secondary and u.secondary.used is not None else None
            for lab, val, win in [(self.c5,p,u.primary),(self.c7,s,u.secondary)]:
                c = self.usage_color(win)
                lab.setText(f"{val}%" if val is not None else "—")
                lab.setStyleSheet(f"color:#09111b;background:{c};border-radius:7px;padding:0 5px;")
            self.cstate.setText("● Límite" if u.allowed is False else "● OK")
            self.cstate.setStyleSheet(f"color:{state};background:transparent;")
            self.cresets.setText(f"↻ ×{u.reset_credits}")
        else:
            for meter, win in [(self.p1,u.primary),(self.p2,u.secondary)]:
                used = win.used if win and win.used is not None else None
                c = self.usage_color(win)
                meter[0].set_value(used or 0, c)
                meter[1].setText(f"{used}%" if used is not None else "—")
                meter[1].setStyleSheet(f"color:{c};background:transparent;")
            self.status.setText("●  Disponible" if u.allowed is True else
                                "●  Límite alcanzado" if u.allowed is False else
                                "●  Estado desconocido")
            self.status.setStyleSheet(f"color:{state};background:transparent;")
            self.resets.setText(f"↻  Reset ×{u.reset_credits}")
        self.tick()

    def countdown(self, deadline, short=False):
        sec = seconds_until(deadline)
        if sec is None:
            return "—"
        d, rem = divmod(sec, 86400)
        h, rem = divmod(rem, 3600)
        m, ss = divmod(rem, 60)
        if short:
            if d:
                return f"{d}d{h}h"
            if h:
                return f"{h}h{m:02}m"
            return f"{m}m"
        if d:
            return f"{d}d {h:02}h {m:02}m"
        return f"{h}h {m:02}m {ss:02}s"

    def tick(self):
        if not self.usage:
            return
        if self.compact:
            self.ctime.setText(self.countdown(self.deadlines.primary, True))
        else:
            self.p1[2].setText(
                "↻  Se reinicia en " + self.countdown(self.deadlines.primary)
            )
            self.p2[2].setText(
                "↻  Se reinicia en " + self.countdown(self.deadlines.secondary)
            )

    def toggle_compact(self):
        screen = self._current_screen()
        self.compact = not self.compact
        self.build(); self.apply_geometry(screen); self.save_cfg()
        if self.usage: self.apply_usage(self.usage)
        self._apply_topmost()

    def autostart_enabled(self):
        from .windows_autostart import build_startup_command, is_enabled

        try:
            enabled = is_enabled(build_startup_command())
            self._last_autostart_error = None
            return enabled
        except Exception as exc:
            self._last_autostart_error = str(exc)
            logger.warning("No se pudo leer Abrir al iniciar Windows: %s", exc)
            return False

    def toggle_autostart(self):
        from .windows_autostart import (
            build_startup_command,
            disable,
            enable,
            is_enabled,
        )

        command = build_startup_command()
        try:
            if is_enabled(command):
                disable()
                if is_enabled(command):
                    raise RuntimeError("Windows mantuvo el autostart activado")
            else:
                enable(command)
                if not is_enabled(command):
                    raise RuntimeError("Windows no activó el autostart")
            self._last_autostart_error = None
        except Exception as exc:
            self._last_autostart_error = str(exc)
            logger.warning("No se pudo cambiar Abrir al iniciar Windows: %s", exc)
            if hasattr(self, "tray"):
                self.tray.showMessage(
                    "Codex Usage Monitor",
                    "No se pudo cambiar Abrir al iniciar Windows.",
                    QSystemTrayIcon.Warning,
                    4000,
                )

    def update_pin_state(self):
        if not hasattr(self, "pin"):
            return
        if self.topmost:
            self.pin.setStyleSheet("color:#63adff;background:transparent;")
        else:
            self.pin.setStyleSheet("color:#d4dfeb;background:transparent;")

    def _apply_topmost(self, allow_retry=True):
        """Apply topmost using the native Windows z-order.

        The widget itself is a normal Qt.Window. On Windows we mark it as a
        tool-style window only to keep it out of the taskbar; TOPMOST is
        controlled exclusively by SetWindowPos.
        """
        if sys.platform == "win32":
            if self._applying_topmost:
                return True
            self._applying_topmost = True
            try:
                from .windows_topmost import apply_topmost

                apply_topmost(int(self.winId()), self.topmost)
                self._last_topmost_error = None
                return True
            except Exception as exc:
                self._last_topmost_error = str(exc)
                logger.warning("No se pudo aplicar Siempre visible: %s", exc)
                # Keep the saved user intent. Windows can transiently report
                # the old z-order while a newly created native window settles.
                if allow_retry:
                    QTimer.singleShot(0, lambda: self._apply_topmost(False))
                return False
            finally:
                self._applying_topmost = False
                self.update_pin_state()

        # Non-Windows fallback.
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.topmost)
        if self.isVisible():
            self.show()
        self.update_pin_state()
        return True

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._applying_topmost:
            QTimer.singleShot(0, self._apply_topmost)

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self._apply_topmost()
        self.update_pin_state()
        self.save_cfg()

    def contextMenuEvent(self, event):
        if self.menu: self.menu.close()
        self.menu = MenuPanel(self)
        self.menu.adjustSize()
        pos = event.globalPos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(pos.x(), area.right()-self.menu.width())
        y = min(pos.y(), area.bottom()-self.menu.height())
        self.menu.move(x, y)
        self.menu.show()
        self.menu.raise_()
        self.menu.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.anchor = "free"
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        self.snap(); self.save_cfg()
        super().mouseReleaseEvent(event)

    def snap(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        a = screen.availableGeometry()
        x,y,w,h = self.x(),self.y(),self.width(),self.height()
        if abs(x-a.left()) < SNAP and abs(y-a.top()) < SNAP: self.set_anchor("tl")
        elif abs((x+w)-a.right()) < SNAP and abs(y-a.top()) < SNAP: self.set_anchor("tr")
        elif abs(x-a.left()) < SNAP and abs((y+h)-a.bottom()) < SNAP: self.set_anchor("bl")
        elif abs((x+w)-a.right()) < SNAP and abs((y+h)-a.bottom()) < SNAP: self.set_anchor("br")

    def set_anchor(self, anchor):
        screen = self._current_screen()
        self.anchor = anchor; self.apply_geometry(screen); self.save_cfg()

    @staticmethod
    def _screen_rect(screen):
        area = screen.availableGeometry()
        return area.x(), area.y(), area.width(), area.height()

    def _available_screen_rects(self):
        primary = QGuiApplication.primaryScreen()
        screens = list(QGuiApplication.screens())
        if primary in screens:
            screens.remove(primary)
            screens.insert(0, primary)
        return [self._screen_rect(screen) for screen in screens]

    def _current_screen(self):
        return (
            QGuiApplication.screenAt(self.frameGeometry().center())
            or QGuiApplication.primaryScreen()
        )

    def apply_geometry(self, preferred_screen=None):
        primary = QGuiApplication.primaryScreen()
        screens = self._available_screen_rects()
        if not screens or primary is None:
            return

        width, height = self.width(), self.height()
        saved_x = int(self.cfg.get("x", screens[0][0] + screens[0][2] - width - MARGIN))
        saved_y = int(self.cfg.get("y", screens[0][1] + MARGIN))

        if self.anchor != "free":
            screen = preferred_screen
            if screen is None:
                saved_center = QPoint(saved_x + width // 2, saved_y + height // 2)
                screen = QGuiApplication.screenAt(saved_center) or primary
            x, y = anchor_position(
                self.anchor,
                (width, height),
                self._screen_rect(screen),
                MARGIN,
            )
        else:
            x, y = recover_position((saved_x, saved_y), (width, height), screens)
        self.move(x, y)

    def setup_screen_tracking(self):
        app = QGuiApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self._schedule_screen_recovery)
        for screen in QGuiApplication.screens():
            self._track_screen(screen)

    def _track_screen(self, screen):
        if any(tracked is screen for tracked in self._tracked_screens):
            return
        self._tracked_screens.append(screen)
        screen.geometryChanged.connect(self._schedule_screen_recovery)
        screen.availableGeometryChanged.connect(self._schedule_screen_recovery)

    def _screen_added(self, screen):
        self._track_screen(screen)
        self._schedule_screen_recovery()

    def _schedule_screen_recovery(self, *_args):
        if self._screen_recovery_scheduled:
            return
        self._screen_recovery_scheduled = True
        QTimer.singleShot(250, self._recover_after_screen_change)

    def _recover_after_screen_change(self):
        self._screen_recovery_scheduled = False
        if self.drag_offset is not None:
            self._schedule_screen_recovery()
            return

        if self.anchor != "free":
            self.apply_geometry(self._current_screen())
        else:
            position = recover_position(
                (self.x(), self.y()),
                (self.width(), self.height()),
                self._available_screen_rects(),
            )
            if position != (self.x(), self.y()):
                self.move(*position)
        self.save_cfg()

    def hide(self):
        super().hide()

    def close_app(self):
        self.save_cfg()
        if hasattr(self, "tray"):
            self.tray.hide()
        try:
            self.client.close()
        finally:
            QApplication.quit()
