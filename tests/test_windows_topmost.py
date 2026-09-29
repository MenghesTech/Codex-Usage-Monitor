from __future__ import annotations

import json
import sys
import ctypes

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 only")


def destroy_widget(window, app):
    from PySide6.QtCore import QCoreApplication, QEvent

    window.hide()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def open_topmost_menu_item(window, app):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    from src.widget import ClickableLabel

    local = QPoint(window.width() // 2, window.height() // 2)
    event = QContextMenuEvent(
        QContextMenuEvent.Mouse,
        local,
        window.mapToGlobal(local),
    )
    app.sendEvent(window, event)
    app.processEvents()
    return next(
        label
        for label in window.menu.findChildren(ClickableLabel)
        if "Siempre visible" in label.text()
    )


def test_real_widget_topmost_on_off_hide_show_and_compact(
    tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QApplication

    from src import widget
    from src.windows_topmost import apply_topmost, is_topmost

    app = QApplication.instance() or QApplication([])
    config = tmp_path / ".codex-usage-monitor-qt-v062.json"
    config.write_text(json.dumps({"topmost": False}), encoding="utf-8")
    monkeypatch.setattr(
        widget,
        "user_config_path",
        lambda: tmp_path / ".codex-usage-monitor-qt-v062.json",
    )
    monkeypatch.setattr(widget.Monitor, "refresh", lambda self: None)

    window = widget.Monitor()
    app.processEvents()
    hwnd = int(window.winId())
    states = []

    assert window.size().width() == 290 and window.size().height() == 175
    assert is_topmost(hwnd) is False
    states.append(("startup_false", is_topmost(hwnd)))
    assert apply_topmost(hwnd, True) is True
    window.topmost = True
    assert window._apply_topmost() is True
    assert is_topmost(hwnd) is True
    states.append(("enabled", is_topmost(hwnd)))

    window.toggle_topmost()
    app.processEvents()
    assert is_topmost(hwnd) is False
    states.append(("disabled", is_topmost(hwnd)))
    window.toggle_topmost()
    app.processEvents()
    assert is_topmost(hwnd) is True
    states.append(("enabled_again", is_topmost(hwnd)))

    window.hide()
    app.processEvents()
    window.show()
    app.processEvents()
    assert is_topmost(hwnd) is True
    states.append(("after_hide_show", is_topmost(hwnd)))

    window.toggle_compact()
    app.processEvents()
    assert window.size().width() == 290 and window.size().height() == 65
    assert is_topmost(hwnd) is True
    states.append(("compact", is_topmost(hwnd)))
    window.toggle_compact()
    app.processEvents()
    assert window.size().width() == 290 and window.size().height() == 175
    assert is_topmost(hwnd) is True
    states.append(("full", is_topmost(hwnd)))

    window.topmost = False
    assert window._apply_topmost() is True
    assert is_topmost(hwnd) is False
    states.append(("final_false", is_topmost(hwnd)))
    print("TOPMOST_REAL", states)
    window.tray.hide()
    destroy_widget(window, app)


def test_set_window_pos_false_raises_win32_error(monkeypatch):
    from src import windows_topmost

    def get_style(hwnd, index):
        return windows_topmost.WS_EX_TOOLWINDOW

    def set_style(hwnd, index, style):
        return windows_topmost.WS_EX_TOOLWINDOW

    def set_window_pos(*args):
        ctypes.set_last_error(1400)
        return 0

    monkeypatch.setattr(
        windows_topmost,
        "_functions",
        lambda: (get_style, set_style, set_window_pos),
    )

    with pytest.raises(windows_topmost.WindowsTopmostError) as exc_info:
        windows_topmost.apply_topmost(123, True)

    assert exc_info.value.errno == 1400


def test_real_ui_controls_toggle_native_topmost(tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from src import widget
    from src.windows_topmost import is_topmost

    app = QApplication.instance() or QApplication([])
    config = tmp_path / ".codex-usage-monitor-qt-v062.json"
    config.write_text(json.dumps({"topmost": False}), encoding="utf-8")
    monkeypatch.setattr(
        widget,
        "user_config_path",
        lambda: tmp_path / ".codex-usage-monitor-qt-v062.json",
    )
    monkeypatch.setattr(widget.Monitor, "refresh", lambda self: None)

    window = widget.Monitor()
    window.move(80, 120)
    window.show()
    window.raise_()
    app.processEvents()
    hwnd = int(window.winId())
    states = []

    assert window.topmost is False
    assert is_topmost(hwnd) is False
    assert window.pin.width() >= 24
    assert "color:#d4dfeb" in window.pin.styleSheet()
    assert "background:transparent" in window.pin.styleSheet()

    QTest.mouseClick(window.pin, Qt.LeftButton)
    app.processEvents()
    states.append(("pin_on", window.topmost, is_topmost(hwnd)))
    assert window.topmost is True
    assert is_topmost(hwnd) is True
    assert "color:#63adff" in window.pin.styleSheet()
    assert "background:transparent" in window.pin.styleSheet()
    assert "border" not in window.pin.styleSheet()

    QTest.mouseClick(window.pin, Qt.LeftButton)
    app.processEvents()
    states.append(("pin_off", window.topmost, is_topmost(hwnd)))
    assert window.topmost is False
    assert is_topmost(hwnd) is False
    assert "color:#d4dfeb" in window.pin.styleSheet()
    assert "background:transparent" in window.pin.styleSheet()

    menu_item = open_topmost_menu_item(window, app)
    QTest.mouseClick(menu_item, Qt.LeftButton)
    app.processEvents()
    states.append(("menu_on", window.topmost, is_topmost(hwnd)))
    assert window.topmost is True
    assert is_topmost(hwnd) is True
    assert "color:#63adff" in window.pin.styleSheet()
    assert "background:transparent" in window.pin.styleSheet()
    assert "border" not in window.pin.styleSheet()

    menu_item = open_topmost_menu_item(window, app)
    QTest.mouseClick(menu_item, Qt.LeftButton)
    app.processEvents()
    states.append(("menu_off", window.topmost, is_topmost(hwnd)))
    assert window.topmost is False
    assert is_topmost(hwnd) is False
    assert "color:#d4dfeb" in window.pin.styleSheet()
    assert "background:transparent" in window.pin.styleSheet()

    print("UI_TOPMOST_REAL", states)
    window.tray.hide()
    destroy_widget(window, app)


def test_position_compact_and_topmost_survive_widget_restart(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from src import widget
    from src.windows_topmost import is_topmost

    app = QApplication.instance() or QApplication([])
    area = app.primaryScreen().availableGeometry()
    expected = (area.x() + 120, area.y() + 140)
    config = tmp_path / ".codex-usage-monitor-qt-v062.json"
    config.write_text(
        json.dumps(
            {
                "topmost": True,
                "compact": True,
                "anchor": "free",
                "x": expected[0],
                "y": expected[1],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        widget,
        "user_config_path",
        lambda: tmp_path / ".codex-usage-monitor-qt-v062.json",
    )
    monkeypatch.setattr(widget.Monitor, "refresh", lambda self: None)

    first = widget.Monitor()
    app.processEvents()
    assert (first.x(), first.y()) == expected
    assert first.compact is True
    assert first.topmost is True
    assert is_topmost(int(first.winId())) is True
    first.save_cfg()
    first.tray.hide()
    destroy_widget(first, app)

    second = widget.Monitor()
    app.processEvents()
    assert (second.x(), second.y()) == expected
    assert second.compact is True
    assert second.topmost is True
    assert is_topmost(int(second.winId())) is True
    second.topmost = False
    second._apply_topmost()
    second.tray.hide()
    destroy_widget(second, app)
